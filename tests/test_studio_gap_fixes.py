"""Product-completeness: dormant features now DELIVERED to the paying customer.

Audit (2026-06-28) found advertised features whose engine existed but the customer
had no portal access. These pin the two cleanest fixes wired into the customer studio:
- #24 A/B post variations (was admin-only) → /api/customer/studio/variations
- #25 review kit (was missing) → /api/customer/studio/review-kit
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.mark.asyncio
async def test_studio_variations_returns_n_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import customer_marketing_studio as s

    monkeypatch.setattr(s, "_ctx", lambda cid: {"business_name": "Sharma Solar", "niche": "solar"})

    async def _fake_gen(**kw: Any) -> dict[str, Any]:
        return {"caption": "ok", "hashtags": ["#solar"]}

    from app.marketing import post_generator

    monkeypatch.setattr(post_generator, "generate_post", _fake_gen)

    out = await s.studio_variations(s.VariationsReq(count=3), client_id="c1")
    assert out["ok"] is True
    assert out["count"] == 3
    assert len(out["variations"]) == 3


@pytest.mark.asyncio
async def test_studio_review_kit_branded_happy_and_unhappy(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import customer_marketing_studio as s

    monkeypatch.setattr(s, "_ctx", lambda cid: {"business_name": "Verma Tiffin", "niche": "tiffin"})

    out = await s.studio_review_kit(
        s.ReviewKitReq(google_link="https://g.page/r/abc"), client_id="c1"
    )
    r = out["result"]
    assert out["ok"] is True
    assert "Verma Tiffin" in r["happy_message"]
    assert "https://g.page/r/abc" in r["happy_message"]  # review link woven in
    assert "PRIVATE" in r["unhappy_message"]  # unhappy → private, not public


@pytest.mark.asyncio
async def test_studio_review_kit_failopen_without_link(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import customer_marketing_studio as s

    monkeypatch.setattr(s, "_ctx", lambda cid: {"business_name": "X", "niche": "general"})
    out = await s.studio_review_kit(s.ReviewKitReq(), client_id="c1")
    assert out["ok"] is True
    assert out["result"]["happy_message"]  # never empty even without a link


@pytest.mark.asyncio
async def test_studio_catalog_upi_paylinks(monkeypatch: pytest.MonkeyPatch) -> None:
    """#27: catalog generates per-item UPI deep-links (no gateway needed)."""
    from app.api import customer_marketing_studio as s

    monkeypatch.setattr(s, "_ctx", lambda cid: {"business_name": "Sharma Salon", "niche": "salon"})
    out = await s.studio_catalog(
        s.CatalogReq(items="Haircut:200, Facial:500", vpa="sharma@oksbi"), client_id="c1"
    )
    items = out["result"]["items"]
    assert len(items) == 2
    assert items[0]["pay_link"].startswith("upi://pay?")
    assert "am=200" in items[0]["pay_link"] and "pa=sharma%40oksbi" in items[0]["pay_link"]
    # no VPA → no pay-link, but still lists items (graceful)
    out2 = await s.studio_catalog(s.CatalogReq(items="Haircut:200"), client_id="c1")
    assert out2["result"]["items"][0]["pay_link"] == ""
