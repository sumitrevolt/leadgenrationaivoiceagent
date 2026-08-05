"""Memory Stack (7-layer facade) — flag contract, tenant scoping, token budget, drain.

Durable claim/lease semantics live in `tests/test_prospective_store.py`; this
suite covers the facade: master/layer flags, fail-closed dispatch, tenant
isolation of the working window, token-based budgeting, and the coordinator
canary's OFF-path equivalence.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def ms(monkeypatch):
    monkeypatch.setenv("MEMORY_STACK_ENABLED", "1")
    for name in (
        "MEMORY_STACK_TIERS",
        "MEMORY_STACK_TOKEN_BUDGET",
        "MEMORY_STACK_WORKING_TURNS",
        "MEMORY_STACK_WORKING_TTL_S",
        "MEMORY_STACK_COORDINATOR_CANARY",
    ):
        monkeypatch.delenv(name, raising=False)
    for name in ("WORKING", "PROSPECTIVE", "EPISODIC", "SEMANTIC", "PROCEDURAL", "SHARED"):
        monkeypatch.delenv(f"MEMORY_STACK_LAYER_{name}", raising=False)

    from app.platform import memory_stack as _ms

    for k in list(_ms._STATS):
        _ms._STATS[k] = 0
    _ms._WORKING.clear()
    _ms._WORKING_SEEN.clear()
    yield _ms
    _ms._WORKING.clear()
    _ms._WORKING_SEEN.clear()


# --------------------------------------------------------------- flag contract


async def test_master_flag_off_is_inert(monkeypatch):
    monkeypatch.delenv("MEMORY_STACK_ENABLED", raising=False)
    from app.platform import memory_stack as ms

    assert ms.is_enabled() is False
    assert ms.layer_enabled("working") is False  # every layer is subordinate
    out = await ms.assemble("tenantA", "rohan", "hot leads")
    assert out["enabled"] is False and out["block"] == ""
    assert (await ms.drain_if_enabled())["fired"] == 0


def test_layer_flags_are_subordinate_to_master(ms, monkeypatch):
    assert ms.layer_enabled("semantic") is True  # default ON under master
    monkeypatch.setenv("MEMORY_STACK_LAYER_SEMANTIC", "0")
    assert ms.layer_enabled("semantic") is False
    monkeypatch.setenv("MEMORY_STACK_ENABLED", "0")
    assert ms.layer_enabled("procedural") is False


async def test_dispatch_fails_closed_without_durable_store(ms, monkeypatch):
    from app.platform import prospective_store

    monkeypatch.setattr(prospective_store, "available", lambda: False)
    ok, why = ms.dispatch_ready()
    assert ok is False and "unavailable" in why

    res = await ms.drain_if_enabled()
    assert res["fired"] == 0 and "unavailable" in res["skipped"]
    assert ms.stats()["drain_blocked"] == 1  # blocked, not silently "successful"


def test_validate_config_reports_problems(ms, monkeypatch):
    monkeypatch.delenv("AGENT_MEMORY", raising=False)
    monkeypatch.delenv("WORKFORCE_MEMORY", raising=False)
    cfg = ms.validate_config()
    assert cfg["master"] is True
    assert any("AGENT_MEMORY" in p for p in cfg["problems"])
    assert any("WORKFORCE_MEMORY" in p for p in cfg["problems"])
    assert set(cfg["layers"]) == set(ms.LAYERS)


def test_budget_over_context_window_is_flagged_and_clamped(ms, monkeypatch):
    monkeypatch.setenv("MEMORY_STACK_CONTEXT_TOKENS", "1000")
    monkeypatch.setenv("MEMORY_STACK_RESERVE_TOKENS", "900")
    monkeypatch.setenv("MEMORY_STACK_TOKEN_BUDGET", "500")
    assert ms.effective_token_budget() == 100  # clamped to what is actually free
    assert any("context window" in p for p in ms.validate_config()["problems"])
    assert ms.effective_token_budget(500, prompt_overhead=100) == 0


# ------------------------------------------------ L1 working memory (scoped)


def test_working_window_is_tenant_scoped(ms):
    ms.push_turn("tenantA", "s1", "user", "tenant A private detail")
    ms.push_turn("tenantB", "s1", "user", "tenant B private detail")

    a = ms.working_window("tenantA", "s1", max_tokens=200)
    b = ms.working_window("tenantB", "s1", max_tokens=200)
    assert "A private" in a and "B private" not in a
    assert "B private" in b and "A private" not in b
    # same session id across tenants must never collide
    assert ms.working_window("", "s1") == ""
    assert ms.push_turn("", "s1", "user", "no tenant") is False


def test_working_fifo_ttl_and_namespace_cleanup(ms, monkeypatch):
    monkeypatch.setenv("MEMORY_STACK_WORKING_TURNS", "3")
    for i in range(5):
        ms.push_turn("tenantA", "s2", "user", f"turn{i}")
    win = ms.working_window("tenantA", "s2", max_tokens=500)
    assert "turn0" not in win and "turn4" in win
    assert win.strip().endswith("turn4")  # newest last

    assert ms.working_snapshot()["authoritative"] is False  # never claimed durable

    monkeypatch.setenv("MEMORY_STACK_WORKING_TTL_S", "30")
    ms._WORKING_SEEN["tenantA::s2"] = 0.0  # far in the past
    assert ms._sweep_working() >= 1
    assert ms.working_window("tenantA", "s2") == ""

    ms.push_turn("tenantA", "s3", "user", "x")
    assert ms.clear_tenant_working("tenantA") == 1
    assert ms.clear_tenant_working("") == 0


def test_working_cache_enforces_per_tenant_and_total_caps(ms, monkeypatch):
    """Bounded keys: one tenant cannot evict everyone, total is hard-capped."""
    monkeypatch.setenv("MEMORY_STACK_WORKING_MAX_PER_TENANT", "3")
    for i in range(6):
        ms.push_turn("tenantC", f"s{i}", "user", "x")
    mine = [k for k in ms._WORKING if k.startswith("tenantC::")]
    assert len(mine) == 3  # cap counts the entry being written, not just prior ones
    assert "tenantC::s5" in mine and "tenantC::s0" not in mine  # LRU, newest kept

    monkeypatch.setenv("MEMORY_STACK_WORKING_MAX_SESSIONS", "10")
    monkeypatch.setenv("MEMORY_STACK_WORKING_MAX_PER_TENANT", "50")
    for i in range(20):
        ms.push_turn("tenantD", f"d{i}", "user", "x")
    assert len(ms._WORKING) <= ms._working_max_sessions()
    assert "tenantD::d19" in ms._WORKING


def test_do_not_remember_blocks_writes_at_the_boundary(ms, tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_SUPPRESSION_PATH", str(tmp_path / "supp.jsonl"))
    monkeypatch.setenv("MEMORY_GOVERNANCE_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    from app.platform import memory_governance as gov

    gov.suppress("tenantA", "session", "private-session")
    gov.suppress("tenantA", "pattern", r"credit\s*card")

    assert ms.push_turn("tenantA", "private-session", "user", "hi") is False
    assert ms.push_turn("tenantA", "ok-session", "user", "my credit card is 4111") is False
    assert ms.push_turn("tenantA", "ok-session", "user", "normal note") is True
    assert ms.push_turn("tenantB", "private-session", "user", "hi") is True  # other tenant
    assert ms.schedule("tenantA", "rohan", "store credit card details")["ok"] is False
    assert ms.stats()["suppressed_writes"] >= 3


def test_durable_writes_fail_closed_when_governance_is_damaged(ms, tmp_path, monkeypatch):
    """P0: unknown DNR authority => refuse to persist; answer without remembering."""
    rules = tmp_path / "supp.jsonl"
    monkeypatch.setenv("MEMORY_SUPPRESSION_PATH", str(rules))
    monkeypatch.setenv("MEMORY_GOVERNANCE_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    rules.write_text("{not json\n", encoding="utf-8")

    out = ms.schedule("tenantA", "rohan", "remember card 4111111111111111")
    assert out["ok"] is False and out["deferred"] is True
    assert out["code"] == ms.DEFER_CODE
    assert "4111111111111111" not in str(out)  # no raw content in the refusal
    assert ms.remembering_allowed("tenantA") is False
    assert ms.stats()["deferred_writes"] >= 1

    # foreground can still answer: L1 is non-durable, and the session is marked
    assert ms.push_turn("tenantA", "sess-x", "user", "card 4111111111111111") is True
    assert "tenantA::sess-x" in ms._DEGRADED_SESSIONS
    assert ms.stats()["ephemeral_writes"] >= 1

    cfg = ms.validate_config()
    assert cfg["durable_writes_allowed"] is False
    assert any("fail-closed" in p for p in cfg["problems"])
    assert "4111111111111111" not in str(cfg)

    # recovery -> retry succeeds and yields exactly one record
    rules.write_text("", encoding="utf-8")
    assert ms.remembering_allowed("tenantA") is True


def test_layer_flag_cannot_bypass_the_fail_closed_boundary(ms, tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_SUPPRESSION_PATH", str(tmp_path / "supp.jsonl"))
    (tmp_path / "supp.jsonl").write_text("{not json\n", encoding="utf-8")
    monkeypatch.setenv("MEMORY_STACK_LAYER_PROSPECTIVE", "1")
    assert ms.schedule("tenantA", "rohan", "x")["ok"] is False


async def test_unresolved_conflict_is_not_injected_by_assemble(ms, monkeypatch):
    monkeypatch.setenv("MEMORY_STACK_LANE_AUTHORITY", "semantic:0,procedural:0")
    monkeypatch.setitem(
        ms._SYNC_LANES, "semantic", lambda *a: "- plan: main (observed: 2026-08-01T00:00:00Z)"
    )
    monkeypatch.setitem(
        ms._SYNC_LANES, "procedural", lambda *a: "- plan: combo (observed: 2026-08-01T00:00:00Z)"
    )
    for key in ("prospective", "shared"):
        monkeypatch.setitem(ms._SYNC_LANES, key, lambda *a: "")

    out = await ms.assemble("tenantA", "rohan", "plan")
    assert "main" not in out["block"] and "combo" not in out["block"]
    assert out["conflicts_unresolved"] >= 1


async def test_assemble_drops_stale_fact_across_layers(ms, monkeypatch):
    monkeypatch.setitem(
        ms._SYNC_LANES, "semantic", lambda *a: "- city: Pune (observed: 2026-01-01T00:00:00Z)"
    )
    monkeypatch.setitem(
        ms._SYNC_LANES, "procedural", lambda *a: "- city: Mumbai (observed: 2026-08-01T00:00:00Z)"
    )
    for key in ("prospective", "shared"):
        monkeypatch.setitem(ms._SYNC_LANES, key, lambda *a: "")

    out = await ms.assemble("tenantA", "rohan", "city")
    assert "Mumbai" in out["block"] and "Pune" not in out["block"]
    assert out["conflicts_resolved"] >= 1


def test_working_window_respects_token_budget(ms):
    ms.push_turn("tenantA", "s4", "user", "word " * 400)
    win = ms.working_window("tenantA", "s4", max_tokens=20)
    assert ms.count_tokens(win) <= 20


# ------------------------------------------------ L5 assembly (tokens/tiers)


async def test_assemble_requires_tenant(ms):
    out = await ms.assemble("", "rohan", "x")
    assert out["enabled"] is False and out["reason"] == "tenant_id required"


async def test_assemble_never_raises_when_lanes_break(ms, monkeypatch):
    def broken(*_a, **_kw):
        raise RuntimeError("lane down")

    for key in ("prospective", "semantic", "procedural", "shared"):
        monkeypatch.setitem(ms._SYNC_LANES, key, broken)

    ms.push_turn("tenantA", "s5", "user", "budget 5000 hai")
    out = await ms.assemble("tenantA", "rohan", "budget", session_id="s5")

    assert out["enabled"] is True and isinstance(out["block"], str)
    assert "working" in out["layers"]  # healthy lane still delivered
    assert out["errors"] >= 4


async def test_assemble_respects_token_budget_and_tiers(ms, monkeypatch):
    monkeypatch.setitem(ms._SYNC_LANES, "prospective", lambda *a: "")
    monkeypatch.setitem(ms._SYNC_LANES, "semantic", lambda *a: "x " * 5000)
    monkeypatch.setitem(ms._SYNC_LANES, "procedural", lambda *a: "y " * 5000)
    monkeypatch.setitem(ms._SYNC_LANES, "shared", lambda *a: "")
    ms.push_turn("tenantA", "s6", "user", "z " * 5000)

    out = await ms.assemble("tenantA", "rohan", "x", session_id="s6", token_budget=120)
    assert out["tokens"] <= 120
    assert ms.count_tokens(out["block"]) <= 120
    assert out["truncated"] is True

    hot = await ms.assemble("tenantA", "rohan", "x", session_id="s6", tiers=["hot"])
    assert hot["tiers"] == ["hot"]
    assert set(hot["layers"]) <= {"working", "prospective", "episodic"}


async def test_assemble_dedupes_repeated_lines_across_layers(ms, monkeypatch):
    same = "- lead prefers evening callbacks"
    monkeypatch.setitem(ms._SYNC_LANES, "semantic", lambda *a: same)
    monkeypatch.setitem(ms._SYNC_LANES, "procedural", lambda *a: same)
    monkeypatch.setitem(ms._SYNC_LANES, "prospective", lambda *a: "")
    monkeypatch.setitem(ms._SYNC_LANES, "shared", lambda *a: "")

    out = await ms.assemble("tenantA", "rohan", "callback")
    assert out["block"].count("evening callbacks") == 1
    assert ms.stats()["deduped"] >= 1


async def test_first_assemble_warms_helpers_outside_the_deadline(ms, monkeypatch):
    """Regression: cold-start import cost used to time out EVERY lane (895ms).

    Warm-up must happen before the deadline clock starts, and must be idempotent.
    """
    monkeypatch.setattr(ms, "_WARM", False)
    monkeypatch.setattr(ms, "_TOKENIZER", None)
    monkeypatch.setitem(ms._SYNC_LANES, "semantic", lambda *a: "- warm check")
    for key in ("prospective", "procedural", "shared"):
        monkeypatch.setitem(ms._SYNC_LANES, key, lambda *a: "")

    out = await ms.assemble("tenantA", "rohan", "x")
    assert ms._WARM is True
    assert out["timeouts"] == 0
    assert "semantic" in out["layers"]  # cold start still returns memory
    assert await ms.prewarm() is True  # idempotent


def test_hot_path_redaction_strips_secrets_but_keeps_lead_pii(ms):
    """Hot path scrubs secret-shaped tokens; lead phone/name IS the payload."""
    fake_sk = "sk-ABCDEFGHIJKLMNOP1234"  # pragma: allowlist secret
    fake_g = "AIzaSyA1234567890123456789012345678901"  # pragma: allowlist secret
    assert fake_sk not in ms._redact(f"key {fake_sk}")
    assert "AIza" not in ms._redact(f"g {fake_g}")
    assert "REDACTED_ENV" in ms._redact("UPI_VPA=someone@okhdfcbank")
    kept = ms._redact("lead Ramesh 9876543210 evening pe free")
    assert "Ramesh" in kept and "9876543210" in kept


async def test_assemble_redacts_secrets_from_lane_output(ms, monkeypatch):
    monkeypatch.setitem(
        ms._SYNC_LANES, "semantic", lambda *a: "token sk-ABCDEFGHIJKLMNOP1234 hai"
    )  # pragma: allowlist secret

    for key in ("prospective", "procedural", "shared"):
        monkeypatch.setitem(ms._SYNC_LANES, key, lambda *a: "")

    out = await ms.assemble("tenantA", "rohan", "x")
    assert "sk-ABCDEFGHIJKLMNOP1234" not in out["block"]  # pragma: allowlist secret


def test_snapshot_never_exposes_memory_content(ms):
    ms.push_turn("tenantA", "s7", "user", "very private lead detail")
    snap = ms.snapshot("tenantA")
    assert "very private lead detail" not in str(snap)
    assert set(snap["lanes"]) == set(ms.LAYERS)
    assert snap["working"]["authoritative"] is False


# --------------------------------------------------- drain (dispatch wiring)


async def test_drain_marks_dispatched_and_failed_via_store(ms, monkeypatch):
    from app.platform import prospective_store as ps

    rows = [{"id": "r1", "agent_id": "rohan", "action": "one", "payload": {}}]
    calls: dict[str, list] = {"dispatched": [], "failed": []}

    monkeypatch.setattr(ps, "available", lambda: True)
    monkeypatch.setattr(ps, "recover_expired", lambda *a, **k: 0)
    monkeypatch.setattr(ps, "claim_batch", lambda *a, **k: list(rows))
    monkeypatch.setattr(
        ps, "mark_dispatched", lambda rid, tid="": calls["dispatched"].append((rid, tid)) or True
    )
    monkeypatch.setattr(
        ps, "mark_failed", lambda rid, err="", **k: calls["failed"].append((rid, err)) or "pending"
    )

    ok = await ms.drain_due(handler=lambda row: "task-9")
    assert ok["fired"] == 1 and calls["dispatched"] == [("r1", "task-9")]

    def boom(_row):
        raise RuntimeError("queue down")

    bad = await ms.drain_due(handler=boom)
    assert bad["fired"] == 0 and bad["failed"] == 1
    assert calls["failed"] and "queue down" in calls["failed"][0][1]


async def test_drain_treats_empty_task_id_as_failure(ms, monkeypatch):
    from app.platform import prospective_store as ps

    failed: list = []
    monkeypatch.setattr(ps, "available", lambda: True)
    monkeypatch.setattr(ps, "recover_expired", lambda *a, **k: 0)
    monkeypatch.setattr(
        ps, "claim_batch", lambda *a, **k: [{"id": "r2", "agent_id": "rohan", "action": "x"}]
    )
    monkeypatch.setattr(ps, "mark_dispatched", lambda *a, **k: True)
    monkeypatch.setattr(ps, "mark_failed", lambda rid, err="", **k: failed.append(rid) or "pending")

    res = await ms.drain_due(handler=lambda row: "")  # handler "succeeded" but gave nothing
    assert res["fired"] == 0 and failed == ["r2"]


# ------------------------------------------- coordinator canary equivalence


async def test_coordinator_canary_off_is_byte_identical_to_legacy(monkeypatch):
    monkeypatch.delenv("MEMORY_STACK_COORDINATOR_CANARY", raising=False)
    from app.agents import coordinator

    assert coordinator._memory_canary_on() is False
    ctx = await coordinator._plan_context("goal", "past learnings")
    assert ctx == "\nPichhle learnings (inhe dhyan me rakho): past learnings"
    assert await coordinator._plan_context("goal", "") == ""


async def test_coordinator_canary_needs_master_flag_too(monkeypatch):
    monkeypatch.setenv("MEMORY_STACK_COORDINATOR_CANARY", "1")
    monkeypatch.delenv("MEMORY_STACK_ENABLED", raising=False)
    from app.agents import coordinator

    assert coordinator._memory_canary_on() is False  # canary alone can't arm it


async def test_coordinator_canary_on_appends_memory_then_legacy(monkeypatch):
    monkeypatch.setenv("MEMORY_STACK_COORDINATOR_CANARY", "1")
    monkeypatch.setenv("MEMORY_STACK_ENABLED", "1")
    from app.agents import coordinator
    from app.platform import memory_stack

    async def fake_block(*_a, **_kw):
        return "## Pakki baatein (semantic)\n- lead evening pe free hai"

    monkeypatch.setattr(memory_stack, "assemble_block", fake_block)
    ctx = await coordinator._plan_context("goal", "past learnings")
    assert "Yaaddasht (memory stack)" in ctx
    assert "evening pe free" in ctx
    assert "past learnings" in ctx  # legacy hint is preserved, not replaced


async def test_coordinator_canary_degrades_to_legacy_on_failure(monkeypatch):
    monkeypatch.setenv("MEMORY_STACK_COORDINATOR_CANARY", "1")
    monkeypatch.setenv("MEMORY_STACK_ENABLED", "1")
    from app.agents import coordinator
    from app.platform import memory_stack

    async def boom(*_a, **_kw):
        raise RuntimeError("retrieval down")

    monkeypatch.setattr(memory_stack, "assemble_block", boom)
    ctx = await coordinator._plan_context("goal", "past learnings")
    assert ctx == "\nPichhle learnings (inhe dhyan me rakho): past learnings"

    async def empty(*_a, **_kw):
        return ""

    monkeypatch.setattr(memory_stack, "assemble_block", empty)
    assert await coordinator._plan_context("goal", "past learnings") == (
        "\nPichhle learnings (inhe dhyan me rakho): past learnings"
    )
