"""Voice product (Product 2) public-API contract — flat per-band pricing truth.

Kyun ye file exist karti hai (2026-07-14 postmortem):
`GET /api/voice/niches` production me 7 din tak **500** de raha tha aur kisi test ne
nahi pakda. Root cause: pricing 2026-06-12 ko lead-counting se **flat per-niche-band**
ho gayi (`voice_packages.py` docstring: "Koi lead-counting nahi", "Unlimited AI calls"),
aur tab `lead_topup_price()` hata diya gaya — par `app/api/voice_product.py` use abhi
bhi import kar raha tha. Import fail -> har request pe ImportError -> 500.
Sentry: 375 + 222 + 84 (`'_IncludedRouter' object has no attribute 'path'`, secondary)
+ 173 (`PlanTierRateLimit call_next failed: ImportError(...)`) events.

Ye tests band ke flat price ko truth maante hain (§5 billing-truth: `voice_packages.py`
= single source) aur koi bhi resurrected lead-topup concept fail karenge.
"""

from __future__ import annotations

import pytest

from app.marketing import voice_packages as VP


# ---------------------------------------------------------------- pricing truth
def test_flat_band_pricing_is_the_source_of_truth():
    """Band flat monthly prices expose karein (CLAUDE.md §1: 4999/9999/19999,
    + 2026-08: S Starter 1999 · F Freemium 0)."""
    assert set(VP.BANDS) == {"S", "F", "A", "B", "C"}
    assert VP.BANDS["S"]["price_month"] == 1_999
    assert VP.BANDS["F"]["price_month"] == 0
    assert VP.BANDS["A"]["price_month"] == 4_999
    assert VP.BANDS["B"]["price_month"] == 9_999
    assert VP.BANDS["C"]["price_month"] == 19_999


def test_lead_topup_price_stays_removed():
    """Flat pricing me per-lead top-up pack ka concept hai hi nahi.

    Agar koi ise wapas laata hai to pricing model badal raha hai -> ye test
    jaan-bujh kar fail hoga taaki `test_billing_truth_2026.py` bhi saath update ho.
    """
    assert not hasattr(VP, "lead_topup_price"), (
        "lead_topup_price flat-band pricing me retire ho chuka hai — "
        "wapas laane se pehle billing-truth contract update karo"
    )


# ------------------------------------------------------- public API must not 500
def test_voice_niches_returns_200_and_never_500(client):
    """REGRESSION: ye endpoint prod me 500 de raha tha (dangling import)."""
    r = client.get("/api/voice/niches")
    assert r.status_code == 200, f"/api/voice/niches must not 500 — got {r.status_code}"
    body = r.json()
    assert body["product"] == "voice_agent"
    assert body["count"] == len(body["niches"])
    assert body["count"] > 0


def test_voice_niches_exposes_flat_band_price_not_topup(client):
    """Har niche apne band ka FLAT monthly price de — dead topup field nahi."""
    body = client.get("/api/voice/niches").json()
    for n in body["niches"]:
        assert "topup_pack_inr" not in n, "topup_pack_inr retired hai (flat pricing)"
        assert n["lead_band"] in {"A", "B", "C"}
        # band ka flat price truth voice_packages.BANDS se aana chahiye
        assert n["band_price_month_inr"] == VP.BANDS[n["lead_band"]]["price_month"]


def test_voice_packages_endpoint_healthy(client):
    """Padosi public endpoint bhi green rahe (same module import surface)."""
    r = client.get("/api/voice/packages")
    assert r.status_code == 200
    assert "tiers" in r.json()


@pytest.mark.parametrize("path", ["/api/voice/niches", "/api/voice/packages"])
def test_voice_public_endpoints_are_json(client, path):
    r = client.get(path)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
