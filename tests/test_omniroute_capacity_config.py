"""Contracts for the local gateway's bounded admission queue settings."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_compose_waits_for_slow_free_tier_without_removing_heap_valve():
    text = (ROOT / "deploy" / "compose" / "docker-compose.omniroute.yml").read_text(
        encoding="utf-8"
    )
    assert 'OMNIROUTE_CHAT_ADMISSION_QUEUE_MS: "${OMNIROUTE_CHAT_ADMISSION_QUEUE_MS:-120000}"' in text
    assert 'OMNIROUTE_CHAT_ADMISSION_MAX_QUEUED_BYTES: "${OMNIROUTE_CHAT_ADMISSION_MAX_QUEUED_BYTES:-4194304}"' in text
    assert "OMNIROUTE_CHAT_MAX_HEAVY_IN_FLIGHT" not in text
    assert 'mem_limit: "${OMNIROUTE_MEM_LIMIT_MB:-2048}m"' in text
