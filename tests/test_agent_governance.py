"""Tests — agent governance: per-tool permissions (OpenCode ACL), lifecycle
hooks (Hermes/Ruflo), custom agents (OpenCode/Kilo personas).

Pure-python, no network/DB. tmp_path data files via monkeypatch (skill_pack
pattern). asyncio.run for the one async helper (lifecycle_hooks.fire).
"""

from __future__ import annotations

import asyncio
import json
import os


# --------------------------------------------------------------------------- #
# 1) agent_permissions — per-tool ACL, fail-open vs fail-safe high-risk
# --------------------------------------------------------------------------- #
def _perms(monkeypatch, tmp_path):
    from app.agents import agent_permissions as ap

    monkeypatch.setattr(ap, "_DATA_FILE", str(tmp_path / "perms.json"))
    return ap


def test_permissions_flag_gate(monkeypatch, tmp_path):
    ap = _perms(monkeypatch, tmp_path)
    monkeypatch.delenv("AGENT_PERMISSIONS", raising=False)
    assert ap.enabled() is False
    # OFF → allow-all even for high-risk (zero behaviour change)
    assert ap.can("swara", "place_call") is True
    assert ap.can("rohan", "spend") is True
    monkeypatch.setenv("AGENT_PERMISSIONS", "1")
    assert ap.enabled() is True


def test_permissions_fail_open_vs_high_risk(monkeypatch, tmp_path):
    ap = _perms(monkeypatch, tmp_path)
    monkeypatch.setenv("AGENT_PERMISSIONS", "1")
    # unset normal tool → fail-OPEN (allow)
    assert ap.can("rohan", "send_email") is True
    assert ap.can("rohan", "write_code") is True
    # unset HIGH_RISK tool → fail-SAFE (deny)
    assert ap.can("rohan", "spend") is False
    assert ap.can("rohan", "place_call") is False
    assert ap.can("rohan", "send_whatsapp") is False


def test_permissions_set_and_lookup(monkeypatch, tmp_path):
    ap = _perms(monkeypatch, tmp_path)
    monkeypatch.setenv("AGENT_PERMISSIONS", "1")
    # explicit allow on a high-risk tool overrides fail-safe
    r = ap.set_permission("Swara", "place_call", "allow")
    assert r["ok"] and r["agent"] == "swara"
    assert ap.can("swara", "place_call") is True
    # explicit deny on a normal tool overrides fail-open
    assert ap.set_permission("rohan", "send_email", "deny")["ok"]
    assert ap.can("rohan", "send_email") is False
    # persisted to json
    data = json.loads((tmp_path / "perms.json").read_text(encoding="utf-8"))
    assert data["swara"]["place_call"] == "allow"
    # list_permissions surfaces matrix + meta
    lp = ap.list_permissions()
    assert lp["enabled"] is True and "spend" in lp["high_risk"]
    assert lp["permissions"]["rohan"]["send_email"] == "deny"


def test_permissions_set_validation(monkeypatch, tmp_path):
    ap = _perms(monkeypatch, tmp_path)
    assert ap.set_permission("", "spend", "allow")["ok"] is False
    assert ap.set_permission("x", "not_a_tool", "allow")["ok"] is False
    assert ap.set_permission("x", "spend", "maybe")["ok"] is False


# --------------------------------------------------------------------------- #
# 2) lifecycle_hooks — register/list/fire (log never network, bounded)
# --------------------------------------------------------------------------- #
def _hooks(monkeypatch, tmp_path):
    from app.agents import lifecycle_hooks as lh

    monkeypatch.setattr(lh, "_DATA_FILE", str(tmp_path / "hooks.json"))
    # These tests exercise register/fire MECHANICS, not the SSRF guard (covered in
    # test_lifecycle_hooks_ssrf.py). Stub the guard permissive so example.com targets
    # don't get rejected by offline DNS-fail (fail-safe reject is correct in prod).
    monkeypatch.setattr(lh, "_is_safe_target", lambda u: (True, ""))
    return lh


def test_hooks_flag_gate(monkeypatch, tmp_path):
    lh = _hooks(monkeypatch, tmp_path)
    monkeypatch.delenv("AGENT_HOOKS", raising=False)
    assert lh.enabled() is False
    monkeypatch.setenv("AGENT_HOOKS", "1")
    assert lh.enabled() is True


def test_hooks_register_validation(monkeypatch, tmp_path):
    lh = _hooks(monkeypatch, tmp_path)
    assert lh.register("bad_event", "n", "log")["ok"] is False
    assert lh.register("pre_task", "", "log")["ok"] is False
    assert lh.register("pre_task", "n", "bad_type")["ok"] is False
    # network types need a target
    assert lh.register("pre_task", "n", "ntfy")["ok"] is False
    assert lh.register("post_task", "n", "webhook")["ok"] is False


