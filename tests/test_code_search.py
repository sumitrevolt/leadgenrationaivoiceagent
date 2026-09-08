"""Tests for engineering-agent codebase search (Kilo-Code parity).

Covers: enabled() env gate, never-raise/empty paths, grounding_block shaping, and
the search_code() normalization (the bug-fixed indexer path that earlier called a
non-existent VectorStore.search()). Offline-clean — no real index / network needed.
"""

import asyncio

from app.agents import code_search
from app.ml import codebase_indexer


def test_enabled_reads_env(monkeypatch):
    monkeypatch.delenv("CODE_SEARCH", raising=False)
    assert code_search.enabled() is False
    monkeypatch.setenv("CODE_SEARCH", "1")
    assert code_search.enabled() is True
    monkeypatch.setenv("CODE_SEARCH", "0")
    assert code_search.enabled() is False


def test_search_empty_query_returns_empty():
    assert asyncio.run(code_search.search("")) == []
    assert asyncio.run(code_search.search("   ")) == []


def test_search_never_raises(monkeypatch):
    """Indexer blows up → search must swallow and return [] (never break caller)."""

    def boom():
        raise RuntimeError("no index available")

    monkeypatch.setattr(codebase_indexer, "get_codebase_indexer", boom)
    assert asyncio.run(code_search.search("anything at all")) == []


def test_grounding_block_shape():
    hits = [
        {
            "file": "app/x.py",
            "start_line": 1,
            "end_line": 9,
            "score": 0.812,
            "snippet": "def x():\n    return 1",
        }
    ]
    blk = code_search.grounding_block(hits)
    assert "app/x.py:1-9" in blk
    assert "def x()" in blk
    # empty hits → empty grounding (no spurious header)
    assert code_search.grounding_block([]) == ""


def test_grounding_block_respects_char_budget():
    big = "x" * 5000
    hits = [
        {"file": f"f{i}.py", "start_line": 1, "end_line": 2, "score": 0.5, "snippet": big}
        for i in range(5)
    ]
    blk = code_search.grounding_block(hits, max_chars=1200)
    # only the first block fits under the budget
    assert blk.count("# f") == 1


def test_search_code_normalizes(monkeypatch):
    """search_code() must use search_similar() and parse file/lines + snippet."""

    class FakeVS:
        async def search_similar(self, query, industry=None, language=None, top_k=5):
            return [
                {
                    "conversation_id": "app/foo.py:2",
                    "score": 0.91,
                    "user_message": "Code from app/foo.py lines 10-20",
                    "agent_response": "def foo():\n    return 1",
                    "industry": "platform",
                    "language": "python",
                },
                # locator missing from message → fall back to id parse
                {
                    "conversation_id": "app/bar.py:0",
                    "score": 0.4,
                    "user_message": "Code from somewhere",
                    "agent_response": "x = 2",
                    "industry": "general",
                    "language": "python",
                },
            ]

    idx = codebase_indexer.CodebaseIndexer()
    idx._vector_store = FakeVS()
    rows = asyncio.run(idx.search_code("foo helper", limit=5))

    assert len(rows) == 2
    first = rows[0]
    assert first["file"] == "app/foo.py"
    assert first["start_line"] == 10 and first["end_line"] == 20
    assert "def foo" in first["snippet"]
    assert first["language"] == "python" and first["domain"] == "platform"
    # id-parse fallback still yields a file path
    assert rows[1]["file"] == "app/bar.py"


def test_search_code_swallows_backend_error(monkeypatch):
    class BoomVS:
        async def search_similar(self, *a, **k):
            raise RuntimeError("vector store down")

    idx = codebase_indexer.CodebaseIndexer()
    idx._qdrant_index = None
    monkeypatch.setattr(codebase_indexer.CodebaseIndexer, "_qdrant", lambda self: None)
    idx._vector_store = BoomVS()
    assert asyncio.run(idx.search_code("anything")) == []


def test_qdrant_disabled_when_no_url(monkeypatch):
    """No QDRANT_URL → _qdrant() None → ChromaDB fallback path."""
    from app.config import settings

    monkeypatch.setattr(settings, "qdrant_url", "", raising=False)
    idx = codebase_indexer.CodebaseIndexer()
    assert idx._qdrant() is None


def test_qdrant_code_index_normalizes(monkeypatch):
    """QdrantCodeIndex.search_sync must normalize Qdrant points → {file,lines,snippet}."""
    import sys

    # Mock qdrant_client so the test works offline (no qdrant_client package needed)
    fake_qmodels = type(
        "QModels",
        (),
        {
            "Filter": lambda **k: None,
            "FieldCondition": lambda **k: None,
            "MatchValue": lambda **k: None,
            "PayloadSchemaType": type("PST", (), {"KEYWORD": "keyword"})(),
            "VectorParams": lambda **k: None,
            "Distance": type("D", (), {"COSINE": "cosine"})(),
        },
    )()
    monkeypatch.setitem(sys.modules, "qdrant_client", type("M", (), {"models": fake_qmodels})())

    idx = codebase_indexer.QdrantCodeIndex()

    class FakePoint:
        def __init__(self, payload, score):
            self.payload = payload
            self.score = score

    class FakeRes:
        points = [
            FakePoint(
                {
                    "file_path": "app/foo.py",
                    "start_line": 10,
                    "end_line": 20,
                    "content": "def foo():\n    return 1",
                    "language": "python",
                    "agent_domain": "platform",
                },
                0.91,
            )
        ]

    class FakeClient:
        def query_points(self, **k):
            return FakeRes()

    class FakeEmb:
        def embed(self, texts):
            return iter([[0.1, 0.2, 0.3]])

    # bypass real Qdrant/embedder setup
    idx._ready = True
    idx._client = FakeClient()
    idx._embedder = FakeEmb()
    rows = idx.search_sync("foo helper", limit=3)
    assert rows and rows[0]["file"] == "app/foo.py"
    assert rows[0]["start_line"] == 10 and rows[0]["end_line"] == 20
    assert "def foo" in rows[0]["snippet"]
    assert rows[0]["language"] == "python" and rows[0]["domain"] == "platform"


def test_qdrant_code_index_never_raises():
    """search_sync on a broken client → [] (never raises)."""
    idx = codebase_indexer.QdrantCodeIndex()
    idx._ready = True

    class BoomClient:
        def query_points(self, **k):
            raise RuntimeError("qdrant down")

    class FakeEmb:
        def embed(self, texts):
            return iter([[0.1]])

    idx._client = BoomClient()
    idx._embedder = FakeEmb()
    assert idx.search_sync("x") == []
