"""Regression contract for busy-gateway health checks."""

from pathlib import Path

import scripts.omniroute_self_healing_watchdog as watchdog


def test_gateway_health_timeout_allows_slow_but_live_catalog():
    assert watchdog.GATEWAY_HEALTH_TIMEOUT_S == 60
    source = (Path(watchdog.__file__)).read_text(encoding="utf-8")
    assert "urlopen(req, timeout=GATEWAY_HEALTH_TIMEOUT_S)" in source
