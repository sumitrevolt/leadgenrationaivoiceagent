# Workflow Maps — LeadGenAI Pipelines

> **Visual ops reference** · Code paths verified 2026-06-20 · Runtime liveness re-verified 2026-06-27 (worker + scheduler Up, Celery queue 0, heartbeat fresh — `DIAGNOSTIC_ROOT_CAUSE_2026_06_27.md`) · Detail: [`AUTOMATION.md`](AUTOMATION.md)

---

## 1. Master pipeline (platform growth)

```mermaid
flowchart LR
  A[Scrape / Harvest] --> B[Score & Hot leads]
  B --> C[Email outreach]
  C --> D[Reply triage]
  D --> E{Interested?}
  E -->|Yes| F[Sales pipeline + WA draft]
  E -->|No| G[Nurture / cadence]
  F --> H[Signup / Pay UPI]
  H --> I[Onboard client]
```

**Jobs:** prospect 09:30 · outreach 10:30 · reply hourly · pipeline 11:00

---

## 2. Lead scraping → qualification

```mermaid
flowchart TD
  NR[NICHE_ROTATION=1] --> NP[niche_prospector]
  NP --> PR[prospector.run_prospecting]
  PR --> GM[Google Maps / OSM]
  PR --> DB[(leads table)]
  DB --> LS[lead_scoring.rescore_db]
  LS --> HOT[top_hot_leads API]
  HOT --> ROH[Rohan outreach queue]
```

Caps: `PROSPECT_MAX_LOOKUPS=60`/run · MX verify `OUTREACH_VERIFY_MX=1`

---

## 3. Inquiry → client lead (inbound)

```mermaid
flowchart TD
  W[Widget / Mini-site / Landing] --> PI[POST /api/public/inquiry]
  PI --> STORE[data/inquiries.jsonl + DB]
  STORE --> IH[inquiry_hooks.run_after_inquiry]
  IH --> AL[lead_alerts notify]
  IH --> LD[lead_distribution round-robin]
  IH --> CB[AUTO_CALLBACK_INQUIRY optional]
  IH --> WH[customer_webhooks lead.created]
  IH --> JR[journeys if JOURNEY_ENGINE=1]
```

Speed-to-lead metric: `speed_to_lead.py` — inquiry → first touch timestamp.

---

## 4. Calling → CRM (voice)

```mermaid
flowchart TD
  Q[queue_call] --> CMP[compliance gate]
  CMP --> VZ[Vobiz place_call]
  VZ --> WS[vobiz_stream WS]
  WS --> STT[Groq STT]
  STT --> LLM[telecaller_brain + RAG]
  LLM --> TTS[EdgeTTS]
  WS --> CL[cleanup]
  CL --> USG[usage.record_call_usage]
  CL --> WH2[call.completed webhook]
  CL --> AQ[AUTO_QUALIFY → CRM/cadence]
```

Cross-path audit: `scripts/cross_path_audit.py`

---

## 5. Follow-up omnichannel

```mermaid
flowchart LR
  EN[cadence.enroll] --> SEQ[email→sms→wa→voice→linkedin]
  SEQ --> DRAFT[draft only per step]
  DRAFT --> HUMAN[1-click human send]
  RE[reply_agent] --> UPD[prospect status hot/dead]
  SP[sales_pipeline] --> PROP[auto-proposal draft]
```

Flags: `CADENCE_ENGINE=1` · `SALES_ENGINE=1` · `WHATSAPP_AUTO_SEND=0` default

---

## 6. Revenue loop

```mermaid
flowchart TD
  PAY[UPI screenshot] --> ADM[admin upi/activate]
  ADM --> ACT[usage.activate_plan]
  ACT --> INV[gst_invoice if AUTO_INVOICE=1]
  ACT --> WH3[payment.received webhook]
  DUN[dunning_engine] --> REC[recovery emails]
  NU[nurture] --> RET[retention]
```

---

## 7. Client delivery loop (marketing)

```mermaid
flowchart LR
  ON[AUTO_ONBOARD] --> KB[KB seed]
  KB --> CP[content pack]
  CP --> SCH[content_schedule]
  SCH --> READY[status=ready]
  READY --> POST[human posts to social]
```

---

## 8. AI staff daily rhythm (IST)

| Time | Job | Agent |
|------|-----|-------|
| 06:30 | blog | Ravi |
| 07:00 | content | Isha |
| 08:30 | digest | Boss/Kavya |
| 09:30 | prospect | Dev/Rohan |
| 10:30 | email outreach | Rohan |
| 11:00 | pipeline | Neha |
| Hourly | health, reply, watchdog | Kavya, reply_agent, Hermes |

Full schedule: `team_scheduler.py` · Celery mirror: `worker.py`

---

## 9. Human breakpoints (when automation stops)

| Step | Why human |
|------|-----------|
| UPI verify | Fraud prevention |
| WhatsApp send | Meta ban policy |
| Social publish | Meta API approval |
| Cold phone India | DLT paperwork |
| Code deploy | Sumit approve Vikram patches |
