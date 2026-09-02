"""Guards: hard-dead modules deleted 2026-07-19 stay gone."""

from __future__ import annotations

import importlib

import pytest

_REMOVED = (
    "app.platform.orchestrator",
    "app.config_production",
    "app.utils.logger_backup",
    "app.billing.payment_recon",
    "app.billing.payment_links",
)


@pytest.mark.parametrize("mod", _REMOVED)
def test_hard_dead_module_removed(mod: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(mod)


def test_usage_alerts_topup_link_is_empty_noop() -> None:
    import asyncio

    from app.billing import usage_alerts

    assert asyncio.run(usage_alerts._topup_link("c1", "Biz")) == ""
