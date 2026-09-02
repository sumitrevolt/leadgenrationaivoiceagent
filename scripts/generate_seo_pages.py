"""One-shot SEO pages batch generator — top niches × top cities.
Run: docker exec leadgen_app python scripts/generate_seo_pages.py
Generates ~30+ pages covering key lead-gen niches and cities for organic inbound.
"""

import asyncio
import os
import sys

sys.path.insert(0, "/app")


async def main():
    from app.marketing import seo_pages

    NICHES = [
        "solar",
        "real_estate",
        "gym_fitness",
        "restaurant",
        "clinic_doctor",
        "salon_spa",
        "coaching_institute",
        "interior_design",
        "ca_accountant",
        "car_dealer",
        "photographer",
        "event_management",
        "pest_control",
        "packers_movers",
        "insurance_agent",
        "driving_school",
        "grocery_store",
        "dental_clinic",
        "home_services",
        "travel_agent",
    ]
    CITIES = [
        "Pune",
        "Mumbai",
        "Nagpur",
        "Nashik",
        "Aurangabad",
        "Delhi",
        "Bangalore",
        "Hyderabad",
        "Ahmedabad",
        "Jaipur",
        "Indore",
        "Surat",
        "Lucknow",
        "Bhopal",
        "Kolhapur",
    ]

    # Check existing
    existing = {(p.get("niche"), p.get("city")) for p in seo_pages.list_pages(limit=500)}
    print(f"Existing pages: {len(existing)}")

    generated, skipped = 0, 0
    for niche in NICHES:
        for city in CITIES:
            if (niche, city) in existing:
                skipped += 1
                continue
            try:
                r = await seo_pages.generate_page(niche, city)
                if r.get("ok"):
                    generated += 1
                    print(f"  ✓ {niche} × {city} → {r['page']['slug']}")
                else:
                    print(f"  ✗ {niche} × {city} — {r}")
            except Exception as e:
                print(f"  ✗ {niche} × {city} — {e}")
            await asyncio.sleep(0.3)  # token safety

    print(f"\nDone: {generated} new pages generated, {skipped} already existed.")
    print(f"Total: {generated + len(existing)} pages indexed.")


if __name__ == "__main__":
    asyncio.run(main())
