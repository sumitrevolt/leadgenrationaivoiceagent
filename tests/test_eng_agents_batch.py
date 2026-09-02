"""Tests for the eng-agents batch — code_reviewer · agent_recall · agent_checkpoints.

Pure-python: NO network / DB / real-LLM. free_ai.chat ko monkeypatch se fake karte
hain; vector store path ko fail karwa ke keyword-fallback verify karte; checkpoints
ko tmp data/ subtree pe chalate (path-guard + roundtrip).

Covers per module:
  code_reviewer  — JSON parse, prose-wrapped JSON, garbage→static, LLM-error→static,
                   empty input, dimensions default/normalize, enabled() flag.
  agent_recall   — record append, keyword recall (substring + token-overlap), empty
                   query, semantic-failure→keyword fallback, never-raise.
  agent_checkpoints — snapshot+rollback roundtrip, path-guard (traversal/absolute
                   refuse), list newest-first, missing ckpt, enabled() flag.
"""

import asyncio
import json

import pytest

from app.agents import agent_checkpoints, agent_recall, code_reviewer


# ----------------------------- shared env clean -------------------------------------- #
@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("CODE_REVIEWER", "AGENT_RECALL", "AGENT_CHECKPOINTS"):
        monkeypatch.delenv(k, raising=False)
    yield


# =============================== code_reviewer ======================================== #
def _fake_chat(reply: str):
    async def _chat(system, messages, max_tokens=90, temperature=0.6, **kw):
        return reply, "fake-provider"

    return _chat


def test_reviewer_parses_clean_json(monkeypatch):
    payload = {
        "findings": [
            {"dimension": "security", "severity": "high", "line": 12, "message": "sql injection"}
        ],
        "summary": "one high issue",
    }
    from app.voice_agent import free_ai

    monkeypatch.setattr(free_ai, "chat", _fake_chat(json.dumps(payload)))
    res = asyncio.run(code_reviewer.review("SELECT * FROM x"))
    assert res["ok"] is True
    assert res["summary"] == "one high issue"
    assert len(res["findings"]) == 1
    f = res["findings"][0]
    assert f["dimension"] == "security"
    assert f["severity"] == "high"
    assert f["line"] == 12
    assert res["dimensions"] == ["correctness", "security", "performance", "style", "tests"]


def test_reviewer_handles_prose_wrapped_and_fenced_json(monkeypatch):
    fenced = 'Here is my review:\n```json\n{"findings": [], "summary": "looks clean"}\n```\nDone.'
    from app.voice_agent import free_ai

    monkeypatch.setattr(free_ai, "chat", _fake_chat(fenced))
    res = asyncio.run(code_reviewer.review("def f(): return 1"))
    assert res["ok"] is True
    assert res["summary"] == "looks clean"
    assert res["findings"] == []


def test_reviewer_garbage_output_falls_back_static(monkeypatch):
    from app.voice_agent import free_ai

    monkeypatch.setattr(free_ai, "chat", _fake_chat("totally not json at all"))
    res = asyncio.run(code_reviewer.review("x=1"))
    # static result: never empty, never raise
    assert res["findings"]
    assert res["ok"] is False


def test_reviewer_llm_error_falls_back_static(monkeypatch):
    async def _boom(*a, **k):
        raise RuntimeError("provider down")

    from app.voice_agent import free_ai

    monkeypatch.setattr(free_ai, "chat", _boom)
    res = asyncio.run(code_reviewer.review("x=1"))
    assert res["ok"] is False
    assert res["findings"]  # static floor, not empty


def test_reviewer_normalizes_bad_severity_and_line(monkeypatch):
    payload = {
        "findings": [
            {"dimension": "STYLE", "severity": "CRITICAL", "line": "nope", "message": "x"},
        ],
        "summary": "s",
    }
    from app.voice_agent import free_ai

    monkeypatch.setattr(free_ai, "chat", _fake_chat(json.dumps(payload)))
    res = asyncio.run(code_reviewer.review("code", dimensions=["style"]))
    f = res["findings"][0]
    assert f["severity"] == "low"  # invalid severity -> low
    assert f["line"] is None  # non-int line -> None
    assert res["dimensions"] == ["style"]


def test_reviewer_empty_input_no_llm_call(monkeypatch):
    def _explode(*a, **k):
        raise AssertionError("LLM should not be called for empty input")

    from app.voice_agent import free_ai

    monkeypatch.setattr(free_ai, "chat", _explode)
    res = asyncio.run(code_reviewer.review("   "))
    assert res["ok"] is True
    assert res["findings"] == []


def test_reviewer_enabled_flag(monkeypatch):
    assert code_reviewer.enabled() is False
    monkeypatch.setenv("CODE_REVIEWER", "1")
    assert code_reviewer.enabled() is True


# =============================== agent_recall ========================================= #
@pytest.fixture
def _recall_store(tmp_path, monkeypatch):
    """Isolate the jsonl store to tmp + force semantic path to fail (keyword fallback)."""
    store = tmp_path / "agent_recall.jsonl"
    monkeypatch.setattr(agent_recall, "_STORE_PATH", store)
    # semantic recall unavailable -> exercises keyword fallback deterministically
    monkeypatch.setattr(agent_recall, "_semantic_recall", lambda q, k: None)
    return store


