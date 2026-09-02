# Pending Plans — consolidated (as of 2026-06-24)

> Single source-of-truth for plans that are **NOT yet done**. Completed plans were removed
> (recoverable from git history). Their work is LIVE — see notes below.
>
> For ongoing/forward roadmap (not formal "plans"), see `docs/ADVANCEMENT_ROADMAP_2026.md`,
> `docs/ROADMAP_2026_Automation_Revenue_Hardening.md`, `docs/PRIORITIZED_BACKLOG.md`.

## ✅ Removed — completed & shipped (for traceability)
- **Flow Runner** (`2026-06-20-flow-runner*.md`, phases 2/3/5) — all 7 phases merged + deployed LIVE 2026-06-21 (full n8n-parity + per-client builder). Design specs kept under `docs/superpowers/specs/`.
- **Readiness Infra Improvement** (`2026-06-20-readiness-infra-improvement.md`) — activation readiness probes LIVE (`/api/activation/summary` → `ready_for_first_paid_customer=true`, 0 blockers).
- **God-file Refactor** (`REFACTOR_PLAN.md`) — 10 god-files → 22 modules, all LIVE (`growth_revenue/crm/deliverability/...`, `marketing_tools/models`).

---

## ⏳ PENDING — Own Telephony Stack + Service Reselling (P3)
*(Originally `docs/P3_Own_Telephony_Stack_Plan.md`, decision 2026-06-07 — consolidated here, current-state updated.)*

**Goal:** apna telephony stack (cost control + white-label reselling), 3rd-party provider pe dependency kam.

### Current reality (2026-06-24) — vs original plan
- Provider ab **Vobiz** (not Plivo). **Exotel DELETED** 2026-06-18. Twilio = international fallback only.
- **FreeSWITCH container already exists** on VPS (part of the ~13-container stack) — partial groundwork done.
- Web-call transport LIVE (`/app/test-call`, free tuning). Vobiz SIP/WS stream LIVE (`vobiz_stream.py`).
- **Still NOT built:** own PBX/SBC dialplan + Pipecat-style owned pipeline replacing Vobiz; operator-direct trunk; per-client minute reselling/white-label billing.

### Target architecture (build order)
```
SIP trunk (Vobiz now → operator-direct @scale: Tata/Airtel ₹0.30-0.40/min)
        ↓
FreeSWITCH (Docker, VPS) — own PBX/SBC: DID routing, recording, CDRs
        ↓
Owned voice pipeline (Python) — STT (Groq/Whisper) → TelecallerBrain/free_ai → EdgeTTS
        ↓
Existing platform — campaigns, agents, niches, billing
```
- Transport-agnostic: web-call + SIP share the same bot core; swap trunk without code change.

### Economics (own stack @ ~50K min/mo)
- Software ₹0 (FreeSWITCH open-source, on existing VPS). Trunk operator-direct ₹0.30-0.40/min.
- ~₹17-22K total vs provider-route ₹30K+ → 20-40% saving + full control.
- White-label resell: minutes + numbers + AI agent on agency's brand (Synthflow charges $2,000/mo; we can undercut). Per-client usage metering already tracked (`calls_this_month`).

### Implementation steps (when unblocked)
1. `app/telephony/freeswitch/` — dialplan + ESL socket → owned pipeline; wire into VPS deploy.
2. Owned pipeline module — web-call transport first (proof), then SIP.
3. Outbound test call e2e on operator-direct trunk.
4. Usage metering + per-client minute packs (billing) — extend existing meter.
5. White-label: subdomain/branding per agency client (tenant middleware already exists).

### Blockers (EXTERNAL — user action / regulatory; do not burn tokens until unblocked)
- [ ] Vobiz recharge + DID purchase (`VOBIZ_CALLER_ID=+91<DID>`) — calls untestable till then.
- [ ] DLT + 140-series number for cold-calling (Udyam-based proprietorship re-apply path).
- [ ] Operator-direct trunk quote (only economical @25K+ min/mo — not yet at scale).
- [ ] Legal: pure minutes-resale touches VNO/OSP rules — safe path = SaaS bundle (DLT/140 in client's name). Deep legal research before reselling.
