import asyncio
import csv
from app.marketing.packages import get_public_packages


async def main():
    print("--- STARTING PROSPECT ENRICHMENT TEST ---")
    # Read public packages for offer picking
    packages = get_public_packages()
    offers = {p.get("key"): p.get("price") for p in packages}
    print(f"Loaded Offers: {offers}")

    # Read prospect
    with open("hot_icp_prospects.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        prospect = next(reader)

    print("\n[Target Prospect]")
    print(f"Company: {prospect['company']}")
    print(f"Name: {prospect['name']} ({prospect['title']})")
    print(f"Niche: {prospect['niche']}")
    print(f"Notes: {prospect['notes']}")

    # Simple logic mapping for Board specs
    # Offer-ladder pick based on niche/role
    offer_pick = "unknown"
    pain = "Needs more structured lead generation"

    if "SaaS" in prospect["niche"] or "Tech" in prospect["niche"]:
        offer_pick = "leadgen_advanced"
        pain = "Differentiating tech features in crowded ad market"
    if "Compliance" in prospect["niche"] or "Financial" in prospect["niche"]:
        offer_pick = "leadgen_combo"
        pain = "High value per client requires trust-building multi-channel touch"

    print("\n[Enrichment & Thesis]")
    print(f"Pain Hypothesis: {pain}")
    print(f"Recommended Offer: {offer_pick}")
    print(f"Will push PROSPECT_ID {prospect['id']} to @sales with score {prospect['score']}")


if __name__ == "__main__":
    asyncio.run(main())
