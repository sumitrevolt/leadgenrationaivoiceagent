"""Growth v3 VPS smoke — QR, report, reactivation, drip, brand, crm (no LLM needed)."""

import asyncio


async def main() -> None:
    from app.marketing import brand_kit, crm_lite, drip, monthly_report, reactivation, review_kit

    kit = await review_kit.full_kit("Sharma Solar", "Sharma Solar Pune")
    qr = str(kit.get("qr_svg") or "")
    print("REVIEWKIT:", qr.startswith("<svg"), qr.count("<rect") > 100, bool(kit.get("wa_message")))

    rep = await monthly_report.build_report("Sharma Solar")
    print("REPORT:", "Sharma Solar" in (rep.get("html") or ""), bool(rep.get("stats")))

    rc = await reactivation.reactivation_campaign(
        "Sharma Solar",
        "solar_residential",
        [{"name": "Amit", "phone": "9876543210"}, {"name": "Priya", "phone": "9123456780"}],
        offer="20% off",
    )
    print(
        "REACT:",
        len(rc.get("messages") or []),
        all("wa.me" in m.get("wa_link", "") for m in rc.get("messages") or []),
    )

    d = await drip.drip_sequence("Sharma Solar", "solar_residential", "new_inquiry")
    steps = d.get("steps") or d.get("sequence") or []
    print("DRIP:", len(steps))

    brand_kit.save_brand(
        "smoketest",
        {"business_name": "Sharma Solar", "colors": {"primary": "#0ea5e9", "accent": "#f59e0b"}},
    )
    print("BRAND:", bool(brand_kit.get_brand("smoketest")))

    crm_lite.add_customers(
        "smoketest", [{"name": "Amit", "phone": "9876543210", "birthday": "06-07"}]
    )
    print("CRM:", len(crm_lite.list_customers("smoketest")) >= 1)


if __name__ == "__main__":
    asyncio.run(main())
