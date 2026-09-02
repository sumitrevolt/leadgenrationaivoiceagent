"""Agent-memory admin — list_facts / purge_subject + their API endpoints.

The DPDP "right to be forgotten" is the bar these tests raise: purge MUST
actually call the backend purge function with the right subject, and the
returned count MUST flow back to the operator. Backend itself is mocked —
no real Qdrant required.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.voice_agent import agent_memory


# --------------------------------------------------------------------------- #
# Mock backend (mimics _NativeBackend surface — scroll/purge/embed/search/upsert)
# --------------------------------------------------------------------------- #
class _MockNativeBackend:
    def __init__(self) -> None:
        self.store: dict[str, list[dict[str, Any]]] = {}
        self.purge_calls: list[str] = []

    # _NativeBackend contract used by list_facts / purge_subject
    def scroll_subject(self, subject: str, limit: int) -> list[dict[str, Any]]:
        return list(self.store.get(subject, []))[: max(1, int(limit))]

    def purge_subject(self, subject: str) -> int:
        self.purge_calls.append(subject)
        return len(self.store.pop(subject, []))


@pytest.fixture(autouse=True)
def _enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_MEMORY", "1")


# --------------------------------------------------------------------------- #
# list_facts — operator inspection
# --------------------------------------------------------------------------- #
async def test_list_facts_returns_stored_facts() -> None:
    be = _MockNativeBackend()
    be.store["lead:LEAD-1"] = [
        {"fact": "wants morning slot", "ts": 1700000000.0},
        {"fact": "prefers WhatsApp", "ts": 1700000100.0},
    ]
    out = await agent_memory.list_facts("LEAD-1", scope="lead", backend=be)
    assert len(out) == 2
    assert out[0]["fact"] == "wants morning slot"


async def test_list_facts_empty_when_subject_unknown() -> None:
    be = _MockNativeBackend()
    out = await agent_memory.list_facts("LEAD-999", scope="lead", backend=be)
    assert out == []


async def test_list_facts_disabled_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    """AGENT_MEMORY unset -> empty list, never touches backend."""
    monkeypatch.delenv("AGENT_MEMORY", raising=False)
    be = _MockNativeBackend()
    be.store["lead:LEAD-1"] = [{"fact": "x", "ts": 0.0}]
    assert await agent_memory.list_facts("LEAD-1", scope="lead", backend=be) == []


async def test_list_facts_requires_subject_id() -> None:
    be = _MockNativeBackend()
    assert await agent_memory.list_facts("", scope="lead", backend=be) == []


# --------------------------------------------------------------------------- #
# purge_subject — DPDP right-to-be-forgotten
# --------------------------------------------------------------------------- #
async def test_purge_subject_actually_calls_backend_and_returns_count() -> None:
    be = _MockNativeBackend()
    be.store["lead:LEAD-7"] = [
        {"fact": "f1", "ts": 0.0},
        {"fact": "f2", "ts": 0.0},
        {"fact": "f3", "ts": 0.0},
    ]
    out = await agent_memory.purge_subject("LEAD-7", scope="lead", backend=be)
    assert out["purged"] == 3
    assert out["subject"] == "lead:LEAD-7"
    assert be.purge_calls == ["lead:LEAD-7"]
    # Storage actually cleared (DPDP requirement)
    assert "lead:LEAD-7" not in be.store


async def test_purge_subject_scope_isolation() -> None:
    """Purging lead:X must not touch client:X (different subjects)."""
    be = _MockNativeBackend()
    be.store["lead:X"] = [{"fact": "lead-fact", "ts": 0.0}]
    be.store["client:X"] = [{"fact": "client-fact", "ts": 0.0}]
    out = await agent_memory.purge_subject("X", scope="lead", backend=be)
    assert out["purged"] == 1
    assert "client:X" in be.store
    assert be.store["client:X"][0]["fact"] == "client-fact"


async def test_purge_disabled_returns_disabled_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_MEMORY", raising=False)
    be = _MockNativeBackend()
    out = await agent_memory.purge_subject("LEAD-1", scope="lead", backend=be)
    assert out == {"purged": 0, "disabled": True}
    assert be.purge_calls == []  # critical: must NOT touch backend when disabled


async def test_purge_no_subject_id_safe() -> None:
    be = _MockNativeBackend()
    out = await agent_memory.purge_subject("", scope="lead", backend=be)
    assert out["purged"] == 0
    assert out["error"] == "no_subject"


async def test_purge_handles_backend_exception_gracefully() -> None:
    class _Raises:
        def purge_subject(self, subject: str) -> int:
            raise RuntimeError("qdrant down")

    out = await agent_memory.purge_subject("LEAD-1", scope="lead", backend=_Raises())
    # _safe_thread swallows the exception and returns None -> {"purged": 0}.
    # The contract: never raises to the caller; returns structured zero.
    assert out["purged"] == 0
    assert "error" in out or "purged" in out
