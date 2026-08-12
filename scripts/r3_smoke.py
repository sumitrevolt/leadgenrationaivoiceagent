"""Round-3 features VPS smoke (no LLM needed — fallbacks/pure logic)."""

import asyncio


async def main() -> None:
    from app.marketing import ads_copy, catalog, gbp_text, lead_scoring, reels, upi_kit

    u = upi_kit.payment_kit("Sharma Solar", "sharma@upi", amount="499")
    print(
        "UPI:", "upi://pay?pa=sharma@upi" in str(u), str(u.get("qr_svg", "")).count("<rect") > 100
    )

    c = await catalog.build_catalog(
        "Sharma Solar",
        [{"name": "3kW Solar", "price": "1,85,000"}, {"name": "5kW Solar", "price": "2,90,000"}],
    )
    print(
        "CATALOG:",
        "3kW" in str(c.get("svg") or c.get("price_list_svg") or ""),
        bool(c.get("wa_catalog_text")),
    )

    a = await ads_copy.ads_pack("Sharma Solar", "solar_residential", offer="20% off", city="Pune")
    g = a.get("google") or {}
    print(
        "ADS:", len(g.get("headlines") or []), all(len(h) <= 30 for h in g.get("headlines") or [])
    )

    r = await reels.reels_scripts("Sharma Solar", "solar_residential", topic="subsidy")
    print("REELS:", len(r.get("scripts") or []))

    s = lead_scoring.score_leads()
    print("SCORING:", "counts" in s, isinstance(s.get("leads"), list))

    t = await gbp_text.gbp_texts(
        "Sharma Solar", "solar_residential", city="Pune", services=["rooftop install"]
    )
    print(
        "GBP:",
        len(str(t.get("description") or "")) <= 750 and len(str(t.get("description") or "")) > 50,
    )


if __name__ == "__main__":
    asyncio.run(main())
