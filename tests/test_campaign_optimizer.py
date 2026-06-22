"""Tests for enterprise flywheel — campaign optimizer, identity, promotion gate."""

from __future__ import annotations

import os

import pytest


@pytest.mark.asyncio
async def test_campaign_optimizer_status_off_by_default(monkeypatch):
    monkeypatch.delenv("CAMPAIGN_OPTIMIZER", raising=False)
    from app.agents import campaign_optimizer

    st = campaign_optimizer.status()
    assert st["enabled"] is False
    assert "interaction_count" in st


@pytest.mark.asyncio
async def test_campaign_optimizer_skips_when_off(monkeypatch):
    monkeypatch.setenv("CAMPAIGN_OPTIMIZER", "0")
    from app.agents import campaign_optimizer

    res = await campaign_optimizer.optimize(force=False)
    assert res.get("skipped") or res.get("enabled") is False


@pytest.mark.asyncio
async def test_campaign_optimizer_force_run(monkeypatch, tmp_path):
    monkeypatch.setenv("CAMPAIGN_OPTIMIZER", "1")
    monkeypatch.chdir(tmp_path)
    os.makedirs("data/campaign_optimization", exist_ok=True)
    from app.agents import campaign_optimizer

    res = await campaign_optimizer.optimize(force=True)
    assert res.get("ok") is True
    assert res.get("run_id")


def test_promotion_gate_blocks_low_sample():
    from app.agents.campaign_optimizer import check_promotion_gate

    g = check_promotion_gate(0.05, 0.08, 50, 50)
    assert g["promote"] is False
    assert g["champion_n"] == 50


def test_promotion_gate_passes_strong_lift(monkeypatch):
    monkeypatch.setenv("EVAL_GATE", "0")
    from app.agents.campaign_optimizer import check_promotion_gate

    g = check_promotion_gate(0.02, 0.05, 120, 120)
    assert g["relative_improvement"] >= 0.15
    assert g["champion_n"] >= 100


def test_identity_resolve_key_phone():
    from app.platform.identity_resolver import resolve_key

    k = resolve_key({"phone": "+919876543210"})
    assert k == "p:9876543210"


def test_identity_duplicate_groups_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from app.platform.identity_resolver import find_duplicate_groups

    assert find_duplicate_groups() == []


def test_spintax_expand():
    from app.platform.auto_outreach import _pick_spintax

    out = _pick_spintax("{Hi|Hello} {there|ji}")
    assert out.split()[0] in ("Hi", "Hello")


@pytest.mark.asyncio
async def test_approve_proposal_registers_variant(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    os.makedirs("data/campaign_optimization", exist_ok=True)
    from app.agents import campaign_optimizer

    pid = "abc123dead01"
    campaign_optimizer._append(
        campaign_optimizer._PROPOSALS,
        {
            "id": pid,
            "type": "email_variant",
            "niche": "solar",
            "title": "Test subject",
            "body": "Test body",
            "status": "proposal",
        },
    )
    res = await campaign_optimizer.approve_proposal(pid)
    assert res.get("ok") is True
    assert res.get("script_id") == "cold_email"
    again = await campaign_optimizer.approve_proposal(pid)
    assert again.get("already") is True


def test_revenue_attribution_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from app.platform import revenue_attribution

    r = revenue_attribution.record_touch(client_id="c1", channel="email", event="inquiry")
    assert r.get("ok") is True
    s = revenue_attribution.summary()
    assert s.get("touches", 0) >= 1