def test_hooks_register_and_list(monkeypatch, tmp_path):
    lh = _hooks(monkeypatch, tmp_path)
    assert lh.register("pre_task", "log-it", "log")["ok"]
    assert lh.register("on_error", "ping", "ntfy", "https://ntfy.example/topic")["ok"]
    lst = lh.list_hooks()
    assert lst["hooks"] and {h["name"] for h in lst["hooks"]} == {"log-it", "ping"}
    # persisted
    data = json.loads((tmp_path / "hooks.json").read_text(encoding="utf-8"))
    assert len(data) == 2


def test_hooks_fire_log_only_no_network(monkeypatch, tmp_path):
    lh = _hooks(monkeypatch, tmp_path)
    lh.register("pre_task", "log-it", "log")

    # if a network hook ever tried to POST, this would explode the test
    async def _boom(url, payload):
        raise AssertionError("log hook must not hit network")

    monkeypatch.setattr(lh, "_post", _boom)
    res = asyncio.run(lh.fire("pre_task", {"task": "score_lead"}))
    assert res["ok"] and res["fired"] == 1
    assert res["results"][0] == {"name": "log-it", "type": "log", "ok": True}
    # non-matching event → nothing fired
    assert asyncio.run(lh.fire("post_task", {}))["fired"] == 0


def test_hooks_fire_network_bounded_best_effort(monkeypatch, tmp_path):
    lh = _hooks(monkeypatch, tmp_path)
    lh.register("post_task", "wh", "webhook", "https://example.com/hook")
    calls = {}

    async def _ok(url, payload):
        calls["url"] = url
        calls["payload"] = payload
        return True

    monkeypatch.setattr(lh, "_post", _ok)
    res = asyncio.run(lh.fire("post_task", {"task": "x"}))
    assert res["results"][0]["ok"] is True
    assert calls["url"] == "https://example.com/hook"

    # _post raising is swallowed → ok:False, never propagates
    async def _raise(url, payload):
        raise RuntimeError("down")

    monkeypatch.setattr(lh, "_post", _raise)
    res2 = asyncio.run(lh.fire("post_task", {"task": "x"}))
    assert res2["ok"] and res2["results"][0]["ok"] is False


# --------------------------------------------------------------------------- #
# 3) custom_agents — data-defined personas, validate + register + roster
# --------------------------------------------------------------------------- #
def _custom(monkeypatch, tmp_path):
    from app.agents import custom_agents as ca

    monkeypatch.setattr(ca, "_DATA_DIR", str(tmp_path / "custom_agents"))
    ca._cache["at"] = 0.0
    ca._cache["agents"] = []
    return ca


def test_custom_agents_flag_gate(monkeypatch, tmp_path):
    ca = _custom(monkeypatch, tmp_path)
    monkeypatch.delenv("CUSTOM_AGENTS", raising=False)
    assert ca.enabled() is False
    monkeypatch.setenv("CUSTOM_AGENTS", "1")
    assert ca.enabled() is True


def test_custom_agents_register_and_get(monkeypatch, tmp_path):
    ca = _custom(monkeypatch, tmp_path)
    spec = {
        "name": "Harsh Retention",
        "role": "Retention specialist",
        "system_prompt": "Churned customers ko win-back karo, Hinglish me.",
        "allowed_tools": ["send_email", "publish"],
        "product": "marketing",
    }
    r = ca.register(spec)
    assert r["ok"] and r["name"] == "harshretention"
    # file written in the data dir (path-escape-safe slug)
    assert os.path.dirname(os.path.abspath(r["path"])) == os.path.abspath(ca._DATA_DIR)
    got = ca.get("harshretention")
    assert got and got["role"] == "Retention specialist"
    assert got["allowed_tools"] == ["send_email", "publish"]
    assert ca.get("nope") is None
    agents = ca.list_custom_agents()
    assert len(agents) == 1 and agents[0]["name"] == "harshretention"


def test_custom_agents_register_validation(monkeypatch, tmp_path):
    ca = _custom(monkeypatch, tmp_path)
    assert ca.register("not a dict")["ok"] is False
    assert ca.register({"name": "x"})["ok"] is False  # missing role/system_prompt
    assert ca.register({"name": "!!!", "role": "r", "system_prompt": "p"})["ok"] is False
    # script block
    bad = {"name": "x", "role": "r", "system_prompt": "<script>alert(1)</script>"}
    assert ca.register(bad)["ok"] is False


def test_custom_agents_merged_roster(monkeypatch, tmp_path):
    ca = _custom(monkeypatch, tmp_path)
    ca.register({"name": "harsh", "role": "Retention", "system_prompt": "win-back karo"})
    roster = ca.merged_roster()
    assert "note" in roster and "team.py" in roster["note"]
    assert len(roster["custom_agents"]) == 1
    assert roster["custom_agents"][0]["name"] == "harsh"


# --------------------------------------------------------------------------- #
# 4) router — wiring sanity (routes exist on the prefix, no mount needed)
# --------------------------------------------------------------------------- #
def test_router_routes_present():
    from app.api import agent_governance as ag

    paths = {r.path for r in ag.router.routes}
    assert {"/permissions", "/hooks", "/custom-agents"} <= paths
    # tags set as required
    assert any("AgentGovernance" in (getattr(r, "tags", []) or []) for r in ag.router.routes)
