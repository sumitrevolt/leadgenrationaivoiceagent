"""Context packets, packet cache, staged token budgets, handoff packets, redaction.

Hermetic: stdlib-pure modules under test; guardrails PII layer is exercised
only when importable (secret-shaped masking is asserted unconditionally).
"""

from __future__ import annotations

from app.dev_control.budgets import (
    DEFAULT_STAGE_BUDGETS,
    budget_state,
    build_handoff_packet,
    is_repeat_prompt,
    next_attempt_decision,
    prompt_fingerprint,
    total_budget,
)
from app.dev_control.context_packets import (
    PACKET_TOKEN_LIMITS,
    PacketCache,
    build_context_packet,
    cache_key,
    file_hashes,
    redact_packet_text,
)


def _packet(**overrides):
    base = dict(
        task_id="t-100",
        commit_sha="abc1234",
        size_class="standard",
        task_goal="Fix the UPI submit 404",
        business_impact="unblocks live payment path",
        acceptance_criteria=["route returns 200", "contract test green"],
        relevant_files=["app/api/upi.py"],
        code_excerpts=[
            {
                "path": "app/api/upi.py",
                "start": 1,
                "end": 5,
                "text": "from pydantic import BaseModel",
            }
        ],
        do_not_change=["app/marketing/packages.py"],
        security_rules=["no secrets in prompts"],
    )
    base.update(overrides)
    return build_context_packet(**base)


# ---------------------------------------------------------------- context packets
def test_packet_within_limit_is_ok_and_reproducible():
    a, b = _packet(), _packet()
    assert a["ok"] and b["ok"]
    assert a["cache_key"] == b["cache_key"], "same inputs must produce the same cache key"
    assert a["tokens"] <= PACKET_TOKEN_LIMITS["standard"]
    for heading in ("TASK GOAL", "ACCEPTANCE CRITERIA", "DO-NOT-CHANGE LIST", "TOKEN BUDGET"):
        assert heading in a["text"]


def test_oversize_packet_is_hard_blocked_even_with_justification():
    big = "x" * (PACKET_TOKEN_LIMITS["simple"] * 4 + 500)
    denied = _packet(size_class="simple", code_excerpts=[{"path": "big.py", "text": big}])
    assert denied["ok"] is False and denied["reason"] == "packet_over_budget"
    allowed = _packet(
        size_class="simple",
        code_excerpts=[{"path": "big.py", "text": big}],
        oversize_justification="full-file migration diff required",
    )
    assert allowed["ok"] is False and allowed["reason"] == "packet_over_budget"


def test_prior_failed_attempts_are_included_for_the_next_model():
    out = _packet(
        prior_failed_attempts=[
            {"attempt_no": 1, "provider": "deepseek", "error": "hallucinated route"}
        ]
    )
    assert "prior attempt #1 via deepseek: hallucinated route" in out["text"]


def test_cache_key_changes_only_when_inputs_change():
    h1 = file_hashes({"a.py": "content-1"})
    h2 = file_hashes({"a.py": "content-2"})
    k1 = cache_key(task_id="t", commit_sha="s1", relevant_file_hashes=h1, contract_version="v1")
    k_same = cache_key(task_id="t", commit_sha="s1", relevant_file_hashes=h1, contract_version="v1")
    assert k1 == k_same
    assert k1 != cache_key(
        task_id="t", commit_sha="s1", relevant_file_hashes=h2, contract_version="v1"
    )
    assert k1 != cache_key(
        task_id="t", commit_sha="s2", relevant_file_hashes=h1, contract_version="v1"
    )
    assert k1 != cache_key(
        task_id="t", commit_sha="s1", relevant_file_hashes=h1, contract_version="v2"
    )


def test_packet_cache_hit_miss_and_bounded_size():
    cache = PacketCache(max_entries=2)
    assert cache.get("k1") is None
    cache.put("k1", {"ok": True, "tokens": 1})
    assert cache.get("k1")["tokens"] == 1
    cache.put("k2", {"ok": True})
    cache.put("k3", {"ok": True})  # evicts oldest
    assert len(cache._store) == 2
    assert cache.hits == 1 and cache.misses >= 1


