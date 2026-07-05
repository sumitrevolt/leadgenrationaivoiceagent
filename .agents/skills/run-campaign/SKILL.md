---
name: run-campaign
description: Run a lead-generation voice campaign for a client — scrape prospects for a niche/city, call + qualify them with the AI voice agent, score Hot/Warm/Cold, and deliver qualified leads. Use when the user says "run a campaign", "generate leads for X", "call prospects", or "start lead-gen for <client>".
---

# Run a Lead-Gen Campaign

Pipeline: scrape -> clean/DND-scrub -> 9am-7pm promo gate -> WhatsApp warm-up -> AI voice call (qualify) -> score -> deliver -> bill.

## Steps

1. Confirm inputs (ask if missing): client name, niche (see app/niches.py — exact keys, e.g. solar_commercial, dental_implants, hvac_commercial, ivf_clinics, immigration, home_loans, etc. — 39 builtin niches), cities, lead sources (google_maps, web; justdial/indiamart/linkedin = ToS-blocked auto-scrape, manual CSV import only), max leads.

2. Run the pipeline:
   ```python
   from app.automation.orchestrator_pipeline import LeadGenPipeline
   import asyncio
   pipe = LeadGenPipeline()
   result = asyncio.run(pipe.run_campaign(
       client_id="<client-id>", niche="<niche>",
       cities=["Pune","Mumbai"], sources=["google_maps","web"],
       max_leads=50, channels=["whatsapp","voice"],
   ))
   print(result)
   ```

3. Many clients at once -> use app/automation/agent_pool.py (AgentWorkerPool) for concurrent campaigns.

4. Compliance: real calls only 9am-7pm (TRAI window, fail-CLOSED; fix 2026-07-05), DND-scrubbed, DLT-registered number. Without telephony keys it runs in simulation mode (safe to test).

5. Report: scraped vs qualified vs delivered + estimated cost (INR), and where leads landed (Sheet/HubSpot/WhatsApp).
