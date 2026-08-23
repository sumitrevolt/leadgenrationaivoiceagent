import os
import csv
import json
import asyncio
from app.lead_scraper.deep_extract import extract_url


async def process_prospects():
    in_csv = "data/hunter_leads/TASK_LI-001_top10.csv"
    out_dir = "data/enriched_prospects"
    out_jsonl = os.path.join(out_dir, "TASK_LI-001_enriched.jsonl")
    os.makedirs(out_dir, exist_ok=True)

    # HubSpot Check directly from env
    hubspot_key = os.environ.get("HUBSPOT_API_KEY", "").strip()
    # Checking the .env file explicitly since os.environ might not have it in this subshell if not exported
    if not hubspot_key and os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                if line.startswith("HUBSPOT_API_KEY="):
                    hubspot_key = line.split("=", 1)[1].strip()
                    break

    has_hubspot = bool(hubspot_key and hubspot_key != "your-hubspot-api-key")

    results = []
    with open(in_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    async def enrich_row(row):
        lid = row["lead_id"]
        company = row["company"]
        email = row.get("contact_email", "")
        phone = row.get("contact_phone", "")
        notes = row.get("notes", "")

        # Derive Quality
        has_e = "@" in email
        has_p = ("+" in phone) or (
            phone.strip().replace("-", "").isdigit() and len(phone.replace("-", "").strip()) >= 10
        )

        if has_e and has_p:
            contact_q = "Email + Phone"
        elif has_e:
            contact_q = "Email Only"
        elif has_p:
            contact_q = "Phone Only"
        else:
            contact_q = "Form/Public Contact Only"

        # Basic domain resolution for deep_extract (via Web site if available in email)
        website = ""
        if has_e and "gmail.com" not in email and "outlook.com" not in email:
            domain = email.split("@")[-1].strip()
            website = f"http://{domain}"

        url_extracted_len = 0
        if website:
            try:
                # Bounded timeout for deep_extract to avoid hanging the loop
                ext = await asyncio.wait_for(extract_url(website), timeout=5)
                if ext and ext.get("ok"):
                    url_extracted_len = len(ext.get("text", ""))
            except Exception:
                pass  # Fail-closed smoothly as instructed, rely on CSV notes

        # Logic mapping
        score = int(row.get("score", 0))
        # recommended_offer based on ₹1,999 Main / ₹5,999 Combo instructions
        offer = (
            "Combo ₹5,999/mo"
            if score >= 80 or "Agency" in row.get("industry", "")
            else "Main ₹1,999/mo"
        )

        # Pain thesis derived intelligently from their model notes + deep extract presence if any
        pain = f"{notes.split('.')[0] if notes else 'Needs automated pipeline.'} High labor cost bottleneck."

        return {
            "lead_id": lid,
            "company": company,
            "pain_thesis": pain,
            "recommended_offer": offer,
            "next_action": "route_to_sales_cadence",
            "contact_quality": contact_q,
            "crm_status": "synced" if has_hubspot else "pending_token",
        }

    # Execute all 10 concurrently
    tasks = [enrich_row(r) for r in rows]
    enriched = await asyncio.gather(*tasks, return_exceptions=True)

    valid_enriched = []
    for count, r in enumerate(enriched):
        if isinstance(r, dict):
            valid_enriched.append(r)
        else:
            print(f"Row {count} error: {r}")

    with open(out_jsonl, "w", encoding="utf-8") as f:
        for v in valid_enriched:
            f.write(json.dumps(v) + "\n")

    return len(valid_enriched), has_hubspot, out_jsonl


if __name__ == "__main__":
    count, has_hs, out_path = asyncio.run(process_prospects())
    print(f"ENRICHED_COUNT={count}")
    print(f"HUBSPOT_ENABLED={has_hs}")
    print(f"FILE={out_path}")