# ---------------------------------------------------------------- redaction
def test_secret_shaped_tokens_are_always_masked():
    text = (
        "key sk-live-abcdefghijklmnop1234 and Bearer abcdefghijklmnopqrstuvwx "
        "AKIAABCDEFGHIJKLMNOP eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sflKxwRJSMeKKF2QT4 "
        "GST 27ABCDE1234F1Z5\nSTRIPE_SECRET_KEY=whatever123"
    )
    out = redact_packet_text(text)
    assert "sk-live-abcdefghijklmnop1234" not in out
    assert "AKIAABCDEFGHIJKLMNOP" not in out
    assert "27ABCDE1234F1Z5" not in out
    assert "whatever123" not in out
    assert "[REDACTED_KEY]" in out and "[REDACTED_ENV]" in out


def test_pii_masked_when_guardrails_available():
    try:
        from app.voice_agent.guardrails import get_guardrails  # noqa: F401
    except Exception:
        import pytest

        pytest.skip("guardrails unavailable in this environment")
    out = redact_packet_text("call me at +91 98765 43210 or mail sumit@example.com")
    assert "98765" not in out and "sumit@example.com" not in out


# ---------------------------------------------------------------- token budgets
def test_budget_checkpoints_70_85_100():
    budget = 10_000
    assert budget_state(5_000, budget)["phase"] == "normal"
    assert budget_state(7_000, budget)["phase"] == "checkpoint"
    assert budget_state(8_500, budget)["phase"] == "wrap_up"
    assert budget_state(10_000, budget)["phase"] == "exhausted"
    assert budget_state(12_000, budget)["phase"] == "exhausted"


def test_default_stage_budgets_total():
    assert total_budget() == sum(DEFAULT_STAGE_BUDGETS.values()) == 68_000


def test_third_attempt_must_escalate():
    attempts = [
        {"provider": "deepseek", "ok": False},
        {"provider": "deepseek", "ok": False},
        {"provider": "local", "ok": False},
    ]
    decision = next_attempt_decision(attempts, "deepseek")
    assert decision["allowed"] is False
    assert decision["required_action"] == "escalate_to_stronger_model"
    assert next_attempt_decision(attempts, "local")["allowed"] is True  # only 1 failure


def test_successful_attempts_do_not_count_against_the_cap():
    attempts = [{"provider": "deepseek", "ok": True}, {"provider": "deepseek", "ok": False}]
    assert next_attempt_decision(attempts, "deepseek")["allowed"] is True


def test_repeat_identical_prompt_is_refused():
    fp = prompt_fingerprint("  fix the bug ")
    assert is_repeat_prompt([fp], "fix the bug") is True
    assert is_repeat_prompt([fp], "fix the bug differently") is False


# ---------------------------------------------------------------- handoff packets
def _handoff_fields(**overrides):
    fields = dict(
        work_completed="atomic claim implemented",
        files_changed=["app/dev_control/claims.py"],
        commands_run=["pytest tests/test_dev_control_claims.py -q"],
        tests_run="6",
        tests_passing="6",
        tests_failing="0",
        current_blocker="none",
        likely_cause="n/a",
        next_exact_action="wire API layer",
        investigations_already_completed=["checked reconcile path"],
        decisions_made=["conditional UPDATE over advisory locks"],
        remaining_risk="low",
    )
    fields.update(overrides)
    return fields


def test_handoff_packet_requires_all_12_fields():
    incomplete = _handoff_fields()
    incomplete.pop("current_blocker")
    out = build_handoff_packet(**incomplete)
    assert out["ok"] is False and out["missing"] == ["current_blocker"]


def test_handoff_packet_complete_and_redacted():
    out = build_handoff_packet(
        **_handoff_fields(remaining_risk="token sk-live-abcdefghijklmnop1234 leaked?")
    )
    assert out["ok"] is True
    assert "sk-live-abcdefghijklmnop1234" not in out["text"]
    assert "NEXT EXACT ACTION" in out["text"]


def test_handoff_packet_rejects_unknown_fields():
    out = build_handoff_packet(**_handoff_fields(), extra_field="nope")
    assert out["ok"] is False and out["reason"] == "unknown_fields"
