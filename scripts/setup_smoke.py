"""Customer-ready setup smoke — client store + auto content + scraper (no paid key)."""

import asyncio


async def main() -> None:
    from app.marketing import auto_content, clients_store

    # 1) onboard a client
    c = clients_store.add_client(
        "Sharma Solar",
        "solar_residential",
        city="Pune",
        phone="9876543210",
        plan="growth",
        brand={
            "primary": "#0ea5e9",
            "accent": "#f59e0b",
            "tagline": "Bijli bachao",
            "logo_text": "SS",
        },
        socials={"instagram": "sharmasolar"},
    )
    cid = c.get("id")
    print(
        "CLIENT:", bool(cid), c.get("business_name"), "| list:", len(clients_store.list_clients())
    )

    # 2) generate today's content for that client
    items = await auto_content.generate_for_client(c)
    print("GEN_ITEMS:", len(items), "types:", sorted({i.get("type") for i in items}))

    # 3) run_daily across active clients
    r = await auto_content.run_daily_content()
    print("DAILY:", r)
    q = auto_content.list_queue(cid)
    print("QUEUE:", len(q))

    # 4) scraper free OSM (network — best effort, short)
    try:
        from app.platform import prospector

        osm = prospector._osm_search("restaurant", "Pune", 5)
        print("OSM:", len(osm), "(first:", (osm[0].get("business_name") if osm else "none"), ")")
    except Exception as e:
        print("OSM: err", str(e)[:80])


if __name__ == "__main__":
    asyncio.run(main())
