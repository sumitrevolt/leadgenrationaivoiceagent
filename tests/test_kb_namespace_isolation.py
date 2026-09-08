"""Qdrant namespace-isolation enforcement (enterprise audit fix 2026-08-01).

kb_main is a SINGLE payload-partitioned collection — multi-tenant isolation is
100% dependent on every _QdrantIndex operation carrying a namespace filter:

  * size()  -> count() with count_filter = {namespace: X}
  * search() -> query_points() with query_filter = {namespace: X}
  * delete_source() -> delete() filter scoped by BOTH namespace AND source
  * add()   -> point payload records {namespace: X, ...}

These tests fake the QdrantClient and assert the filter/payload on every call —
a regression (e.g. someone drops the namespace filter "to speed up search")
would leak tenant A's KB chunks into tenant B's agent answers. Cross-tenant
leak is a DPDP-critical invariant (CLAUDE.md §5).
"""

from app.voice_agent import knowledge_base as KB


class FakeCount:
    def __init__(self, n):
        self.count = n


class FakePoint:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class FakeClient:
    """Records every call; returns canned shapes. Never does real I/O."""

    def __init__(self):
        self.calls = []

    def count(self, collection_name=None, count_filter=None, exact=None):
        self.calls.append(("count", collection_name, count_filter, exact))
        return FakeCount(3)

    def query_points(
        self,
        collection_name=None,
        query=None,
        query_filter=None,
        limit=None,
        with_payload=None,
        search_params=None,
    ):
        self.calls.append(("query", collection_name, query, query_filter, limit))
        return FakePoint(
            points=[FakePoint(payload={"namespace": "ns-a", "text": "A only", "source": "src"})]
        )

    def upsert(self, collection_name=None, points=None):
        self.calls.append(("upsert", collection_name, points))

    def delete(self, collection_name=None, points_selector=None):
        self.calls.append(("delete", collection_name, points_selector))


def _filter_conds(flt):
    """(key, value) pairs from a Qdrant Filter's `must` list."""
    out = []
    for c in getattr(flt, "must", []) or []:
        out.append((getattr(c, "key", None), getattr(getattr(c, "match", None), "value", None)))
    return out


def _make_index(fake, namespace="ns-a", monkeypatch=None):
    monkeypatch.setattr(KB, "_get_qdrant_client", lambda: fake)
    monkeypatch.setattr(KB, "_get_qdrant_embedder", lambda: _FakeEmbedder())
    return KB._QdrantIndex(namespace)


class _FakeEmbedder:
    def embed(self, texts):
        for t in texts:
            yield [0.1] * KB._QDRANT_VECTOR_SIZE


def test_search_scoped_by_namespace(monkeypatch):
    fake = FakeClient()
    idx = _make_index(fake, namespace="ns-a", monkeypatch=monkeypatch)

    idx.search("pricing")

    op, coll, query, flt, limit = fake.calls[0]
    assert op == "query"
    assert coll == KB._QDRANT_COLLECTION
    assert ("namespace", "ns-a") in _filter_conds(flt), "search must be namespace-filtered"
    # only the namespace condition — no other tenant's data can leak in
    assert len(_filter_conds(flt)) == 1


def test_size_scoped_by_namespace(monkeypatch):
    fake = FakeClient()
    idx = _make_index(fake, namespace="ns-b", monkeypatch=monkeypatch)

    n = idx.size

    op, coll, flt, exact = fake.calls[0]
    assert op == "count"
    assert coll == KB._QDRANT_COLLECTION
    assert ("namespace", "ns-b") in _filter_conds(flt)
    assert exact is True
    assert n == 3


def test_add_payload_records_namespace(monkeypatch):
    fake = FakeClient()
    idx = _make_index(fake, namespace="ns-c", monkeypatch=monkeypatch)

    idx.add("confidential client info", source="site")

    op, coll, points = fake.calls[0]
    assert op == "upsert"
    assert coll == KB._QDRANT_COLLECTION
    payload = points[0].payload
    assert payload["namespace"] == "ns-c", "upsert payload must carry the namespace"
    assert payload["text"] == "confidential client info"
    assert payload["source"] == "site"


def test_delete_source_scoped_by_namespace_and_source(monkeypatch):
    fake = FakeClient()
    idx = _make_index(fake, namespace="ns-a", monkeypatch=monkeypatch)

    idx.delete_source("site")

    op, coll, selector = fake.calls[0]
    assert op == "delete"
    assert coll == KB._QDRANT_COLLECTION
    flt = getattr(selector, "filter", None)
    conds = _filter_conds(flt)
    assert ("namespace", "ns-a") in conds
    assert ("source", "site") in conds, "delete must not nuke other sources/tenants"
    assert len(conds) == 2, "delete scope = namespace AND source, nothing else"


def test_distinct_namespaces_never_share_index(monkeypatch):
    """Two namespaces -> two isolated _QdrantIndex objects with their own ns."""
    fake = FakeClient()
    idx_a = _make_index(fake, namespace="client:111", monkeypatch=monkeypatch)
    idx_b = _make_index(fake, namespace="client:222", monkeypatch=monkeypatch)

    assert idx_a._namespace != idx_b._namespace
    idx_a.search("q")
    idx_b.search("q")
    conds = [_filter_conds(c[3]) for c in fake.calls if c[0] == "query"]
    assert ("namespace", "client:111") in conds[0]
    assert ("namespace", "client:222") in conds[1]
