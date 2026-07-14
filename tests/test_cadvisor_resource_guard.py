"""Contracts for the production cAdvisor resource guard."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.observability.yml"


def _cadvisor_block() -> str:
    text = COMPOSE.read_text(encoding="utf-8")
    return text.split("\n  cadvisor:\n", 1)[1].split("\n  postgres-exporter:\n", 1)[0]


def test_cadvisor_skips_expensive_per_container_disk_scans() -> None:
    block = _cadvisor_block()

    assert "--disable_metrics=disk,diskIO" in block


def test_cadvisor_collection_matches_its_prometheus_scrape_interval() -> None:
    block = _cadvisor_block()
    prometheus = (ROOT / "monitoring" / "prometheus.yml").read_text(encoding="utf-8")
    cadvisor_job = prometheus.split("  - job_name: cadvisor", 1)[1].split(
        "\n  - job_name:", 1
    )[0]

    assert "--housekeeping_interval=10s" in block
    assert "scrape_interval: 10s" in cadvisor_job
