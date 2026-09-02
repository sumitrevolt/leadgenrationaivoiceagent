"""Desktop-app registry contract — doc JSON is the source, hub projects it read-only.

Covers: registry JSON validity, required per-app fields, buzzlock TOOL tokens
matching scripts/buzzlock.py TOOLS, hub snapshot inclusion (inert-safe when
flag OFF), and never-raise degradation on missing/invalid/malformed input.
"""

from __future__ import annotations

import json

from app.platform import coordination_desktop_registry as reg
from app.platform.coordination_hub_auth import hub_enabled

_REQUIRED_KEYS = (
    "id",
    "name",
    "project",
    "worktree",
    "channel",
    "buzzlock_tool",
    "harness",
    "headless_cli",
    "heartbeat",
    "status",
)


def _buzzlock_tools() -> set[str]:
    """Parse scripts/buzzlock.py TOOLS tuple without importing the script."""
    import ast
    from pathlib import Path

    src = Path("scripts/buzzlock.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "TOOLS":
                    val = ast.literal_eval(node.value)
                    return set(val)
    return set()


def _strings(obj) -> list[str]:
    out: list[str] = []
    if isinstance(obj, dict):
        for v in obj.values():
            out.extend(_strings(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_strings(v))
    elif isinstance(obj, str):
        out.append(obj)
    return out


def test_registry_loads_with_all_required_fields():
    out = reg.load_registry()
    assert out["ok"] is True
    assert out["version"] == 1
    assert len(out["apps"]) == 6
    ids = [a["id"] for a in out["apps"]]
    assert len(ids) == len(set(ids)), "app ids must be unique"
    for app in out["apps"]:
        for key in _REQUIRED_KEYS:
            assert key in app, f"app {app.get('id')} missing {key}"
    assert {a["id"] for a in out["apps"]} == {
        "freebuff",
        "android",
        "opencode",
        "cursor",
        "hermes",
        "buzz",
    }


def test_registry_slice_shape():
    sl = reg.registry_slice()
    assert sl["ok"] is True
    assert sl["enabled"] is True
    assert isinstance(sl["apps"], list) and len(sl["apps"]) == 6
    assert "Read-only projection" in sl["note"]
    assert "error" in sl


def test_buzzlock_tokens_match_registry():
    enrolled = _buzzlock_tools()
    assert {"CURSOR", "OPENCODE", "FREEBUFF"} <= enrolled
    for app in reg.load_registry()["apps"]:
        tok = app.get("buzzlock_tool")
        if tok:
            assert tok in enrolled, f"registry buzzlock_tool {tok} not in scripts/buzzlock.py TOOLS"


def test_registry_contains_no_secret_values():
    """No secret VALUES (env-var NAME references like COORD_HUB_BUZZ_SECRET are fine)."""
    data = reg.load_registry()
    for s in _strings(data):
        # credential-shaped: opaque, long, no spaces (keys/tokens/passwords)
        if len(s) >= 40 and " " not in s:
            raise AssertionError(f"credential-shaped value in registry: {s[:16]}...")
    for app in data["apps"]:
        for key in ("api_key", "password", "private_key"):
            assert key not in app
        v = app.get("buzzlock_tool")
        assert v is None or (v.isupper() and v.isalpha())


def test_hub_snapshot_includes_registry_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("COORDINATION_HUB_ENABLED", "1")
    from app.platform import coordination_hub as hub
    from app.platform import coordination_hub_auth as auth_mod
    from app.platform import coordination_hub_events as events_mod

    root = tmp_path / "coordination_hub"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(events_mod, "_ROOT", str(root))
    monkeypatch.setattr(events_mod, "_EVENTS", str(root / "events.jsonl"))
    monkeypatch.setattr(events_mod, "_PRESENCE", str(root / "presence.json"))
    monkeypatch.setattr(events_mod, "_PRESENCE_TMP", str(root / "presence.json.tmp"))
    monkeypatch.setattr(auth_mod, "_HUB_ROOT", str(root))
    monkeypatch.setattr(auth_mod, "_NONCE_FILE", str(root / "nonce_fps.jsonl"))
    monkeypatch.setattr(hub, "probe_git", lambda: {"ok": False})

    snap = hub.snapshot(include_git=True)
    assert snap["enabled"] is True
    dr = snap["desktop_registry"]
    assert dr["ok"] is True
    assert dr["enabled"] is True
    assert len(dr["apps"]) == 6


def test_hub_snapshot_registry_inert_when_flag_off(monkeypatch):
    monkeypatch.delenv("COORDINATION_HUB_ENABLED", raising=False)
    from app.platform import coordination_hub as hub

    assert hub_enabled() is False
    snap = hub.snapshot(include_git=False)
    assert snap["enabled"] is False
    dr = snap["desktop_registry"]
    assert dr["ok"] is True
    assert dr["enabled"] is False
    assert dr["apps"] == []


def test_loader_never_raises_on_missing(tmp_path):
    out = reg.load_registry(tmp_path / "missing.json")
    assert out["ok"] is False
    assert out["error"] == "registry_unreadable"
    assert out["apps"] == []


def test_loader_never_raises_on_invalid_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    out = reg.load_registry(p)
    assert out["ok"] is False
    assert out["error"] == "registry_invalid_json"
    assert out["apps"] == []


def _valid_app_row(row_id: str) -> dict:
    return {
        "id": row_id,
        "name": "Test App",
        "project": "test project",
        "worktree": "own worktree",
        "channel": "#dev",
        "buzzlock_tool": None,
        "harness": "headless",
        "headless_cli": True,
        "heartbeat": "none",
        "status": "registered",
    }


def test_loader_filters_malformed_rows(tmp_path):
    p = tmp_path / "registry.json"
    good = _valid_app_row("ok_app")
    missing_keys = _valid_app_row("missing_keys")
    del missing_keys["harness"]
    p.write_text(
        json.dumps({"version": 1, "apps": [good, missing_keys, "not-a-dict"]}),
        encoding="utf-8",
    )
    out = reg.load_registry(p)
    assert out["ok"] is True
    assert [a["id"] for a in out["apps"]] == ["ok_app"]


def test_loader_never_raises_on_missing_apps_key(tmp_path):
    p = tmp_path / "registry.json"
    p.write_text(json.dumps({"version": 1}), encoding="utf-8")
    out = reg.load_registry(p)
    assert out["ok"] is False
    assert out["error"] == "registry_missing_apps"
    assert out["apps"] == []
