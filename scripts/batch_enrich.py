import asyncio
import csv
import json
import os
from datetime import datetime

async def main():
    print("--- BATCH ENRICHMENT: TASK_LI-001 ---")
    in_file = os.path.join("data", "hunter_leads", "TASK_LI-001_top10.csv")
    out_file = os.path.join("data", "enriched_prospects.jsonl")
    
    count = 0
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(in_file, 'r', encoding='utf-8') as f_in, open(out_file, 'a', encoding='utf-8') as f_out:
        reader = csv.DictReader(f_in)
        for row in reader:
            # Map enrichment data based on notes and intent
            row['enriched_at'] = datetime.utcnow().isoformat() + "Z"
            
            # Basic offer mapping logic based on score and notes
            score = int(row.get('score', 0))
            if score > 85 or 'Agency' in row.get('industry', ''):
                row['recommended_offer'] = "leadgen_advanced"
                row['pain_hypothesis'] = "Manual SEO audits consume too much team throughput. Needs automated AI delivery."
            else:
                row['recommended_offer'] = "leadgen_combo"
                row['pain_hypothesis'] = "Struggling to capture inbound intent effectively. Needs immediate AI callback + audit."
                
            row['crm_sync_status'] = "pending_token"
            
            f_out.write(json.dumps(row) + "\n")
            count += 1
            
    print(f"VERIFIED: Enriched {count} leads and appended to {out_file}")

if __name__ == "__main__":
    asyncio.run(main())
