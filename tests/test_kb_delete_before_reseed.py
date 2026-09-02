"""Contract for KB delete-before-reseed (audit 2026-07-06 P1 — the actual stale-grounding fix).

The deterministic point-id dedup (test_kb_point_id) only collapses *byte-identical*
re-ingests. When a client's website content CHANGES, the new text hashes differently
so the old chunk is orphaned, not overwritten. `add_documents(..., replace_source=True)`
must drop the (namespace, source)'s OLD chunks before adding, so the voice agent stops
quoting stale content (e.g. old pricing). Runs on the pure-python keyword backend
(`prefer_chroma=False`), which shares the facade delete path.
"""

from app.voice_agent.knowledge_base import KnowledgeBase, _KeywordIndex


def _kb() -> KnowledgeBase:
    return KnowledgeBase(
        prefer_chroma=False
    )  # force deterministic keyword backend (no qdrant/chroma)


def test_reseed_replaces_stale_same_source():
    kb = _kb()
    ns = "client:test"
    kb.add_documents(
        ["hamari pricing 1999 rupaye per month"],
        source="website:x.com",
        namespace=ns,
        replace_source=True,
    )
    kb.add_documents(
        ["hamari pricing 2999 rupaye per month"],
        source="website:x.com",
        namespace=ns,
        replace_source=True,
    )
    texts = " ".join(h["text"] for h in kb.retrieve("pricing kitni", k=5, namespace=ns))
    assert "2999" in texts  # new content present
    assert "1999" not in texts  # stale chunk deleted before reseed (the fix)


def test_reseed_preserves_other_sources_in_namespace():
    kb = _kb()
    ns = "client:test2"
    kb.add_documents(
        ["owner ka naam Meera hai"], source="kb_interview", namespace=ns
    )  # manual KB, no replace
    kb.add_documents(
        ["site pricing 1999"], source="website:y.com", namespace=ns, replace_source=True
    )
    kb.add_documents(
        ["site pricing 2999"], source="website:y.com", namespace=ns, replace_source=True
    )
    texts = " ".join(h["text"] for h in kb.retrieve("owner naam", k=5, namespace=ns))
    assert "Meera" in texts  # different source survived the website reseed (scoped delete)


def test_replace_source_noop_without_source():
    kb = _kb()
    ns = "client:test3"
    kb.add_documents(
        ["doc one alpha"], namespace=ns, replace_source=True
    )  # no source -> cannot scope -> no delete
    kb.add_documents(["doc two beta"], namespace=ns, replace_source=True)
    texts = " ".join(h["text"] for h in kb.retrieve("doc", k=5, namespace=ns))
    assert "alpha" in texts and "beta" in texts  # nothing deleted when there's no source to scope


def test_default_add_still_appends():
    kb = _kb()
    ns = "client:test4"
    kb.add_documents(
        ["fact one gamma"], source="website:z.com", namespace=ns
    )  # replace_source defaults False
    kb.add_documents(["fact two delta"], source="website:z.com", namespace=ns)
    texts = " ".join(h["text"] for h in kb.retrieve("fact", k=5, namespace=ns))
    assert "gamma" in texts and "delta" in texts  # no behaviour change for normal add


def test_keyword_delete_source_rebuilds_df():
    idx = _KeywordIndex()
    idx.add("alpha beta", source="a")
    idx.add("beta gamma", source="b")
    assert idx.delete_source("a") == 1
    assert idx.size == 1
    hits = idx.search("gamma", k=3)
    assert hits and "gamma" in hits[0]["text"]  # survivor still searchable after df rebuild
    assert idx.delete_source("") == 0  # empty source is a no-op (never mass-deletes)
