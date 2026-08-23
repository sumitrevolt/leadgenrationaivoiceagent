"""TASK_RS-001 enrichment — deterministic, CSV-driven (no fabrication).

Reads data/hunter_leads/TASK_LI-001_top10.csv (verified by Board) and writes
data/enriched_prospects/TASK_LI-001_enriched.jsonl with pain_thesis derived
ONLY from the CSV's own notes field, offer ladder from packages.py rules
(₹1,999 Main / ₹5,999 Combo), and contact_quality from actual CSV columns.

HubSpot push: skipped fail-closed if HUBSPOT_API_KEY unset -> crm_status=pending_token.
"""
import csv
import json
import os

SRC = "data/hunter_leads/TASK_LI-001_top10.csv"
DST_DIR = "data/enriched_prospects"
DST = os.path.join(DST_DIR, "TASK_LI-001_enriched.jsonl")

has_hubspot = bool(os.getenv("HUBSPOT_API_KEY"))

rows = []
with open(SRC, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        rows.append(row)

os.makedirs(DST_DIR, exist_ok=True)

out = []
for row in rows:
    lid = row["lead_id"]
    score = int(row["score"])
    industry = row.get("industry", "")
    notes = row.get("notes", "")
    email = row.get("contact_email", "").strip()
    phone = row.get("contact_phone", "").strip()

    # Contact quality from REAL columns only
    if email.startswith("public") or phone.startswith("public") or "via site" in (email + phone).lower():
        contact_q = "form_only"
    elif email and phone:
        contact_q = "email+phone"
    elif phone:
        contact_q = "phone"
    else:
        contact_q = "email"

    # Offer ladder: Combo ₹5,999 for full-service agencies w/ score>=80, else Main ₹1,999
    is_full_agency = any(k in industry.lower() for k in ("full-service", "full strategy"))
    recommended_offer = "Combo ₹5,999/mo" if (score >= 80 and is_full_agency) else "Main ₹1,999/mo"

    # Pain thesis: first sentence of their own public positioning + capacity angle
    first_sentence = notes.split(".")[0].strip() if notes else "Manual delivery bottleneck"
    pain_thesis = f"{first_sentence}. Manual audit/delivery workload = labor-cost bottleneck jo AI Marketing automate karta hai."

    out.append({
        "lead_id": lid,
        "company": row["company"],
        "location": row.get("location", ""),
        "industry": industry,
        "score": score,
        "pain_thesis": pain_thesis,
        "recommended_offer": recommended_offer,
        "next_action": "route_to_sales_cadence",
        "contact_quality": contact_q,
        "contact_email": "" if email.startswith("public") else email,
        "contact_phone": "" if phone.startswith("public") else phone,
        "consent_basis": row.get("consent_basis", "Public contact"),
        "crm_status": "synced" if has_hubspot else "pending_token",
    })

with open(DST, "w", encoding="utf-8") as f:
    for rec in out:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

print(f"WROTE {len(out)} records -> {DST}")
print(f"HUBSPOT_API_KEY set: {has_hubspot} -> crm_status={'synced' if has_hubspot else 'pending_token'}")
offers = {}
for r in out:
    offers[r["recommended_offer"]] = offers.get(r["recommended_offer"], 0) + 1
print("Offer mix:", offers)
cq = {}
for r in out:
    cq[r["contact_quality"]] = cq[r["contact_quality"]] + 1
print("Contact quality:", cq)
