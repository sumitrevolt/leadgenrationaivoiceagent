"""Contract for KB Qdrant point-id dedup (audit 2026-07-06 P0 fix).

Guards the fix for the re-ingest duplication / stale-grounding bug: the same
(namespace, text) chunk MUST map to the same Qdrant point id so a re-seed
OVERWRITES instead of accumulating a fresh random point. Any change that
reintroduces a random/non-deterministic id (the old `uuid.uuid4()`) fails here.
"""

import uuid

from app.voice_agent.knowledge_base import _kb_point_id


def test_same_namespace_and_text_is_stable():
    a = _kb_point_id("client:abc", "hamari pricing 1999 se shuru hoti hai")
    b = _kb_point_id("client:abc", "hamari pricing 1999 se shuru hoti hai")
    assert a == b  # re-ingest -> same point -> upsert overwrites (no duplicate)


def test_different_text_differs():
    a = _kb_point_id("client:abc", "pricing 1999")
    b = _kb_point_id("client:abc", "pricing 5999")  # content changed
    assert a != b  # changed content -> new point (old one overwritten on its own key)


def test_different_namespace_isolates():
    a = _kb_point_id("client:abc", "same text")
    b = _kb_point_id("client:xyz", "same text")
    assert a != b  # no cross-tenant point-id collision


def test_returns_valid_uuid_string():
    pid = _kb_point_id("solar_residential", "kuch bhi content")
    # Qdrant requires a valid UUID (or unsigned int) point id.
    assert str(uuid.UUID(pid)) == pid


def test_empty_inputs_do_not_crash():
    assert _kb_point_id("", "") == _kb_point_id("default", "")
    # falsy namespace normalises to "default" so it stays stable/deterministic.
