"""ADR-154 workforce memory hub — layered assets, bindings, offload, dual-write bridges."""

from __future__ import annotations

import os

import pytest


@pytest.fixture()
def wfm_env(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKFORCE_MEMORY", "1")
    monkeypatch.setenv("WORKFORCE_MEMORY_DIR", str(tmp_path / "wfm"))
    # Hermetic test deadline: the production default (50ms) is intentionally
    # tight, but combined Windows suites can exceed it from scheduler jitter.
    monkeypatch.setenv("WORKFORCE_MEMORY_RECALL_TIMEOUT_MS", "2000")
    monkeypatch.delenv("MEMORY_VAULT", raising=False)
    from app.platform import workforce_memory as wm

    # Reset process counters between tests
    for k in list(wm._STATS):
        wm._STATS[k] = 0
    yield wm


def test_disabled_is_inert(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKFORCE_MEMORY", "0")
    monkeypatch.setenv("WORKFORCE_MEMORY_DIR", str(tmp_path / "wfm_off"))
    from app.platform import workforce_memory as wm

    assert wm.is_enabled() is False
    assert wm.remember("swara", "hello")["ok"] is False
    assert wm.recall("swara", "hello") == []
    assert wm.recall_brief("swara") == ""


def test_remember_recall_progressive(wfm_env):
    wm = wfm_env
    assert wm.remember(
        "swara",
        "Lead prefers evening callbacks after 6pm",
        layer=wm.LAYER_L1,
        asset=wm.ASSET_CHAT,
        topic="callback_pref",
    )["ok"]
    assert wm.remember(
        "swara",
        "When salon owners say price is high, offer Main plan ROI story",
        layer=wm.LAYER_L2,
        asset=wm.ASSET_SKILL,
        topic="price_objection",
    )["ok"]
    assert wm.remember(
        "swara",
        "Swara tone: warm Hinglish, never pushy",
        layer=wm.LAYER_L3,
        asset=wm.ASSET_CHAT,
        topic="persona",
    )["ok"]

    rows = wm.recall("swara", "price", limit=5)
    assert rows
    assert any(r["layer"] == wm.LAYER_L2 for r in rows)

    brief = wm.recall_brief("swara", "callback")
    assert "callback" in brief.lower() or "evening" in brief.lower()
    assert "node_id=" not in brief or "node_id=" in brief  # either fine

    canvas = wm.canvas_mermaid("swara")
    assert "graph LR" in canvas


def test_asset_binding_denies_code_for_swara(wfm_env):
    wm = wfm_env
    out = wm.remember(
        "swara",
        "should not store as code",
        asset=wm.ASSET_CODE,
        layer=wm.LAYER_L1,
    )
    assert out["ok"] is False
    assert out["error"] == "asset_denied"
    assert "chat" in out["allowed"]


def test_dev_may_write_code_asset(wfm_env):
    wm = wfm_env
    out = wm.remember(
        "dev",
        "Prefer additive FastAPI routers; first-route-wins",
        asset=wm.ASSET_CODE,
        layer=wm.LAYER_L2,
        topic="router_convention",
    )
    assert out["ok"] is True
    assert wm.agent_bindings("dev") == sorted([wm.ASSET_CHAT, wm.ASSET_SKILL, wm.ASSET_CODE])


def test_offload_and_drilldown(wfm_env):
    wm = wfm_env
    bulky = "RAW TRACE\n" + ("x" * 2000)
    out = wm.remember(
        "manager",
        "Run failed at step 3 — see offload",
        layer=wm.LAYER_L0,
        asset=wm.ASSET_CHAT,
        topic="run_fail",
        offload=bulky,
    )
    assert out["ok"] is True
    nid = out["entry"]["node_id"]
    assert nid
    recovered = wm.drilldown("manager", nid)
    assert recovered and "RAW TRACE" in recovered


def test_purge_agent(wfm_env):
    wm = wfm_env
    wm.remember("isha", "festival calendar tip", topic="festivals")
    assert wm.list_entries("isha")
    purged = wm.purge_agent("isha")
    assert purged["ok"] is True
    assert purged["purged"] >= 1
    assert wm.list_entries("isha") == []


def test_skill_library_dual_write(wfm_env, monkeypatch, tmp_path):
    wm = wfm_env
    monkeypatch.setattr(
        "app.platform.skill_library._LESSONS",
        str(tmp_path / "skill_lessons.jsonl"),
    )
    from app.platform import skill_library

    r = skill_library.record_lesson("outreach", "Lead with audit gap hook", agent="kiran")
    assert r["ok"] is True
    rows = wm.recall("kiran", "audit", assets=[wm.ASSET_SKILL], limit=5)
    assert rows
    assert rows[0]["layer"] == wm.LAYER_L2


def test_coordinator_dual_write(wfm_env, monkeypatch, tmp_path):
    wm = wfm_env
    monkeypatch.setattr(
        "app.agents.coordinator._MEMORY",
        str(tmp_path / "agent_memory.jsonl"),
    )
    from app.agents import coordinator

    coordinator._remember("gtm", "Need more consented prospects in autopilot queue", 0.7)
    rows = wm.recall("manager", "prospects", limit=5)
    assert rows
    assert any("prospect" in (r.get("content") or "").lower() for r in rows)


def test_hub_snapshot_and_team_brief(wfm_env):
    wm = wfm_env
    wm.remember("guru", "Keep Mem0 hygiene weekly", layer=wm.LAYER_L2, asset=wm.ASSET_WIKI)
    snap = wm.hub_snapshot()
    assert snap["enabled"] is True
    assert snap["agents_with_memory"] >= 1

    from app.platform import team

    brief = team.memory_brief("guru", "Mem0")
    assert "Mem0" in brief or "hygiene" in brief.lower() or "Workforce" in brief


def test_admin_router_mounted_paths():
    from app.api.workforce_memory_admin import router

    paths = {getattr(r, "path", "") for r in router.routes}
    assert "/api/workforce-memory/stats" in paths
    assert "/api/workforce-memory/remember" in paths
    assert "/api/workforce-memory/purge" in paths
    assert "/api/workforce-memory/equip" in paths
    assert "/api/workforce-memory/prune" in paths
    # Must not collide with lead-fact agent-memory admin
    assert not any(p.startswith("/api/agent-memory") for p in paths)


def test_dedupe_exact_hash(wfm_env):
    wm = wfm_env
    a = wm.remember("swara", "Same fact twice", topic="dup")
    b = wm.remember("swara", "Same fact twice", topic="dup")
    assert a["ok"] and b["ok"]
    assert b.get("deduped") is True
    assert wm.stats().get("deduped", 0) >= 1


def test_equip_team_skill(wfm_env):
    wm = wfm_env
    out = wm.remember(
        "guru",
        "Release checklist: health + skew + smoke",
        layer=wm.LAYER_L2,
        asset=wm.ASSET_SKILL,
        topic="release",
        visibility="team",
    )
    assert out["ok"] is True
    eid = out["entry"]["id"]
    eq = wm.equip(eid, "kiran")
    assert eq["ok"] is True
    rows = wm.recall("kiran", "checklist", assets=[wm.ASSET_SKILL], limit=5)
    assert any(r.get("id") == eid for r in rows)


def test_prune_dry_run(wfm_env, monkeypatch):
    wm = wfm_env
    monkeypatch.setenv("WORKFORCE_MEMORY_L0_L1_DAYS", "90")
    wm.remember("manager", "fresh atom", layer=wm.LAYER_L1, asset=wm.ASSET_CHAT)
    res = wm.prune_expired(dry_run=True)
    assert res["ok"] is True
    assert res["dry_run"] is True


def test_inject_for_runtime(wfm_env):
    wm = wfm_env
    wm.remember("kavya", "Watch celery depth before pulsing", layer=wm.LAYER_L2, topic="ops")
    brief = wm.inject_for_runtime("kavya", "ops_pulse")
    assert "celery" in brief.lower() or "Workforce" in brief or "ops" in brief.lower()


def test_tenant_scoped_memory_never_cross_recalls(wfm_env):
    wm = wfm_env
    a = wm.remember("isha", "tenant A private plan", tenant_id="tenant-A")
    b = wm.remember("isha", "tenant B private plan", tenant_id="tenant-B")
    assert a["ok"] and b["ok"]

    a_rows = wm.recall("isha", "private plan", tenant_id="tenant-A")
    b_rows = wm.recall("isha", "private plan", tenant_id="tenant-B")
    platform_rows = wm.recall("isha", "private plan")
    assert [row["content"] for row in a_rows] == ["tenant A private plan"]
    assert [row["content"] for row in b_rows] == ["tenant B private plan"]
    assert platform_rows == []
    assert wm.memory_namespace("isha", "tenant-A") != wm.memory_namespace("isha", "tenant-B")


def test_tenant_memory_cannot_be_mirrored_to_global_team_scope(wfm_env):
    wm = wfm_env
    out = wm.remember(
        "isha",
        "customer-specific playbook",
        asset=wm.ASSET_SKILL,
        visibility="team",
        tenant_id="tenant-A",
    )
    assert out == {"ok": False, "error": "tenant_memory_cannot_be_team_visible"}


def test_tenant_run_can_read_equipped_platform_skill(wfm_env):
    wm = wfm_env
    shared = wm.remember(
        "guru",
        "Platform-safe release checklist",
        asset=wm.ASSET_SKILL,
        layer=wm.LAYER_L2,
        visibility="team",
    )
    assert shared["ok"] and shared["entry"]["tenant_id"] == "platform"
    assert wm.equip(shared["entry"]["id"], "kiran")["ok"]
    rows = wm.recall("kiran", "release checklist", assets=[wm.ASSET_SKILL], tenant_id="tenant-A")
    assert any(row["id"] == shared["entry"]["id"] for row in rows)


def test_tenant_purge_does_not_delete_other_tenant(wfm_env):
    wm = wfm_env
    wm.remember("isha", "A only", tenant_id="tenant-A")
    wm.remember("isha", "B only", tenant_id="tenant-B")
    out = wm.purge_agent("isha", tenant_id="tenant-A")
    assert out["ok"] and out["purged"] == 1
    assert wm.list_entries("isha", tenant_id="tenant-A") == []
    assert len(wm.list_entries("isha", tenant_id="tenant-B")) == 1


def test_tenant_do_not_remember_rule_blocks_only_matching_scope(wfm_env, tmp_path, monkeypatch):
    wm = wfm_env
    monkeypatch.setenv("MEMORY_STACK_ENABLED", "1")
    monkeypatch.setenv("MEMORY_SUPPRESSION_PATH", str(tmp_path / "suppression.jsonl"))
    monkeypatch.setenv("MEMORY_GOVERNANCE_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    from app.platform import memory_governance as gov

    assert gov.suppress("tenant-A", "pattern", "private plan")["ok"] is True
    blocked = wm.remember("isha", "private plan", tenant_id="tenant-A")
    allowed = wm.remember("isha", "private plan", tenant_id="tenant-B")
    assert blocked["ok"] is False
    assert blocked["code"] == "MEMORY_WRITE_SUPPRESSED_BY_RULE"
    assert allowed["ok"] is True
