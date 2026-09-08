"""Maps key smoke — real scraper returns phones + rating + personalized pitch."""

import asyncio


async def main() -> None:
    from app.config import settings

    print(
        "KEY_SET:",
        bool(settings.google_maps_api_key) and "your-" not in settings.google_maps_api_key,
    )

    from app.lead_scraper.google_maps import GoogleMapsScraper

    sc = GoogleMapsScraper()
    leads = await sc.search_businesses("restaurant", "Pune", max_results=5)
    print("LEADS:", len(leads))
    withphone = sum(1 for l in leads if getattr(l, "phone", None))
    print("WITH_PHONE:", withphone)
    if leads:
        l = leads[0]
        print(
            "SAMPLE:",
            getattr(l, "name", "?"),
            "| ph:",
            bool(getattr(l, "phone", None)),
            "| rating:",
            getattr(l, "rating", None),
            "| reviews:",
            getattr(l, "reviews_count", None),
        )

    # personalized pitch
    from app.platform import prospector

    if hasattr(prospector, "build_personalized_pitch"):
        p = prospector.build_personalized_pitch(
            "Test Cafe", "restaurant_cafe", "Pune", 3.9, 12, False
        )
        print("PITCH:", p[:120])


if __name__ == "__main__":
    asyncio.run(main())
