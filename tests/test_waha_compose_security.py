"""Regression guards for the self-hosted WAHA compose boundary.

This is deliberately a small text-level contract: Compose interpolation is the
security boundary before the WAHA container starts, so missing credentials must
not silently become known fallback strings.
"""

import re
from pathlib import Path

COMPOSE_FILE = (
    Path(__file__).resolve().parents[1] / "deploy" / "compose" / "docker-compose.waha.yml"
)
ACTIVATION_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "activate_waha_vps.sh"


def test_waha_compose_requires_real_secrets_and_keeps_internal_app_port():
    content = COMPOSE_FILE.read_text(encoding="utf-8")

    assert "${WAHA_API_KEY:?WAHA_API_KEY must be set before starting WAHA}" in content
    assert "${WAHA_WEBHOOK_TOKEN:?WAHA_WEBHOOK_TOKEN must be set before starting WAHA}" in content
    assert "change-me-strong-key" not in content
    assert "change-me-token" not in content
    assert "http://app:8080/api/wa/selfhost/webhook?token=" in content


def test_waha_activation_script_requires_and_writes_env_supplied_secrets_only():
    content = ACTIVATION_SCRIPT.read_text(encoding="utf-8")

    assert ': "${WAHA_API_KEY:?' in content
    assert ': "${WAHA_WEBHOOK_TOKEN:?' in content
    assert "WAHA_API_KEY=${WAHA_API_KEY}" in content
    assert "WAHA_WEBHOOK_TOKEN=${WAHA_WEBHOOK_TOKEN}" in content
    assert not re.search(r"^WAHA_API_KEY=(?!\$\{WAHA_API_KEY\}$)", content, re.MULTILINE)
    assert not re.search(
        r"^WAHA_WEBHOOK_TOKEN=(?!\$\{WAHA_WEBHOOK_TOKEN\}$)", content, re.MULTILINE
    )
