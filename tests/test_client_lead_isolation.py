"""Client-lead isolation — client-owned inquiry/lead LeadGen ki apni sales
cadence/pipeline me KABHI enroll na ho (warna client ka end-customer LeadGen ka
"Rs 1999 plan lo" draft paata). Platform lead (no client_id) = purana behaviour
BILKUL unchanged.

Owned-file changes covered:
  - app/marketing/sales_pipeline.py: upsert_deal stamps client_id (conditional) +
    run_pipeline skips client-owned deals from cadence/sales actions.
  - app/platform/inquiry_hooks.py: cadence.enroll guard (skip when cid) +
    deal stamped with client_id.
"""

from __future__ import annotations

import asyncio
import os

import pytest


# ---------------------------------------------------------------------------
# 1. upsert_deal: client_id stamp is CONDITIONAL
# ---------------------------------------------------------------------------
def test_upsert_deal_stamps_client_id_when_present(tmp_path, monkeypatch):
    from app.marketing import sales_pipeline as sp

    monkeypatch.setattr(sp, "_DEALS", str(tmp_path / "deals.jsonl"))
    rec = sp.upsert_deal(
        {
            "phone": "9876500001",
            "business_name": "Jiya End-Customer",
            "niche": "beauty_makeover",
            "client_id": "d79d690f61b3",
        },
        stage="new",
    )
    assert rec.get("client_id") == "d79d690f61b3"


def test_upsert_deal_omits_client_id_for_platform_lead(tmp_path, monkeypatch):
    """No client_id -> deal record shape unchanged (key absent, not empty)."""
    from app.marketing import sales_pipeline as sp

    monkeypatch.setattr(sp, "_DEALS", str(tmp_path / "deals.jsonl"))
    rec = sp.upsert_deal(
        {
            "phone": "9876500002",
            "business_name": "LeadGen Prospect",
            "niche": "gym",
        },
        stage="new",
    )
    assert "client_id" not in rec


def test_upsert_deal_blank_client_id_not_stamped(tmp_path, monkeypatch):
    """Empty-string client_id (platform path passes cid or "") -> not stamped."""
    from app.marketing import sales_pipeline as sp

    monkeypatch.setattr(sp, "_DEALS", str(tmp_path / "deals.jsonl"))
    rec = sp.upsert_deal(
        {"phone": "9876500003", "business_name": "Prospect", "client_id": ""},
        stage="new",
    )
    assert "client_id" not in rec


# ---------------------------------------------------------------------------
# 2. run_pipeline: client-owned deal SKIPPED from LeadGen cadence/actions
# ---------------------------------------------------------------------------
def test_run_pipeline_skips_client_owned_deal(tmp_path, monkeypatch):
    from app.marketing import cadence as _cad
    from app.marketing import sales_pipeline as sp

    monkeypatch.setenv("SALES_ENGINE", "1")
    monkeypatch.setattr(sp, "_DEALS", str(tmp_path / "deals.jsonl"))
    monkeypatch.setattr(sp, "_ACTIONS", str(tmp_path / "actions.jsonl"))

    # Seed one platform deal + one client-owned deal, both at stage "new"
    # (send_intro -> cadence.enroll is the ONE live auto-execute action).
    sp.upsert_deal({"phone": "9876500010", "business_name": "LeadGen Prospect"}, stage="new")
    sp.upsert_deal(
        {
            "phone": "9876500011",
            "business_name": "Jiya End-Customer",
            "client_id": "d79d690f61b3",
        },
        stage="new",
    )

    enrolled: list[str] = []

    def _spy_enroll(lead):
        enrolled.append(str(lead.get("phone") or ""))
        return {"id": "x"}

    monkeypatch.setattr(_cad, "enroll", _spy_enroll)

    out = asyncio.run(sp.run_pipeline())
    assert out.get("ok") is True
    # Only the platform deal (phone ...010) reaches LeadGen cadence enroll.
    assert enrolled == ["9876500010"]


# ---------------------------------------------------------------------------
# 3. inquiry_hooks: cadence.enroll guard (skip when inquiry carries client id)
# ---------------------------------------------------------------------------
def _run_hook(rec, **kw):
    from app.platform import inquiry_hooks

    asyncio.run(inquiry_hooks.run_after_inquiry(rec, **kw))


def test_run_after_inquiry_skips_platform_cadence_for_client_lead(monkeypatch):
    from app.marketing import cadence as _cad

    calls: list[dict] = []

    def _spy_enroll(lead):
        calls.append(lead)
        return {"id": "x"}

    monkeypatch.setattr(_cad, "enroll", _spy_enroll)

    _run_hook(
        {
            "phone": "9876500020",
            "business_name": "Jiya End-Customer",
            "niche": "beauty_makeover",
            "source": "mini_site",
        },
        mini_client_id="d79d690f61b3",
    )
    # Client-owned inquiry -> NEVER enrolled in LeadGen's own cadence.
    assert calls == []


def test_run_after_inquiry_enrolls_platform_lead(monkeypatch):
    """No client id -> existing platform behaviour preserved (enroll fires)."""
    from app.marketing import cadence as _cad

    calls: list[dict] = []

    def _spy_enroll(lead):
        calls.append(lead)
        return {"id": "x"}

    monkeypatch.setattr(_cad, "enroll", _spy_enroll)

    _run_hook(
        {
            "phone": "9876500021",
            "business_name": "LeadGen Prospect",
            "niche": "gym",
            "source": "inquiry",
        },
    )
    assert len(calls) == 1
    assert calls[0].get("phone") == "9876500021"


def test_run_after_inquiry_stamps_client_id_on_deal(tmp_path, monkeypatch):
    """Client inquiry -> the deal upserted via inquiry_hooks carries client_id."""
    from app.marketing import cadence as _cad
    from app.marketing import sales_pipeline as sp

    monkeypatch.setattr(sp, "_DEALS", str(tmp_path / "deals.jsonl"))
    monkeypatch.setattr(_cad, "enroll", lambda lead: {"id": "x"})

    _run_hook(
        {
            "phone": "9876500022",
            "business_name": "Jiya End-Customer",
            "niche": "beauty_makeover",
            "source": "mini_site",
        },
        mini_client_id="d79d690f61b3",
    )

    deals = sp._read(sp._DEALS)
    hit = [d for d in deals if d.get("phone") == "9876500022"]
    assert hit, "deal not created via inquiry_hooks"
    assert hit[0].get("client_id") == "d79d690f61b3"


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-x", "-q"]))
