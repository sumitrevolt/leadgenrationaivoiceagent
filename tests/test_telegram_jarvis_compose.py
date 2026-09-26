"""Regression contract for Telegram Jarvis production config mount."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.vps.yml"
SPEC = ROOT / "config" / "telegram" / "setup_spec.yaml"


def test_telegram_jarvis_mounts_canonical_config_read_only() -> None:
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    service = compose["services"]["telegram-jarvis"]
    volumes = service.get("volumes") or []

    assert "./config:/app/config:ro" in volumes
    assert SPEC.is_file()


def test_required_coordination_surfaces_exist_in_spec() -> None:
    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    keys = {
        str(group.get("key") or "")
        for group in (spec.get("cross_product") or [])
    }

    assert {
        "workers_coordination",
        "agents_coordination",
        "admin_command_center",
    }.issubset(keys)
