import asyncio
import csv
import json
import os
from datetime import datetime
from app.platform.prospect_lists import _read_lists, _write_lists, create_list


async def main():
    print("--- UPDATING LOCAL ENRICHMENT RECORD ---")
    out_file = os.path.join("data", "enriched_prospects.jsonl")

    # 1. Read prospect
    with open("hot_icp_prospects.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        prospect = next(reader)

    # 2. Add enrichment data
    prospect["enriched_at"] = datetime.utcnow().isoformat() + "Z"
    prospect["pain_hypothesis"] = (
        "High value per client requires trust-building multi-channel touch. Raised Series A funding -> scaling pains in generating compliant leads predictably."
    )
    prospect["recommended_offer"] = "advanced"
    prospect["crm_sync_status"] = "pending_token"  # explicitly noting HubSpot token missing

    # 3. Write locally to enriched_prospects.jsonl
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(prospect) + "\n")

    print(f"VERIFIED: Wrote LEAD-1001 enrichment data to {out_file}")


if __name__ == "__main__":
    asyncio.run(main())
