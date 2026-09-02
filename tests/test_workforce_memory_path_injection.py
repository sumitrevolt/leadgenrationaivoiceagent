"""CodeQL py/path-injection regression (alerts #572-#575, workforce_memory).

The four alerts flagged "uncontrolled data used in path expression":

  #572/#573  _append_entry()  -- agent_id lands RAW in os.path.join sinks.
  #574       offload_ref()    -- tenant_id flows toward a join.
  #575       hub_snapshot()   -- os.listdir() names joined read-only.

Defences under test here:
  * agent_id is charset-restricted by _safe_agent (^[a-z][a-z0-9_]{0,39}$), so
    no separator / dot / dot-dot can ever reach a path component.
  * _append_entry now re-validates at the sink (defense in depth).
  * tenant_id is never interpolated raw: _agent_dir uses _tenant_key() (sha256
    hexdigest, 16 chars) as the only tenant path component.
  * hub_snapshot skips root-level names that are not agent ids.
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
    "..",
    "swara/..",
    "a/b",
    "a.b",
    "a\\b",
    "A" * 41,
    " ",
    "-x",
    "",
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


def test_safe_agent_rejects_traversal_payloads(wfm_env):
    wm = wfm_env
    for payload in TRAVERSALS:
        assert wm._safe_agent(payload) is None, f"_safe_agent should reject {payload!r}"
    assert wm._safe_agent("swara") == "swara"
    assert wm._safe_agent("isa_2") == "isa_2"


def test_append_entry_rejects_bad_agent_at_sink(wfm_env):
    wm = wfm_env
    for payload in TRAVERSALS:
        assert wm._append_entry(payload, _entry(payload)) is False
    # Nothing may have been created under the memory root.
    root = wm._root()
    assert not os.path.exists(root) or os.listdir(root) == []


def test_append_entry_valid_agent_still_writes(wfm_env):
    wm = wfm_env
    assert wm._append_entry("swara", _entry()) is True
    assert os.path.isfile(os.path.join(wm._root(), "swara", "entries.jsonl"))


def test_tenant_only_ever_enters_path_as_hash(wfm_env):
    wm = wfm_env
    # "../../etc" is a legal tenant *string* (hashed, never interpolated).
    assert wm._safe_tenant("../../etc") == "../../etc"
    assert wm._append_entry("swara", _entry(), tenant_id="../../etc") is True
    tenants_dir = os.path.join(wm._root(), "swara", "tenants")
    scopes = os.listdir(tenants_dir)
    assert len(scopes) == 1
    scope = scopes[0]
    # 16-char sha256 hexdigest — safe charset, no separators, no dot-dot.
    assert re.fullmatch(r"[0-9a-f]{16}", scope), f"tenant scope must be a hash, got {scope!r}"
    assert ".." not in scope
    assert os.path.isfile(os.path.join(tenants_dir, scope, "entries.jsonl"))


def test_offload_ref_tenant_hashed(wfm_env):
    wm = wfm_env
    node = wm.offload_ref("swara", "bulky evidence", tenant_id="../evil")
    assert node
    refs_dir = os.path.join(wm._root(), "swara", "tenants")
    scope = os.listdir(refs_dir)[0]
    assert re.fullmatch(r"[0-9a-f]{16}", scope)
    ref_file = os.path.join(refs_dir, scope, "refs", f"{node}.md")
    assert os.path.isfile(ref_file)
    assert ".." not in os.path.relpath(ref_file, wm._root())


def test_hub_snapshot_ignores_foreign_root_entries(wfm_env):
    wm = wfm_env
    assert wm.remember("swara", "a valid memory", topic="t")["ok"] is True
    # Plant a directory whose name is NOT a valid agent id (dot = outside charset).
    foreign = os.path.join(wm._root(), "x.y")
    os.makedirs(foreign, exist_ok=True)
    with open(os.path.join(foreign, "entries.jsonl"), "w", encoding="utf-8") as f:
        f.write('{"id":"z"}\n')

    out = wm.hub_snapshot(max_agents=8)
    ids = [b["agent_id"] for b in out.get("sample", [])]
    assert "swara" in ids
    assert "x.y" not in ids
