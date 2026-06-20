"""Docker compose: Qdrant reachable from app/worker containers (prod RAG fix)."""


def test_vps_compose_qdrant_host_gateway():
    text = open("docker-compose.vps.yml", encoding="utf-8").read()
    for svc in ("app:", "worker:", "worker-heavy:"):
        idx = text.index(f"  {svc}")
        chunk = text[idx : idx + 2500]
        assert "host.docker.internal:host-gateway" in chunk, f"{svc} missing extra_hosts"
        assert "QDRANT_URL" in chunk, f"{svc} missing QDRANT_URL default"
