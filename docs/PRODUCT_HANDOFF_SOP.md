# PRODUCT HANDOFF + SOP — LeadGenAI (product-wise + automation-wise)

> **Yeh doc kya hai:** Handoff + SOP ka **combination**, **dono products ke hisaab se** + har product ka **automation map** + **[Architecture Explorer](https://leadsgenai.in/app/explorer) mirror**.
> **Generated:** 2026-06-20 (PM, explorer-sync + handoff-lockstep pass) · **Live:** https://leadsgenai.in · **Explorer:** https://leadsgenai.in/app/explorer
> **Latest sync:** 2026-06-22 — **Final Production Advancement Council GREEN** (measure-first gates clean, no fabricated code, lever = GTM; verdict `PROJECT_HANDOFF.md` §27). Prior 06-21: Marketing tier feature lists expanded (packages.py → handoff/SOP/onboarding/sales) · UPI LIVE · godfile refactor · `client_snapshots` shipped · `PROJECT_HANDOFF.md` lockstep.
> **Repo:** github.com/sumitrevolt/leadgenrationaivoiceagent (main) · **VPS:** Hostinger Mumbai `72.61.245.204`
> **Source of truth:** `CLAUDE.md` (current-state facts) — conflict ho to CLAUDE.md jeetta. Detail: `docs/PROJECT_HANDOFF.md` · `docs/PROJECT_SOP.md` · `docs/ENTERPRISE_DOC_INDEX.md`. History: `docs/SESSION_LOG.md`.
> **Graph source (code):** `frontend/explorer.html` — drift audit: `python scripts/explorer_sync.py`
> **Golden rules:** (1) Windows = source of truth. (2) Context-first, verify before "done". (3) Compliance gate kabhi OFF mat karo. (4) Free stack only. (5) DO alag products — "bundle" mat bolo.

---

## PART 0 — Shared Platform Foundation

Dono products EK hi FastAPI platform pe chalte. Yeh layer common hai.

### 0.1 Stack & infra (condensed — full: PROJECT_HANDOFF §3–4)

| Layer | Detail |
|-------|--------|
| **App** | FastAPI async, `leadgen_app:8000` (Docker `docker-compose.vps.yml`), Caddy → `127.0.0.1:8000`. ~753 routes (prod_check), ~464 py files, 50 pages |
| **Data** | Postgres `leadgen_db` via PgBouncer `:6432` · Redis `:6379` · Qdrant `:6333` · `./data` jsonl bind-mount · MinIO opt-in |
| **Workers** | Celery: `leadgen_worker` (conc 4) + `leadgen_scheduler` (beat). `WEB_CONCURRENCY=2`, `RUN_IN_PROCESS_SCHEDULER=0` |
| **VPS** | ~13+ containers (+ 6 observability), self-heal `*/10`, backups ~04:00, ntfy `https://ntfy.leadsgenai.in` |

### 0.2 AI stack — ALL FREE (`app/voice_agent/free_ai.py`)

- **LLM:** Mistral primary → Groq → Cerebras → Gemini → SambaNova → OpenRouter (circuit-breaker on 429)
- **STT:** Groq `whisper-large-v3` → Gemini → faster-whisper
- **TTS:** EdgeTTS `hi-IN-SwaraNeural` (`edge-tts>=7.2.0`)
- **RAG:** Qdrant `kb_main` · namespaces `niche:` · `client:` · `skills` (241 skills via `SKILL_PACK`)

### 0.3 Shared AI staff (platform — dono products serve)

| ID | Name | Role | Schedule / flag |
|----|------|------|-----------------|
| `manager` | Boss 🧑‍💼 | Supervisor / LangGraph routing | on-demand `/api/agents/run` |
| `kavya` | Kavya 🛡️ | Ops health, provider/DB/disk | hourly |
| `hermes` | Hermes 🛰️ | Infra scan 0–100 + fix-actions | `INFRA_HANDLER`, hourly |
| `nikhil` | Nikhil 💰 | Dunning, nurture, MRR digest | `DUNNING_ENGINE`, daily |
| `vikram` | Vikram 🛠️ | Code patch PROPOSALS (admin approve) | `CODE_UPGRADER`, hourly |
| `guru` | Guru 📚 | Skill pack + KB ingest | `SKILL_PACK`, daily |
| `pranav` | Pranav 🔧 | SRE — backup/DR/capacity | `SRE_AGENT`, hourly+daily |
| `vidya` | Vidya 💹 | FinOps — margin/LLM spend | `FINOPS_AGENT`, 09:00 IST |
| `arnav` | Arnav 🛡️ | Security/DPDP/TRAI posture | `SECURITY_AGENT`, 09:30 IST |

Full registry: `docs/AGENT_REGISTRY.md` · UI: `/app/team` · API: `GET /api/platform/team?product=`

### 0.4 Shared automation loops

- **Self-improve** (`SELF_IMPROVE_LOOP` ON) — 180s Celery requeue, 15 actions, eval_gate safety
- **Coordinator** — planner / handoff / fanout / Reflexion / debate
- **Process engine** — event journal, human breakpoints, approvals cockpit
- **Dead-man trio** — heartbeat · revive */20min · ops watchdog
- **Hygiene** Sat 04:00 · **Backups** ~04:00 · **Growth-pulse** */15min

### 0.5 Deploy + compliance + gotchas

**Deploy:** `prod_check` → `run_tests.bat` (log Read) → git push → VPS `git pull` + `build app` + `up -d --no-deps app` (+ worker+scheduler if automation changed) → `/health`=production.

- 🚨 **CI = GATE-ONLY** — manual SSH deploy (`DEPLOY_ENABLED` unset)
- **Compliance:** TRAI DND fail-CLOSED · 10am–7pm · AI disclosure · consent ledger — **kabhi disable mat karo**
- **Gotchas:** Windows = truth · stale `.pyc` → container recreate · secrets sirf `.env`

### 0.6 Architecture Explorer — live system map (`/app/explorer`)

**URL:** https://leadsgenai.in/app/explorer · **Code:** `frontend/explorer.html` · **Route:** `main.py` `@app.get("/app/explorer")`

Yeh doc ka **visual twin** hai — naya owner pehle explorer kholo, phir yeh doc deep-dive ke liye.

#### 0.6.1 UI layout (4 views + sidebar)

| Key | View | Kya dikhata |
|-----|------|-------------|
| **1** | **Structural** | Full stack — Caddy → FastAPI → data → voice → MCP → gaps (red dashed) |
| **2** | **Automation** | Complete IST pipeline — beat→worker→jobs→loops→launch gate |
| **3** | **Builder** | Custom flows (localStorage) — drag orange→green ports, Shift+click connect |
| **4** | **Products** | 2 SKU split — Marketing tiers vs Voice bands vs shared billing |

**Sidebar tabs:** INFO · FLOW · FLAGS · SCHED · BUILD  
**Toolbar:** Play Flow · Connections · Loops · IST Schedule · Export JSON · [Mission Control](/app/automation)

**Live sync APIs (same origin pe auto-poll):**
- `GET /health` · `GET /api/activation/summary` → `production_ready`, `ready_for_first_paid_customer`, blockers
- `GET /api/growth/infra/flags` → FLAGS tab
- `GET /api/growth/infra/explorer-drift` (admin) → graph↔code coverage HUD

**Drift audit (dev):** `python scripts/explorer_sync.py` — engine modules vs graph text; `--stubs` paste-ready nodes.

#### 0.6.2 Structural view — node catalog (explorer `VIEWS.structural`)

| Node ID | Badge | Title | Key files / routes |
|---------|-------|-------|-------------------|
| `internet` | ENTRY | Browser / Internet | Public + widget.js |
| `vps` | HOST | Hostinger VPS Mumbai | `docker-compose.vps.yml` |
| `caddy` | EDGE | Caddy TLS | → `127.0.0.1:8000` |
| `public_pages` | LAYER | Public Frontend | `/audit` `/pricing` `/blog` `/compare` `/voice-agent` |
| `embed_widget` | WIDGET | Lead-Capture Embed | `/b/{slug}/widget.js` → `/api/public/inquiry` |
| `admin_ui` | LAYER | Admin God Mode | `/app/admin` · 21 workflows · bulk · UPI activate |
| `explorer` | GRAPH | Architecture Explorer | `/app/explorer` (yeh page) |
| `growth_hub` | GROWTH | Growth & Ops Hub | `/app/growth-tools` · `/app/outreach` · `/app/dialer` · `/app/analytics` |
| `customer_portal` | LAYER | Customer Portal | `/app/login` → `/app/customer` · TOTP · webhooks |
| `marketing_hub` | MARKETING | Marketing Command | `/app/marketing` 28 tabs · `/api/marketing/*` |
| `team_ui` | TEAM | AI Staff Dashboard | `/app/team` · SSE `agent_events` |
| `auth` | LAYER | Auth & RBAC | Admin JWT · Customer JWT · `/app/team-access` |
| `tenant_wl` | TENANT | White-Label | `middleware/tenant.py` fail-open |
| `billing` | BILLING | Billing & Usage | `packages.py` · `usage.py` · GST |
| `fastapi` | LAYER | FastAPI Monolith | `main.py` ~753 routes |
| `launch` | LAUNCH | Production Ready Gate | `/api/activation/*` |
| `integration_gate` | GATE | Final Integration Check | `final_integration_check.py` |
| `cross_path_audit` | GUARD | Cross-Path Audit | telephony parity guard |
| `mcp_product` | MCP | MCP-as-Product | `/mcp` · `/api/mcp-product/v1` · `/.well-known/agent.json` |
| `compliance` | LEGAL | India Telecom Compliance | `compliance.py` · `dnd_checker.py` |
| `ai_staff` | LAYER | 17 AI Staff | `team.py` · `team_scheduler.py` |
| `voice_brain` | LAYER | Voice Brain Pipeline | `voice_agent/` |
| `voice_product` | PRODUCT | Voice Agent SKU | `voice_packages.py` |
| `telephony_hub` | TELEPHONY | Telephony Webhooks | Vobiz active · Twilio intl |
| `vobiz_stream` | WS STREAM | Vobiz WS Stream | L16/16k · `_cleanup`→hooks |
| `post_call_hooks` | POST-CALL | Post-Call Hooks | meter · qualify · `call.report.ready` |
| `call_insights` | ASK AI | Call Insights NL | `/api/voiceai/ask` · `/api/ai/command` |
| `call_recordings` | RECORDINGS | Call Recordings API | `VOBIZ_CALL_RECORD=1` |
| `celery` | LAYER | Celery Queue | beat → Redis → worker |
| `external` | LAYER | External Integrations | Vobiz · SMTP · Maps · Pollinations · Telegram |
| `monitoring` | LAYER | Monitoring Stack | Prometheus · Grafana · Loki · Tempo · Flower |
| `free_ai` | LAYER | Free AI Chain | `free_ai.py` |
| `rag` | LAYER | RAG / KB | Qdrant · agentic RAG opt-in |
| `data_layer` | LAYER | Data Layer | Postgres · Redis · Qdrant · jsonl |
| `brand_frames` | LIVE | Branded Frames + Daily Feed | `brand_frames.py` |
| `geo_vis` | GEO | GEO / AI Visibility | `/geo-check` · `localseo.py` |
| `crm_sync` | CRM | Native CRM Sync | Zoho/HubSpot · `CRM_SYNC` OFF |
| `agent_memory` | MEMORY | Agent Memory + DPDP | purge API |
| `turnstile` | BOT GATE | Cloudflare Turnstile | `/audit` `/start` |
| `fire_calls` | CAMPAIGN | Outbound Campaign | `scripts/fire_calls.py` |
| `minio` | S3 | MinIO Storage | `minio_client.py` |
| `rate_limit_mw` | MIDDLEWARE | Plan Rate Limit | `PLAN_RATE_LIMIT=1` |
| `gap_transfer` | GAP P0 | Live Human Transfer | `CALL_TRANSFER=1` · needs DID |
| `gap_meta` | BLOCKED | Meta FB/IG Auto-Post | app-review blocked |

**Structural presets:** Full Stack · Products · Voice Stack · Gap Analysis · New Features

#### 0.6.3 Automation view — pipeline nodes (explorer `VIEWS.automation`)

| Node ID | Sched (IST) | Title | Flag (key) |
|---------|-------------|-------|------------|
| `beat` | cron | Celery Beat + team_scheduler | `TEAM_AUTOMATION` |
| `worker` | queue | Celery Worker conc=4 | — |
| `blog` | 06:30 | Programmatic Blog SEO | — |
| `prospect` | 09:30, 14:30 | Prospector + Lead Harvester | `NICHE_ROTATION`, `LEAD_HARVESTER` |
| `niche_prospector` | 09:30+ | Niche rotation scrape | `NICHE_ROTATION` |
| `score` | post-scrape | Lead Scoring 0–100 | — |
| `outreach` | 10:30 | Email Outreach (Rohan) | `AUTO_EMAIL_OUTREACH`, `EMAIL_WARMUP` |
| `email_unsub` | on send | RFC8058 Unsubscribe | — |
| `reply` | hourly | Reply Agent IMAP | `REPLY_AGENT` |
| `content` | 07:00 | Content Generator (Isha) | `USE_STRUCTURED_CONTENT` |
| `content_approve` | on submit | Content Approval Loop | clientops |
| `content_distribute` | on demand | IndexNow (Bing/Yandex) URL ping | — |
| `journey` | event | Journey / Cadence | `JOURNEY_ENGINE`, `CADENCE_ENGINE` |
| `onboard` | hourly | Auto Onboard + FDE | `AUTO_ONBOARD` |
| `lead_dist` | on inquiry | Lead Round-Robin | — |
| `stl` | real-time | Speed-to-Lead SLA | 2-min target |
| `pipeline_ops` | 11:00, 16:00 | Pipeline Ops (Neha) | rescore + followups |
| `sched_ops` | 18:30 Wed Sat | Evening wrap · weekly packs · hygiene | `WEEKLY_MARKETING_PACK` |
| `kb_weekly` | Sun 05:00 | KB Refresh | `KB_WEEKLY_REFRESH` |
| `coordinator` | on-demand | Multi-Agent Coordinator | — |
| `process` | tick | Process Engine | `PROCESS_ENGINE` |
| `process_autostart` | 11:30 | Process Auto-Start | `PROCESS_AUTOSTART` |
| `self_improve` | 180s | Self-Improve Loop | `SELF_IMPROVE_LOOP` |
| `eval_gate` | on eval | Eval Gate regression | `EVAL_GATE` |
| `sales` | trigger | Sales Team + Closer | `SALES_TEAM`, `SALES_ENGINE` |
| `revenue` | daily | Revenue Ops (Nikhil) | `DUNNING_ENGINE` |
| `growth_opt` | */15 | Growth Optimizer | `GROWTH_OPTIMIZER` |
| `channel_exp` | hourly | Channel Experiments bandit | `CHANNEL_EXPERIMENTS` |
| `ops` | hourly | Ops Watchdog + engineers | `OPS_WATCHDOG` |
| `automation_health` | continuous | Dead-man job registry | — |
| `meter_watch` | :55 hourly | Billing meter failure alert | `METER_ALERTS` |
| `loop_supervisor` | 120s | Loop supervisor SPOF | `LOOP_SUPERVISOR` |
| `approvals_cockpit` | live | Agentic Approval Cockpit | `/app/automation` |
| `fire_campaign` | manual | Outbound Swara campaign | `fire_calls.py` |
| `post_call_pipe` | on hangup | Post-call pipeline | `AUTO_QUALIFY_CALLS` |
| `vobiz_inbound` | inbound | Vobiz inbound webhook | `AMD_DETECT` |
| `whatsapp_wa` | 1-click | WhatsApp campaigns | `WHATSAPP_AUTO_SEND` OFF default |
| `launch` | 60s poll | Production Ready | activation probes |
| `public_in` | trigger | Inbound inquiry/signup | `public_site.py` |
| `customer_wh` | events | Customer Webhooks HMAC | `CUSTOMER_WEBHOOKS` |
| `ntfy_alerts` | push | ntfy ops alerts | `ops_alerts` |
| `code_upgrader` | hourly | Vikram proposals | `CODE_UPGRADER` |
| `skill_pack` | ingest | 241 skills | `SKILL_PACK` |
| `consent_ledger` | opt-out | TRAI/DPDP suppress | — |
| `review_monitor` | daily | Google review alerts | `REVIEW_MONITOR` |
| `rank_tracker` | daily | SEO rank tracking | `RANK_TRACKER` |
| `deliverability_monitor` | daily | Email reputation | `DELIVERABILITY_MONITOR` |
| `llm_metrics` | live | LLM provider metrics | — |
| `ui` | — | Mission Control | `/app/automation` 28 tabs |
| `admin_hub` | — | Admin God Mode workflows | `/app/admin` |

**Automation presets:** Full Pipeline · Lead Gen Only · Content · Revenue Ops · Launch & Ops · Client Ops · Outbound Campaign · Roadmap/Next · Loops Only

**Gap nodes (red — explorer roadmap tab):** `gap_transfer` (live human transfer, needs DID) · `rm_ops` (Vobiz DID) · `rm_inbound` · `rm_obs` (Sentry/PostHog) · `rm_deploy` (CI auto-deploy). *(`gap_snapshots` ✅ resolved — `client_snapshots` shipped 06-20.)*

#### 0.6.4 Products view — 2 SKU map (explorer `VIEWS.products`)

```
                    ┌─ Product 1: AI Automated Marketing (MAIN)
Acquisition ────────┤   Trial ₹0 · Starter ₹1,199 · Growth ₹2,999 · Advanced ₹6,999
/audit /pricing     │   Modules: content · GBP · widget · outreach
                    │   Advanced ONLY → voice FEATURE (inbound callback, NOT Product 2)
                    │
                    └─ Product 2: AI Voice Calling Agent (STANDALONE)
                        Pilot FREE · Band A ₹4,999 · B ₹9,999 · C ₹19,999
                        Stack: Vobiz · compliance gate · /voice-agent page
                        
Shared center: billing · customer portal · admin · data layer
```

**Products presets:** Marketing SKU · Voice SKU · Advanced Feature Only · Full Compare

#### 0.6.5 Explorer keyboard shortcuts

| Key | Action |
|-----|--------|
| `1`–`4` | Switch Structural / Automation / Builder / Products |
| `F` | Fit view · `+`/`-` zoom · `Space` animate flow |
| `T` | Trace downstream · `Del` delete (builder) |
| `Shift+click` | Connect two nodes · port drag = wire |
| Dbl-click node | Copy file path to clipboard |

---

## PART 1 — PRODUCT 1: AI Automated Marketing (MAIN)

### 1.1 Positioning
Chhote local businesses — marketing automation (Dhanda-class). **Voice = Advanced tier FEATURE only** (inbound callback). **Sellable ABHI** — DLT/telephony cold-call ki zaroorat nahi.

### 1.2 Features & pages

| Type | Routes |
|------|--------|
| Public magnets | `/audit` · `/site-audit` · `/blog` · `/geo-check` · `/b/{slug}` + widget |
| Signup/revenue | `/pricing` · `/start` · `/compare` |
| App | `/app/marketing` (28 tabs) · `/app/clients` · `/app/outreach` · `/app/growth-tools` (18) · `/app/automation` |

Engines: AI image (Pollinations) · scheduler · mini-site · onboarding · embed widget · brand frames · GEO visibility.

### 1.3 Pricing (`packages.py`)

| Tier | Monthly | Yearly (10×) |
|------|---------|--------------|
| Starter | ₹1,199 | ₹11,990 |
| Growth | ₹2,999 | ₹29,990 |
| Advanced (+ voice feature, 500 min) | ₹6,999 | ₹69,990 |

Top-ups: 100/250/500 min = ₹1,499 / ₹3,499 / ₹5,999.

**Canonical feature copy:** `app/marketing/packages.py` (counts: Trial 11 · Starter 15 · Growth 18 · Advanced 14). Public API: `GET /api/marketing/packages`. **SOP rule:** pricing/marketing copy change = `packages.py` pehle → phir yeh doc + `PROJECT_HANDOFF.md` + landing/pricing HTML.

#### Trial ₹0 (7 din)
5 AI posts · 1 GBP audit · enquiry widget (+ AI chat) · mini-site preview · branded frames · portal 7d · WhatsApp basic · onboarding checklist · 1-click share · **no voice**

#### Starter ₹1,199/mo — poori list
Roz AI Hinglish posts (39 niches) · branded frames · customer portal (roz ~7 baje, WhatsApp share) · festival calendar · tyohar/offer posts · GBP audit + top 5 fixes · review reply drafts · 4 posters/mo · WhatsApp pack · UPI QR card · hashtags · post approval · onboarding dashboard · GST invoices · **100% marketing-only**

#### Growth ₹2,999/mo — Starter + yeh
Unlimited posters · AI image + Complete Post · A/B variations · content calendar/scheduler · competitor analysis · mini-site (bio/card/booking) · enquiry widget · AI chatbot · database reactivation · WhatsApp drip · review kit · team lead routing · CRM sync + webhooks · ads/reels + sentiment/hashtag · catalog + referral · monthly report · 2FA + hot leads

#### Advanced ₹6,999/mo — Growth + voice FEATURE
AI voice ~2-min inquiry callback · lead qualification · appointment booking · missed-call callback (DID) · 500 min/mo + top-ups · weekly 50 follow-ups · call transcripts + AI summary · post-call qualify · speed-to-lead SLA · multi-lingual · TRAI AI disclosure · ek portal (marketing + voice) · minute usage tracker

#### Customer deliverables SOP (kya client ko milta hai)
| Tier | Portal | Done-for-you (Isha daily) | Client action |
|------|--------|---------------------------|---------------|
| Trial | `/app/customer/marketing` 7d | 5 posts + 1 audit + widget setup | Copy/share posts · widget paste |
| Starter | portal + approvals | Roz content queue ~07:00 IST · 4 posters/mo · festival posts | Approve posts · copy to WA/Insta |
| Growth | + mini-site `/b/{slug}` · flows | + calendar · competitor report · drip drafts | Widget embed · team routing setup |
| Advanced | + calls/leads tabs | + inquiry callback (when telephony armed) | Review transcripts · follow hot leads |

**Honest limits (sales SOP):** Meta/GBP auto-publish blocked (human 1-click post). Advanced outbound voice needs Vobiz recharge + DLT for cold-call; inbound callback = marketing Advanced feature only.

### 1.4 Automation map — Marketing staff + IST schedule

**Staff:** Dev · Rohan · Isha · Ravi · Neha (+ platform Nikhil/Guru on shared jobs)

| Time | Job | Staff | Flags |
|------|-----|-------|-------|
| 06:30 | Blog / SEO | Ravi | — |
| 07:00 | Content packs | Isha | `USE_STRUCTURED_CONTENT` |
| 08:30 | Daily digest | Nikhil | — |
| 09:30 | Prospect / harvest | Rohan | `LEAD_HARVESTER`, `NICHE_ROTATION` |
| 10:30 | Email outreach + D3/D7 | Rohan | `AUTO_EMAIL_OUTREACH`, `EMAIL_WARMUP` |
| 11:00 | Pipeline rescore + hot | Neha | — |
| 14:30 | Midday prospect (2nd) | — | `MIDDAY_PROSPECT` |
| 16:00 | Afternoon followups | Neha | — |
| 18:30 | Evening wrap | — | — |
| Wed 12:30 | Weekly marketing packs | Isha | `WEEKLY_MARKETING_PACK` |
| Sat 04:00 | Hygiene DLQ+trim | — | — |
| Sun 05:00 | KB refresh | Dev | `KB_WEEKLY_REFRESH` |
| hourly | Reply triage · auto-onboard · ops | — | `REPLY_AGENT`, `AUTO_ONBOARD`, `OPS_WATCHDOG` |
| */15 | Growth pulse | — | `GROWTH_OPTIMIZER` |

**Always-on:** cadence · sales pipeline · channel experiments · Telegram auto-post · lead distribution · speed-to-lead · RFC8058 unsub.

### 1.5 SOP — Marketing revenue path

1. **Lead gen:** prospector/harvester auto (Maps/SearXNG). ToS-blocked scrape = CSV import only.
2. **Outreach:** Rohan 10:30, cap 25/day, MX + warmup. WhatsApp 1-click human only.
3. **Reply loop:** IMAP triage → draft → human send.
4. **Inbound:** widget/mini-site → `inquiry_hooks` → alerts + round-robin + optional callback.
5. **Signup:** `/start` → **UPI pay** (`/api/public/pay-info`) → admin activate → `/app/login`.
6. **Onboard:** `AUTO_ONBOARD` → KB + content pack + `/b/{slug}`.

### 1.6 Product 1 — current state (2026-06-20 LIVE)

| Item | Status |
|------|--------|
| Feature engines | ✅ Live |
| UPI payments | ✅ **LIVE** — `UPI_VPA=8459012607@axl` on VPS · `/api/public/pay-info` enabled |
| `ready_for_first_paid_customer` | ✅ true (activation summary) |
| Admin configure API | ✅ `POST /api/admin/upi/configure` (no recreate) |
| Speed-to-lead + round-robin | ✅ wired (`clientops`, customer portal) |
| Blocker for first ₹ | **Sales/ops only** — pehla customer acquire karo |

---

## PART 2 — PRODUCT 2: AI Voice Calling Agent (standalone)

### 2.1 Positioning
Full AI telecaller SKU — **ALAG product**, DLT-gated for **cold** outbound. Inbound callback = transactional (DLT-free path ready).

### 2.2 Features & pages

`/voice-agent` · `/app/test-call` (FREE tune) · `/app/dialer` · `/demo` · Vobiz WS stream.

Stack: `vobiz_stream.py` → STT/LLM/TTS → `post_call_hooks` → qualify → CRM/webhooks.

### 2.3 Pricing (`voice_packages.py`) — flat band, unlimited calls

| Band | Monthly | Annual (10×) |
|------|---------|--------------|
| A | ₹4,999 | ₹49,990 |
| B | ₹9,999 | ₹99,990 |
| C | ₹19,999 | ₹1,99,990 |

Pilot: 7 din / 50 calls free. Niche→band: `lead_band()` in `niches.py`.

### 2.4 Automation — Voice staff + jobs

**Staff:** Swara · Arjun · Meera · Tara

| When | Job | Flag |
|------|-----|------|
| 02:30 | Voice QA (`agent_tester.py`) | `VOICE_EVAL_AUTO` |
| 03:00 | Trainer + ML | `ML_NIGHTLY_TRAINING` |
| hourly | Telephony readiness | — |
| per-call | Post-call qualify + meter | `AUTO_QUALIFY_CALLS` |
| on-inquiry | Inbound callback path | `AUTO_CALLBACK_INQUIRY` |
| on inbound WS | Vobiz inbound webhook | wired |
| manual | `fire_calls.py` campaign | TRAI 10–7 gate |

**Cross-path:** `cross_path_audit.py` in `final_integration_check` — vobiz + legacy paths parity.

### 2.5 SOP — Voice go-live path

1. Tune on `/app/test-call` (free).
2. `agent_tester.py` after any prompt/voice change.
3. When unblocked: Vobiz DID + DLT → 1 live call → dialer disposition check.
4. Compliance gates = non-negotiable.
5. Recordings: `VOBIZ_CALL_RECORD=1` → admin player.

### 2.6 Product 2 — blockers (USER-action)

| Blocker | Action |
|---------|--------|
| **DLT** | Udyam cert → Proprietorship re-apply |
| **Vobiz** | Recharge + DID → `VOBIZ_CALLER_ID` |
| **Human transfer** | `CALL_TRANSFER=1` + DID (explorer `gap_transfer`) |

Code = production-ready. Phone outbound = untestable till above.

---

## PART 3 — Master Automation Table (cross-product)

Explorer automation view + PART 0–2 merged. Status = designed ON on VPS unless noted.

| # | Automation | P | Flag | Schedule |
|---|------------|---|------|----------|
| 1 | Blog / programmatic SEO | M | — | 06:30 |
| 2 | Content + approval + distribute | M | `USE_STRUCTURED_CONTENT` | 07:00 |
| 3 | Lead harvester / niche prospect | M | `LEAD_HARVESTER`, `NICHE_ROTATION` | 09:30, 14:30 |
| 4 | Email outreach + RFC8058 unsub | M | `AUTO_EMAIL_OUTREACH`, `EMAIL_WARMUP` | 10:30, 16:00 |
| 5 | Pipeline ops (Neha) | M | — | 11:00, 16:00 |
| 6 | Reply triage | M | `REPLY_AGENT` | hourly |
| 7 | Auto-onboard + FDE | M | `AUTO_ONBOARD` | hourly |
| 8 | Journey + cadence | M | `JOURNEY_ENGINE`, `CADENCE_ENGINE` | event |
| 9 | Lead round-robin + STL | M | — | on inquiry |
| 10 | Sales + revenue ops | M/P | `SALES_TEAM`, `DUNNING_ENGINE` | daily |
| 11 | Growth optimizer + channel bandit | M | `GROWTH_OPTIMIZER`, `CHANNEL_EXPERIMENTS` | */15 / hourly |
| 12 | KB weekly refresh | M | `KB_WEEKLY_REFRESH` | Sun 05:00 |
| 14 | SEO rank + review monitor | M | `RANK_TRACKER`, `REVIEW_MONITOR` | daily |
| 15 | CRM sync | M | `CRM_SYNC` | **OFF** |
| 16 | WhatsApp auto | M | `WHATSAPP_AUTO_SEND` | **OFF** (1-click) |
| 17 | Voice QA + trainer | V | `VOICE_EVAL_AUTO`, `ML_NIGHTLY_TRAINING` | 02:30, 03:00 |
| 18 | Telephony readiness | V | — | hourly |
| 19 | Post-call hooks | V | `AUTO_QUALIFY_CALLS` | per call |
| 20 | Inbound callback / Vobiz inbound | V | `AUTO_CALLBACK_INQUIRY` | on trigger |
| 21 | Outbound fire_calls campaign | V | — | manual |
| 22 | Self-improve loop | P | `SELF_IMPROVE_LOOP` | 180s |
| 23 | Process engine + autostart + approvals | P | `PROCESS_ENGINE`, `PROCESS_AUTOSTART` | 11:30 |
| 24 | Code upgrader + skill pack | P | `CODE_UPGRADER`, `SKILL_PACK` | hourly / daily |
| 25 | Ops watchdog + automation health | P | `OPS_WATCHDOG`, `LOOP_SUPERVISOR` | hourly |
| 26 | SRE / FinOps / Security KPI agents | P | `SRE_AGENT`, `FINOPS_AGENT`, `SECURITY_AGENT` | daily |
| 27 | Meter watch + customer webhooks | P | `METER_ALERTS`, `CUSTOMER_WEBHOOKS` | hourly / event |
| 28 | Hygiene + backups | P | — | Sat 04:00 / ~04:00 |

**Live flags:** `GET /api/growth/infra/flags` · **Job parity:** `prod_check` automation-gaps · **24 staff jobs** Celery-wired.

---

## PART 4 — Cheat Sheet

```
LIVE        : https://leadsgenai.in
EXPLORER    : https://leadsgenai.in/app/explorer  (4 views — start here)
HEALTH      : curl /health  → environment:production
ACTIVATION  : GET /api/activation/summary  → paid_ready, blockers
FLAGS       : GET /api/growth/infra/flags
REPO/VPS    : github.com/sumitrevolt/leadgenrationaivoiceagent · root@72.61.245.204 /opt/leadgen
DEPLOY      : prod_check → tests → push → VPS pull+build+recreate (+ worker if automation)
CI          : GATE-ONLY — manual SSH
PRICING     : packages.py (M) · voice_packages.py (V)

PRODUCT 1   : ✅ sellable · UPI LIVE · staff Dev/Rohan/Isha/Ravi/Neha
PRODUCT 2   : code-ready · BLOCKED DLT+Vobiz · staff Swara/Arjun/Meera/Tara
PLATFORM    : Boss/Kavya/Hermes/Nikhil/Vikram/Guru/Pranav/Vidya/Arnav + self-improve

PAYMENTS    : manual UPI primary (8459012607@axl LIVE) · Stripe intl · Razorpay REMOVED
AI          : Mistral · Groq STT · EdgeTTS · Qdrant · Vobiz
DOCS        : docs/ENTERPRISE_DOC_INDEX.md · docs/PROJECT_HANDOFF.md · docs/PROJECT_SOP.md
```

---

## Appendix — detail pointers

| Doc | Purpose |
|-----|---------|
| [`ENTERPRISE_DOC_INDEX.md`](ENTERPRISE_DOC_INDEX.md) | 10-doc enterprise pack map |
| [`PROJECT_HANDOFF.md`](PROJECT_HANDOFF.md) | Exhaustive 20-section handoff |
| [`PROJECT_SOP.md`](PROJECT_SOP.md) | Engineering + business SOP |
| [`AUTOMATION.md`](AUTOMATION.md) | Loop decision tree |
| [`WORKFLOW_MAPS.md`](WORKFLOW_MAPS.md) | Mermaid pipelines |
| [`AGENT_REGISTRY.md`](AGENT_REGISTRY.md) | Full staff I/O |
| `frontend/explorer.html` | **Live graph source** — edit here when adding nodes |
| `scripts/explorer_sync.py` | Graph↔code drift audit |

*Conflict: CLAUDE.md > yeh doc > purane docs. Pricing: packages.py / voice_packages.py authoritative.*
