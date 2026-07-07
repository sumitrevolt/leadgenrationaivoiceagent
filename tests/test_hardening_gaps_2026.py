"""Hardening gap-closure tests (2026-06-20) — production guarantees that were
BUILT but UNVERIFIED. Audit-flagged HIGH gaps:

  1. Stripe webhook signature verify fail-CLOSED in production (503), open in dev.
  2. Vobiz status-webhook idempotency — completion metering/billing runs once.
  3. Customer-portal invoice reads are tenant-scoped (cross-tenant IDOR filter).
  4. Voice annual + marketing top-up EXACT price literals (a ratio-preserving
     typo would slip past the existing relation-only checks).

Pure-python contract tests — koi network/DB/live-provider nahi. Never raises a
real Stripe/Vobiz call. Async handlers are driven via asyncio.run so the suite
does not depend on pytest-asyncio mode.
"""

from __future__ import annotations

import asyncio

import pytest


class _Req:
    """Minimal stand-in for starlette Request. Only `.form()` is exercised by the
    code paths under test."""

    def __init__(self, form: dict | None = None) -> None:
        self._form = form or {}

    async def form(self):  # noqa: D401 - mimics starlette Request.form()
        return self._form


# --------------------------------------------------------------------------- #
# 1. Stripe webhook signature — fail-CLOSED in prod, open in dev
# --------------------------------------------------------------------------- #
def test_stripe_webhook_503_in_production_without_secret(monkeypatch):
    """No STRIPE_WEBHOOK_SECRET + production = refuse unverified payment webhook
    (503) — a forged event could otherwise grant balance/plan. Dev still returns
    the graceful 200 skip (asserted indirectly: default app_env is development,
    so existing webhook tests are unaffected)."""
    from fastapi import HTTPException

    from app.api import webhooks

    monkeypatch.setattr(webhooks.settings, "stripe_webhook_secret", "", raising=False)
    monkeypatch.setattr(webhooks.settings, "app_env", "production", raising=False)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(webhooks.stripe_webhook(_Req(), stripe_signature=None, db=None))
    assert exc.value.status_code == 503


# --------------------------------------------------------------------------- #
# 2. Vobiz status webhook idempotency — completion handled EXACTLY once
# --------------------------------------------------------------------------- #
def test_vobiz_status_dedup_runs_completion_once(monkeypatch):
    """Duplicate provider callbacks for one call must not double-meter / double-bill.
    First POST processes; second returns duplicate_skipped without re-running."""
    from app.telephony import webhooks as tw

    # stateful seen_before: False on the 1st check (fresh), True after (duplicate)
    state = {"checks": 0}

    async def fake_seen_before(key):
        state["checks"] += 1
        return state["checks"] > 1

    import app.billing.idempotency as _idem

    monkeypatch.setattr(_idem, "seen_before", fake_seen_before, raising=False)

    handled = {"count": 0}

    class _FakeCM:
        async def handle_call_completed(self, call_id, duration=0, recording_url=None):
            handled["count"] += 1
            return None

    monkeypatch.setattr(tw, "_get_call_manager", lambda: _FakeCM(), raising=False)

    form = {"Status": "completed", "call_id": "CALL123", "Duration": "42"}
    out1 = asyncio.run(tw.vobiz_status_webhook(_Req(dict(form))))
    out2 = asyncio.run(tw.vobiz_status_webhook(_Req(dict(form))))

    assert out1.get("status") == "received"
    assert out2.get("status") == "duplicate_skipped"
    assert handled["count"] == 1  # completion ran exactly once across two callbacks


# --------------------------------------------------------------------------- #
# 3. Customer-portal invoice reads are tenant-scoped (cross-tenant IDOR)
# --------------------------------------------------------------------------- #
def test_portal_invoices_filters_to_own_tenant(monkeypatch):
    """gst_invoice.list_invoices returns ALL tenants' rows; the handler's
    client_id filter is the only IDOR guard — pin it."""
    import app.billing.gst_invoice as gi
    from app.api import customer_auth

    all_rows = [
        {
            "client_id": "clientA",
            "number": "INV/2026-27/0001",
            "date": "2026-06-01",
            "description": "Starter",
            "gross_inr": 1999,
            "plan": "starter",
        },
        {
            "client_id": "clientB",
            "number": "INV/2026-27/0002",
            "date": "2026-06-02",
            "description": "Growth",
            "gross_inr": 2999,
            "plan": "growth",
        },
    ]
    monkeypatch.setattr(gi, "list_invoices", lambda limit=50: list(all_rows), raising=False)

    out = asyncio.run(customer_auth.portal_invoices(client_id="clientA"))
    nums = [r["number"] for r in out["invoices"]]
    assert nums == ["INV/2026-27/0001"]  # B's invoice NOT leaked to A


def test_portal_invoice_html_blocks_other_tenant(monkeypatch):
    """clientA requesting clientB's invoice number = not found (no render)."""
    import app.billing.gst_invoice as gi
    from app.api import customer_auth

    monkeypatch.setattr(
        gi,
        "get_by_number",
        lambda number: {"client_id": "clientB", "number": number},
        raising=False,
    )
    out = asyncio.run(
        customer_auth.portal_invoice_html(number="INV/2026-27/0002", client_id="clientA")
    )
    assert isinstance(out, dict) and out.get("error") == "invoice not found"


def test_portal_invoice_html_allows_own_tenant(monkeypatch):
    """Owner DOES get their own invoice rendered (HTMLResponse)."""
    from fastapi.responses import HTMLResponse

    import app.billing.gst_invoice as gi
    from app.api import customer_auth

    monkeypatch.setattr(
        gi,
        "get_by_number",
        lambda number: {"client_id": "clientA", "number": number},
        raising=False,
    )
    monkeypatch.setattr(gi, "invoice_html", lambda inv: "<html>invoice</html>", raising=False)
    out = asyncio.run(
        customer_auth.portal_invoice_html(number="INV/2026-27/0001", client_id="clientA")
    )
    assert isinstance(out, HTMLResponse)


# --------------------------------------------------------------------------- #
# 4. EXACT-price literals (ratio-preserving typo guard)
# --------------------------------------------------------------------------- #
def test_voice_band_exact_price_literals():
    """Annual was only checked as 10x-of-monthly; a typo preserving the ratio
    (e.g. both off by a digit) would pass. Pin the absolute numbers."""
    from app.marketing.voice_packages import BANDS

    assert (BANDS["A"]["price_month"], BANDS["A"]["price_year"]) == (4999, 49990)
    assert (BANDS["B"]["price_month"], BANDS["B"]["price_year"]) == (9999, 99990)
    assert (BANDS["C"]["price_month"], BANDS["C"]["price_year"]) == (19999, 199990)


def test_topup_pack_exact_price_literals():
    """Top-up packs were only checked for >0 / rate>=12; pin exact prices."""
    from app.marketing.packages import topup_pack

    p100, p250, p500 = (
        topup_pack("topup_100"),
        topup_pack("topup_250"),
        topup_pack("topup_500"),
    )
    assert (p100["minutes"], p100["price_inr"]) == (100, 1499)
    assert (p250["minutes"], p250["price_inr"]) == (250, 3499)
    assert (p500["minutes"], p500["price_inr"]) == (500, 5999)
