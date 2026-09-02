"""Docker compose: Qdrant in-stack on leadgen_net (prod RAG fix)."""


def test_vps_compose_qdrant_in_stack():
    text = open("docker-compose.vps.yml", encoding="utf-8").read()
    assert "  qdrant:" in text
    assert "/opt/qdrant_storage:/qdrant/storage" in text
    for svc in ("app:", "worker:", "worker-heavy:"):
        idx = text.index(f"  {svc}")
        chunk = text[idx : idx + 3500]
        assert "QDRANT_URL: http://qdrant:6333" in chunk, f"{svc} missing in-stack QDRANT_URL"
