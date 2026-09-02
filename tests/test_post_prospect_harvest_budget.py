"""D2 — post-prospect harvest SoftTimeLimit budget (2026-08-07)."""

from __future__ import annotations

import os

import pytest

from app.platform.team_scheduler import post_prospect_harvest_timeout


@pytest.fixture(autouse=True)
def _clear_harvest_env(monkeypatch):
    monkeypatch.delenv("PROSPECT_INLINE_HARVEST", raising=False)
    monkeypatch.delenv("PROSPECT_POST_HARVEST_BUDGET_S", raising=False)


def test_default_budget_uses_240_under_ample_remain():
    # Old hard-cap was 120 — that is the WS3 bug. Default must exceed it.
    assert post_prospect_harvest_timeout(345.0) == 240.0


def test_budget_clamped_by_remain_minus_margin():
    # remain 90 → min(60, 240) = 60
    assert post_prospect_harvest_timeout(90.0) == 60.0


def test_skip_when_remain_too_small():
    assert post_prospect_harvest_timeout(44.0) is None


def test_inline_harvest_off_skips(monkeypatch):
    monkeypatch.setenv("PROSPECT_INLINE_HARVEST", "0")
    assert post_prospect_harvest_timeout(400.0) is None


def test_custom_budget_env(monkeypatch):
    monkeypatch.setenv("PROSPECT_POST_HARVEST_BUDGET_S", "180")
    assert post_prospect_harvest_timeout(400.0) == 180.0


def test_budget_hard_clamp_300(monkeypatch):
    monkeypatch.setenv("PROSPECT_POST_HARVEST_BUDGET_S", "999")
    assert post_prospect_harvest_timeout(400.0) == 300.0


def test_garbage_budget_falls_back_to_240(monkeypatch):
    monkeypatch.setenv("PROSPECT_POST_HARVEST_BUDGET_S", "abc")
    assert post_prospect_harvest_timeout(400.0) == 240.0


def test_budget_lower_clamp_30(monkeypatch):
    monkeypatch.setenv("PROSPECT_POST_HARVEST_BUDGET_S", "5")
    assert post_prospect_harvest_timeout(400.0) == 30.0


def test_flags_registered():
    from app.api.automation_flags import AUTOMATION_FLAGS

    assert "PROSPECT_INLINE_HARVEST" in AUTOMATION_FLAGS
    assert "PROSPECT_POST_HARVEST_BUDGET_S" in AUTOMATION_FLAGS
