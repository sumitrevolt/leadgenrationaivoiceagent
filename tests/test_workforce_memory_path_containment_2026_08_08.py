"""CodeQL #578 path-containment barrier regression (2026-08-08).

The canonical barrier lives in app/platform/workforce_memory.py `_contained_under`
+ `_agent_dir`: every path that reaches an open() funnels through `_agent_dir`,
which proves the resolved target stays strictly below `_root()`. On rejection it
collapses to `_root()` (never-raise) and the destructive/write callers
(`_append_entry`, `purge_agent`) additionally refuse to act ON the root itself.

These tests assert: no file is ever written outside the memory root, adversarial
ids return their documented safe-default (False / {"ok": False} / []) without
raising, and prefix-collision / symlink-escape are contained.
"""

from __future__ import annotations

import os
import re

import pytest


@pytest.fixture()
def wfm_env(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKFORCE_MEMORY", "1")
    monkeypatch.setenv("WORKFORCE_MEMORY_DIR", str(tmp_path / "wfm"))
    monkeypatch.setenv("WORKFORCE_MEMORY_RECALL_TIMEOUT_MS", "2000")
    monkeypatch.delenv("MEMORY_VAULT", raising=False)
    from app.platform import workforce_memory as wm

    for k in list(wm._STATS):
        wm._STATS[k] = 0
    yield wm


TRAVERSALS = [
    "../../etc/passwd",
    "swara/../../etc",
    "/etc/passwd",
    "C:\\windows\\evil",
    "..",
    "swara/..",
    "a/b",
    "a\\b",
    "..%2fetc%2fpasswd",
    "a.b",
    ".",
    " ",
    "",
    "-x",
    "A" * 41,
    "guru/../../..",
]


def _entry(agent_id: str = "swara") -> dict:
    return {
        "id": "x",
        "agent_id": agent_id,
        "tenant_id": "platform",
        "layer": "l1_atom",
        "asset": "chat",
        "content": "x",
        "at": "2026-08-08T00:00:00Z",
    }


def _listdir_under_root(root: str) -> list[str]:
    if not os.path.isdir(root):
        return []
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            out.append(os.path.relpath(os.path.join(dirpath, f), root))
    return out


# --- positive --------------------------------------------------------------


def test_valid_agent_dir_stays_under_root(wfm_env):
    wm = wfm_env
    for agent in ("swara", "isa_2", "guru"):
        d = wm._agent_dir(agent)
        assert wm._contained_under(wm._root(), d)
        assert os.path.normpath(d).startswith(os.path.normpath(wm._root()))
    ten = wm._agent_dir("swara", "tenant-A")
    assert wm._contained_under(wm._root(), ten)
    assert re.fullmatch(r"[0-9a-f]{16}", os.path.basename(ten))


def test_contained_under_unit(wfm_env, tmp_path):
    wm = wfm_env
    root = wm._root()
    assert wm._contained_under(root, os.path.join(root, "swara", "entries.jsonl"))
    assert wm._contained_under(root, os.path.join(root, "swara", "tenants", "a" * 16, "refs"))
    assert not wm._contained_under(root, root)  # equal == not strictly below
    assert not wm._contained_under(root, os.path.join(root, "..", "evil"))
    assert not wm._contained_under(root, os.path.join(root, "swara", "..", "..", "evil"))


# --- adversarial path building --------------------------------------------


def test_agent_dir_collapses_on_traversal(wfm_env):
    wm = wfm_env
    root = wm._root()
    for payload in TRAVERSALS:
        d = wm._agent_dir(payload)
        assert os.path.normpath(d) == os.path.normpath(root) or wm._contained_under(root, d), (
            f"_agent_dir({payload!r}) must collapse to root or stay contained"
        )


def test_entries_path_never_escapes_root(wfm_env):
    wm = wfm_env
    root = wm._root()
    for payload in TRAVERSALS:
        p = wm._entries_path(payload)
        assert wm._contained_under(root, p) or os.path.normpath(p) == os.path.normpath(
            os.path.join(root, "entries.jsonl")
        ), f"_entries_path({payload!r}) escaped root: {p!r}"


# --- no write outside root + safe defaults --------------------------------


def test_append_entry_adversarial_no_escape(wfm_env):
    wm = wfm_env
    before = dict.fromkeys(_listdir_under_root(wm._root()))
    for payload in TRAVERSALS:
        assert wm._append_entry(payload, _entry(payload)) is False, (
            f"_append_entry should refuse {payload!r}"
        )
    after = _listdir_under_root(wm._root())
    assert set(after) == set(before)  # nothing new created at all
    root = wm._root()
    if os.path.isdir(root):
        for rel in after:
            assert not os.path.isabs(rel)
            assert ".." not in rel.split(os.sep)


def test_append_entry_valid_agent_writes_inside_root(wfm_env):
    wm = wfm_env
    assert wm._append_entry("swara", _entry()) is True
    written = _listdir_under_root(wm._root())
    assert "swara" + os.sep + "entries.jsonl" in written
    for rel in written:
        assert ".." not in rel.split(os.sep)


def test_remember_adversarial_safe_default(wfm_env):
    wm = wfm_env
    root = wm._root()
    for payload in TRAVERSALS:
        out = wm.remember(payload, "secret content", tenant_id="../evil")
        assert out.get("ok") is False
        assert out.get("deferred") is not True  # real refusal, not a governance deferral
    if os.path.isdir(root):
        for rel in _listdir_under_root(root):
            assert ".." not in rel.split(os.sep)


def test_recall_adversarial_never_raises(wfm_env):
    wm = wfm_env
    for payload in TRAVERSALS:
        assert wm.recall(payload) == []
        assert wm.recall_brief(payload) == ""
        assert wm.list_entries(payload) == []
        assert wm.purge_agent(payload)["ok"] is False


# --- prefix collision -------------------------------------------------------


def test_prefix_collision_isolated(wfm_env):
    wm = wfm_env
    # "swara_evil" is a VALID agent id but must map to its own dir — never the
    # same dir as "swara", and never a containment violation.
    assert wm._agent_dir("swara") != wm._agent_dir("swara_evil")
    assert wm._append_entry("swara", _entry()) is True
    assert wm._append_entry("swara_evil", _entry("swara_evil")) is True
    entries = _listdir_under_root(wm._root())
    assert "swara" + os.sep + "entries.jsonl" in entries
    assert "swara_evil" + os.sep + "entries.jsonl" in entries
    assert wm.recall("swara") and wm.recall("swara_evil")
    # recalling swara never sees swara_evil rows
    assert all(r.get("agent_id") == "swara" for r in wm.recall("swara", limit=50))


# --- symlink escape ---------------------------------------------------------


def test_symlink_escape_blocked(wfm_env, tmp_path):
    wm = wfm_env
    outside = tmp_path / "outside"
    outside.mkdir()
    link = os.path.join(wm._root(), "evil_link")
    try:
        os.makedirs(wm._root(), exist_ok=True)
        os.symlink(str(outside), link, target_is_directory=True)
    except (OSError, NotImplementedError) as e:
        pytest.skip(f"symlink not creatable on this host ({e!r})")

    # _agent_dir resolves the symlink outside root -> collapses to root.
    assert os.path.normpath(wm._agent_dir("evil_link")) == os.path.normpath(wm._root())
    # Writes are refused entirely (never act on the root itself).
    assert wm._append_entry("evil_link", _entry("evil_link")) is False
    assert not (outside / "entries.jsonl").exists()
    # purge_agent must NOT wipe the memory root through the symlink.
    wm.remember("swara", "keep me")
    out = wm.purge_agent("evil_link")
    assert out["ok"] is False
    assert os.path.isdir(wm._root())
    assert wm.list_entries("swara")  # swara data untouched


# --- prune scan hardening ---------------------------------------------------


def test_prune_skips_foreign_names(wfm_env):
    wm = wfm_env
    root = wm._root()
    os.makedirs(os.path.join(root, "x.y"), exist_ok=True)  # invalid agent charset
    with open(os.path.join(root, "x.y", "entries.jsonl"), "w", encoding="utf-8") as f:
        f.write('{"layer":"l1_atom","at":"2026-01-01T00:00:00Z","content":"old"}\n')
    wm.remember("swara", "fresh", layer=wm.LAYER_L1, asset=wm.ASSET_CHAT)
    res = wm.prune_expired(dry_run=False)
    assert res["ok"] is True
    # The foreign dir is untouched by prune (it is not an agent scope).
    assert os.path.isfile(os.path.join(root, "x.y", "entries.jsonl"))