def test_recall_record_and_keyword_recall(_recall_store):
    agent_recall.record("decision", "Switched LLM primary to Mistral for reliability")
    agent_recall.record("decision", "Disabled WhatsApp auto-send to avoid ban")
    agent_recall.record("note", "Edge TTS prosody tuned for phone calls")

    hits = asyncio.run(agent_recall.recall("mistral llm primary"))
    assert hits
    assert "Mistral" in hits[0]["text"]
    assert hits[0]["score"] > 0
    assert hits[0]["kind"] == "decision"


def test_recall_substring_outranks(_recall_store):
    agent_recall.record("a", "ban risk whatsapp bulk")
    agent_recall.record("b", "something totally unrelated content")
    hits = asyncio.run(agent_recall.recall("whatsapp bulk", k=2))
    assert hits
    assert "whatsapp" in hits[0]["text"].lower()


def test_recall_empty_query_returns_empty(_recall_store):
    agent_recall.record("a", "anything")
    assert asyncio.run(agent_recall.recall("   ")) == []


def test_recall_no_store_never_raises(_recall_store):
    # store file doesn't exist yet -> empty, no raise
    assert asyncio.run(agent_recall.recall("query")) == []


def test_recall_record_empty_text_rejected(_recall_store):
    r = agent_recall.record("k", "   ")
    assert r["ok"] is False


def test_recall_semantic_failure_uses_keyword(tmp_path, monkeypatch):
    store = tmp_path / "agent_recall.jsonl"
    monkeypatch.setattr(agent_recall, "_STORE_PATH", store)

    def _boom(q, k):
        raise RuntimeError("chroma exploded")

    # _semantic_recall itself swallows, but ensure recall() is robust even if it raises
    monkeypatch.setattr(agent_recall, "_semantic_recall", _boom)
    agent_recall.record("d", "keyword fallback path works")
    hits = asyncio.run(agent_recall.recall("fallback path"))
    assert hits
    assert "fallback" in hits[0]["text"].lower()


def test_recall_enabled_flag(monkeypatch):
    assert agent_recall.enabled() is False
    monkeypatch.setenv("AGENT_RECALL", "yes")
    assert agent_recall.enabled() is True


# =============================== agent_checkpoints ==================================== #
@pytest.fixture
def _ckpt_env(tmp_path, monkeypatch):
    """Run checkpoints against a tmp repo-root with a real data/ subtree."""
    root = tmp_path
    (root / "data").mkdir()
    monkeypatch.setattr(agent_checkpoints, "_repo_root", lambda: root)
    monkeypatch.setattr(agent_checkpoints, "_CKPT_ROOT", root / "data" / "agent_checkpoints")
    return root


def test_checkpoint_snapshot_and_rollback_roundtrip(_ckpt_env):
    root = _ckpt_env
    target = root / "data" / "mutable.txt"
    target.write_text("original", encoding="utf-8")

    snap = agent_checkpoints.snapshot(["data/mutable.txt"], label="before edit")
    assert snap["ok"] is True
    assert "data/mutable.txt" in snap["paths"]
    cid = snap["id"]

    # agent "mutates"
    target.write_text("CORRUPTED", encoding="utf-8")
    assert target.read_text(encoding="utf-8") == "CORRUPTED"

    rb = agent_checkpoints.rollback(cid)
    assert rb["ok"] is True
    assert "data/mutable.txt" in rb["restored"]
    assert target.read_text(encoding="utf-8") == "original"


def test_checkpoint_rejects_traversal_and_absolute(_ckpt_env):
    snap = agent_checkpoints.snapshot(
        ["../../etc/passwd", "/etc/passwd", "C:/Windows/system32/x", "secrets/.env"]
    )
    # none are under data/ or app/ -> nothing snapshotted
    assert snap["ok"] is False
    assert snap.get("skipped")


def test_checkpoint_refuses_outside_allowed_prefix(_ckpt_env):
    root = _ckpt_env
    (root / "config.txt").write_text("x", encoding="utf-8")  # top-level, not data/ or app/
    snap = agent_checkpoints.snapshot(["config.txt"])
    assert snap["ok"] is False


def test_checkpoint_list_newest_first(_ckpt_env):
    root = _ckpt_env
    (root / "data" / "a.txt").write_text("a", encoding="utf-8")
    (root / "data" / "b.txt").write_text("b", encoding="utf-8")
    s1 = agent_checkpoints.snapshot(["data/a.txt"], label="first")
    s2 = agent_checkpoints.snapshot(["data/b.txt"], label="second")
    lst = agent_checkpoints.list_checkpoints()
    ids = [c["id"] for c in lst]
    assert s1["id"] in ids and s2["id"] in ids
    # newest-first
    assert lst[0]["at"] >= lst[-1]["at"]


def test_rollback_missing_checkpoint(_ckpt_env):
    rb = agent_checkpoints.rollback("ck-doesnotexist-000000")
    assert rb["ok"] is False
    assert rb["error"] == "checkpoint not found"


def test_rollback_invalid_id(_ckpt_env):
    assert agent_checkpoints.rollback("../escape")["ok"] is False
    assert agent_checkpoints.rollback("")["ok"] is False


def test_checkpoint_enabled_flag(monkeypatch):
    assert agent_checkpoints.enabled() is False
    monkeypatch.setenv("AGENT_CHECKPOINTS", "true")
    assert agent_checkpoints.enabled() is True
