from __future__ import annotations


def test_vector_store_accepts_fastembed_vector_iterable(tmp_path):
    from app.ml.vector_store import VectorStore

    store = VectorStore(persist_directory=str(tmp_path))

    class FakeFastEmbed:
        def embed(self, texts):
            assert texts == ["hello"]
            yield [0.1, 0.2, 0.3]

    store._embedder = FakeFastEmbed()
    store._embedder_kind = "fastembed"

    assert store._generate_embedding("hello") == [0.1, 0.2, 0.3]
