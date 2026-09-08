"""Memory governance — two redaction policies, do-not-remember, staleness/conflict.

Review P0/P1: latency must not buy itself with privacy. Policy A (prompt-bound)
keeps authorized lead data but removes secrets; Policy B (logs/audit/admin/UI)
removes secrets AND PII. Plus the previously-missing controls: do-not-remember
and deterministic stale-fact resolution.
"""

from __future__ import annotations

import pytest

from app.platform import memory_governance as gov

SECRET = "sk-ABCDEFGHIJKLMNOP1234"  # pragma: allowlist secret
SAMPLE = f"lead Ramesh 9876543210 ram@example.com key {SECRET}"


@pytest.fixture()
def gov_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_SUPPRESSION_PATH", str(tmp_path / "supp.jsonl"))
    monkeypatch.setenv("MEMORY_GOVERNANCE_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    yield gov


# ------------------------------------------------------------ policy split


def test_policy_a_strips_secrets_but_keeps_authorized_lead_data():
    out = gov.scrub_secrets(SAMPLE)
    assert SECRET not in out
    assert "9876543210" in out and "ram@example.com" in out  # the memory payload


def test_policy_b_masks_pii_and_secrets():
    out = gov.mask_for_observability(SAMPLE)
    assert SECRET not in out
    assert "9876543210" not in out
    assert "ram@example.com" not in out


def test_policy_b_covers_more_secret_shapes():
    for raw in (
        "AKIAABCDEFGHIJKLMNOP",  # pragma: allowlist secret
        "AIzaSyA1234567890123456789012345678901",  # pragma: allowlist secret
        "GEMINI_API_KEY=supersecretvalue",  # pragma: allowlist secret
    ):
        assert raw not in gov.mask_for_observability(f"value {raw} here")


def test_mask_row_masks_text_and_drops_raw_payload():
    row = {
        "id": "r1",
        "action": "call 9876543210",
        "note": "ram@example.com",
        "payload": {"client_id": "c1", "internal": "x"},
    }
    out = gov.mask_row(row)
    assert "9876543210" not in out["action"]
    assert "ram@example.com" not in out["note"]
    assert "payload" not in out  # raw payload never leaves the process
    assert out["payload_keys"] == ["client_id", "internal"]


# --------------------------------------------------------- do-not-remember


def test_suppress_validates_input(gov_env):
    assert gov.suppress("", "session", "s1")["ok"] is False
    assert gov.suppress("tenantA", "bogus", "s1")["ok"] is False
    assert gov.suppress("tenantA", "pattern", "[unclosed")["ok"] is False
    assert gov.suppress("tenantA", "session", "")["ok"] is False


def test_suppression_is_tenant_scoped(gov_env):
    gov.suppress("tenantA", "session", "private-session")
    assert gov.is_suppressed("tenantA", session_id="private-session") is True
    assert gov.is_suppressed("tenantB", session_id="private-session") is False
    assert gov.is_suppressed("", session_id="private-session") is False


def test_pattern_rule_and_revocation(gov_env):
    rule = gov.suppress("tenantA", "pattern", r"credit\s*card")["rule"]
    assert gov.is_suppressed("tenantA", text="my Credit Card number") is True

    assert gov.unsuppress("tenantB", rule["id"])["ok"] is False  # not your rule
    assert gov.unsuppress("tenantA", rule["id"])["ok"] is True
    assert gov.is_suppressed("tenantA", text="my credit card") is False
    assert gov.list_rules("tenantA") == []


def test_audit_records_hash_not_content(gov_env, tmp_path):
    gov.audit("tenantA", "suppress", matched_text="my credit card 4111111111111111")
    blob = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "credit card" not in blob
    assert "4111111111111111" not in blob
    assert "matched_hash" in blob


def test_damaged_rules_fail_closed_for_durable_writes(gov_env, tmp_path):
    """P0: an untrustworthy DNR authority must BLOCK durable memory, not warn."""
    (tmp_path / "supp.jsonl").write_text("{not json\n", encoding="utf-8")

    health = gov.governance_health()
    assert health["ok"] is False and "unparsable" in health["reason"]

    decision = gov.check_write("tenantA", session_id="x", text="lead said something")
    assert decision["decision"] == gov.DECISION_DEFERRED
    assert decision["code"] == gov.DEFER_CODE
    assert "something" not in str(decision)  # reason only, never the content
    assert gov.remembering_allowed("tenantA") is False

    # non-durable (hot cache) is still permitted — "answer without remembering"
    assert gov.check_write("tenantA", text="x", durable=False)["decision"] != gov.DECISION_DEFERRED


def test_rule_evaluation_error_is_deferred_not_suppressed(gov_env, monkeypatch):
    """Cannot prove 'not suppressed' => durable write is DEFERRED (never leak).

    An outage is NOT a suppression (no fabrication of suppression audits / no
    destructive delete). `is_suppressed` reports only real matches (error =>
    False = "unknown"); the fail-closed decision lives in `check_write`.
    """

    def boom(_tenant):
        raise RuntimeError("rule store exploded")

    monkeypatch.setattr(gov, "list_rules", boom)
    assert gov.is_suppressed("tenantA", text="anything") is False  # unknown, not suppressed
    d = gov.check_write("tenantA", text="anything")
    assert d["decision"] == gov.DECISION_DEFERRED
    assert d["code"] == gov.DEFER_CODE


def test_guard_is_a_noop_while_the_memory_stack_is_off(gov_env, tmp_path, monkeypatch):
    (tmp_path / "supp.jsonl").write_text("{not json\n", encoding="utf-8")
    monkeypatch.delenv("MEMORY_STACK_ENABLED", raising=False)
    assert gov.guard_durable_write("tenantA", text="x")["decision"] == gov.DECISION_ALLOW
    assert gov.durable_writes_allowed()["ok"] is True

    monkeypatch.setenv("MEMORY_STACK_ENABLED", "1")
    assert gov.guard_durable_write("tenantA", text="x")["decision"] == gov.DECISION_DEFERRED
    assert gov.durable_writes_allowed()["ok"] is False


def test_missing_tenant_is_refused_not_defaulted(gov_env):
    d = gov.check_write("", text="x")
    assert d["decision"] == gov.DECISION_DEFERRED and "tenant" in d["reason"]


def test_forget_requires_tenant(gov_env):
    assert gov.forget("")["ok"] is False


# ------------------------------------------------------- staleness/conflict


def test_newest_observed_fact_wins():
    text = "\n".join(
        [
            "- city: Pune (observed: 2026-01-01T00:00:00Z)",
            "- city: Mumbai (observed: 2026-08-01T00:00:00Z)",
            "- status: trial (observed: 2026-08-01T00:00:00Z)",
            "plain narrative line, not a fact",
        ]
    )
    out, dropped = gov.resolve_conflicts(text)
    assert "Mumbai" in out and "Pune" not in out
    assert "status: trial" in out
    assert "plain narrative line" in out
    assert any(d["reason"] == "stale" for d in dropped)


def test_equal_time_is_broken_by_source_authority():
    """Determinism alone is not correctness — authority decides, not lane order."""
    items = [
        ("procedural", "- plan: combo (observed: 2026-08-01T00:00:00Z)"),  # first, low authority
        ("semantic", "- plan: main (observed: 2026-08-01T00:00:00Z)"),  # later, authoritative
    ]
    out, report = gov.resolve_facts(items)
    joined = " ".join(t for _lane, t in out)
    assert "main" in joined and "combo" not in joined
    assert any(r["reason"] == gov.REASON_STALE for r in report)


def test_unresolved_equal_time_conflict_injects_neither_value():
    items = [
        ("semantic", "- plan: main (observed: 2026-08-01T00:00:00Z)"),
        ("semantic", "- plan: combo (observed: 2026-08-01T00:00:00Z)"),
    ]
    out, report = gov.resolve_facts(items)
    joined = " ".join(t for _lane, t in out)
    assert "main" not in joined and "combo" not in joined  # contradiction never injected
    conflicted = [r for r in report if r["reason"] == gov.REASON_CONFLICTED]
    assert len(conflicted) == 2  # both preserved for review
    assert all("value" in r and "key" in r for r in conflicted)


def test_malformed_timestamp_never_outranks_a_valid_one():
    items = [
        ("semantic", "- city: Pune (observed: NOT-A-DATE)"),
        ("procedural", "- city: Mumbai (observed: 2026-08-01T00:00:00Z)"),
    ]
    out, _ = gov.resolve_facts(items)
    joined = " ".join(t for _lane, t in out)
    assert "Mumbai" in joined and "Pune" not in joined


def test_conflict_resolution_is_tenant_agnostic_but_lane_aware(monkeypatch):
    monkeypatch.setenv("MEMORY_STACK_LANE_AUTHORITY", "working:9")
    items = [
        ("semantic", "- plan: main (observed: 2026-08-01T00:00:00Z)"),
        ("working", "- plan: hot (observed: 2026-08-01T00:00:00Z)"),
    ]
    out, _ = gov.resolve_facts(items)
    joined = " ".join(t for _lane, t in out)
    assert "hot" in joined and "main" not in joined  # config overrides the default rank


def test_identical_values_are_not_a_conflict():
    out, dropped = gov.resolve_conflicts("- city: Pune\n- city: Pune")
    assert out.count("Pune") == 1
    assert dropped and dropped[0]["reason"] == "duplicate"


def test_resolve_conflicts_never_raises_on_junk():
    for junk in ("", "::::", "- : ", "no colon here"):
        out, dropped = gov.resolve_conflicts(junk)
        assert isinstance(out, str) and isinstance(dropped, list)
