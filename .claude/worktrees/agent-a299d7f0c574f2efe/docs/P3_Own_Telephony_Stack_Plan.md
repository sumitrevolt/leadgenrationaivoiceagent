# P3 — Khud ka Telephony Stack + Service Reselling (Decision: 2026-06-07)

User decision: **khud ka stack banayenge AUR service bhi bechenge** (white-label/usage reselling).

## Architecture (build order)

```
SIP trunk (Plivo Zentrunk ab → Tata/Airtel direct @scale)
        ↓
FreeSWITCH (Docker, VPS) — apna PBX/SBC: DID routing, recording, CDRs
        ↓
Pipecat pipeline (Python) — STT (Vosk/Whisper) → LangGraph/LLMBrain → TTS (EdgeTTS)
        ↓
Existing platform — campaigns, agents (data/leads), niches, billing
```

- Transport-agnostic: web-call (hai) + SIP — same bot core, swap trunk bina code badle.
- Pipecat + LangGraph 2026 ka proven combo (docs/Architecture_Research_RAG_Agents_MCP.md).

## Cost (apna stack)

- Software ₹0 (FreeSWITCH + Pipecat open-source) · VPS pe hi (ya +₹500-1K/mo)
- Trunk: Plivo ₹0.60/min self-serve (pilot) → operator direct ₹0.30-0.40/min (25K+ min/mo)
- DLT ₹5,900 one-time + 140-number ₹1-3K/mo (cold-calling ke liye mandatory)
- @50K min/mo: ~₹17-22K total vs platform-route ₹30K+ → 20-40% saving + full control

## Service-resell model (white-label)

- Clients/agencies ko minutes + numbers + voice-agent platform apne brand pe — Synthflow white-label $2,000/mo hai, hum ₹10-25K/mo me de sakte (gap).
- Billing: per-client usage metering (calls_this_month already tracked) + margin on minutes (buy ₹0.30-0.60, sell ₹1.5-3 bundled w/ AI).
- ⚠️ LEGAL CHECK PENDING: pure minutes-resale India me VNO/OSP regulations touch karta hai (Telecom Act 2023 me OSP liberalized). Software+AI bundled service = SaaS (safe). Numbers client ke naam pe le ke manage karna = safest. Deep legal research next session.

## Implementation steps (next session se)

1. `app/telephony/freeswitch/` — Docker compose + dialplan (ESL socket → Pipecat), VPS deploy script me STEP
2. Pipecat pipeline module `app/voice_agent/pipecat_pipeline.py` — web-call transport pehle (proof), phir SIP
3. Plivo Zentrunk creds .env me (user: account banao) → outbound test call e2e
4. Usage metering + per-client minute packs (billing)
5. White-label: subdomain/branding per agency client

## User action items (blocker)

- [ ] Plivo account + Zentrunk self-serve setup (card chahiye)
- [ ] DLT registration ₹5,900 (Airtel/Jio DLT portal, 3-7 din)
- [ ] 140-series number (Exotel/operator se quote)
- [ ] WhatsApp Business Calling (Meta app) — warm-lead channel parallel
