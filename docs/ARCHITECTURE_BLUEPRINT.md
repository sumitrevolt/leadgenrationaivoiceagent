# LeadGen AI — Complete Architecture Blueprint

> **STALE narrative topology (kept for human orientation).** Canonical Master Blueprint counts come from `app.platform.blueprint_graph.validate_graph()` — as of 2026-08-03: **59 nodes · 56 edges · 11 flows · 0 orphans · workforce 31**. Explorer/prod_check numbers below may lag; do not treat this file as the count authority.
> Live: https://leadsgenai.in | Health truth: direct HTTPS `/health.version` only

---

## SYSTEM TOPOLOGY — Structural View (illustrative — not node-count authority)

```
┌─ INTERNET ───────────────────────────────────────────────────────────┐
│                                                                      │
│  ┌──────────────────┐    HTTPS     ┌───────────────────────┐        │
│  │ Browser / Client │──────────────│ Caddy TLS Edge Proxy   │        │
│  │ + external APIs  │              │ HTTPS→127.0.0.1:8000   │        │
│  └──────────────────┘              └───────────┬───────────┘        │
│                                                │                    │
│         ┌──────────────────────────────────────┼──────────────┐     │
│         │          Hostinger VPS Mumbai        │              │     │
│         │  72.61.245.204 · Docker 13+ containers│              │     │
│         └──────────────────────────────────────┴──────────────┘     │
└──────────────────────────────────────────────────────────────────────┘

────────────────────────────── FRONTEND LAYER ─────────────────────────────
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Public Pages │ │ Admin UI     │ │ Cust Portal  │ │ Embed Widget │
│  /audit      │ │ /app/admin   │ │ /app/login→  │ │ /b/{slug}/   │
│  /pricing    │ │ /app/auto-   │ │  /app/cust   │ │  widget.js   │
│  /blog       │ │   mation     │ │ TOTP 2FA     │ │ inquiry→lead │
│  /compare    │ │ /app/owner   │ │ content appr │ │ distribution │
│  /voice-agnt │ │ /app/explr   │ │ webhooks     │ │              │
│ ~45 pages    │ │ /app/office  │ │              │ │              │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                │                │
       ▼                ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Auth & RBAC Layer                              │
│  Admin JWT · Customer JWT · /app/team-access module RBAC        │
│  consent ledger · TOTP 2FA · impersonation (gated)              │
└───────────────┬─────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────┐
│              Tenant White-Label Middleware                       │
│  Subdomain/custom domain → client branding · FAIL-OPEN apex     │
└───────────────┬─────────────────────────────────────────────────┘
                │
─────────────────▼─────── BACKEND MONOLITH ────────────────────────────
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Monolith                              │
│  ~1150 routes · uvicorn WEB_CONCURRENCY=2 · WS + SSE            │
│  PlanTierRateLimitMiddleware (Starter 60rpm/Growth 200rpm)      │
│  CORS · Sentry · PostHog · OTel (off)                           │
└──────┬──────────┬──────────┬──────────┬──────────┬──────────────┘
       │          │          │          │          │
       ▼          ▼          ▼          ▼          ▼
┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐
│Billng│ │Lanch│ │MCProd│ │Compl │ │Integ│ │Admin│ │Social│
│+Usage│ │Gate  │ │uct   │ │iance │ │Gate │ │Ops  │ │OAuth │
└──┬───┘ └──────┘ └──────┘ └──┬───┘ └──────┘ └──┬───┘ └──────┘
   │                          │                  │
   │    ┌─────────────────────┘                  │
   ▼    ▼                                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DATA LAYER                                  │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌──────────────────┐ │
│  │ Postgres  │ │ Redis x2  │ │  Qdrant   │ │  MinIO S3 (opt)  │ │
│  │+PGBouncer│ │ (broker+  │ │ kb_main + │ │  local-disk      │ │
│  │ :6432     │ │  cache)   │ │ namespces │ │  fallback        │ │
│  └───────────┘ └───────────┘ └───────────┘ └──────────────────┘ │
│  ./data/ → jsonl files (prospects, inquiries, clients, content) │
└─────────────────────────────────────────────────────────────────┘

───────────────────── AI / VOICE STACK ──────────────────────────────────
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ 17 AI Staff  │ │ Voice Brain  │ │ Voice Product│ │ Telephony Hub│
│ Boss·Isha·   │ │ Vobiz WS →   │ │ Standalone   │ │ Vobiz active │
│ Rohan·Swara· │ │ Groq STT →   │ │ SKU /voice-  │ │ Twilio fallbk│
│ Kavya·FDE·   │ │ RAG → LLM →  │ │ agent · band  │ │ call state   │
│ Pranav·Vidya │ │ EdgeTTS      │ │ ABC pricing   │ │ Redis · AMD  │
│ Arnav·Arjun  │ │ web-call     │ │ niche scripts │ │ voicemail    │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                │                │
       ▼                ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│               Free AI Provider Chain                             │
│  Mistral (primary) → Groq (fallback STT+LLM) → Cerebras →       │
│  Gemini (voice, 9-key pool) → NVIDIA/SambaNova (deep-tail)      │
│  429 circuit-breaker escalating (60s→30min)                     │
└─────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│              RAG / Knowledge Base (Qdrant)                       │
│  kb_main · niche:<key> · client:<id> · skills (250)             │
│  agentic RAG opt-in (Hybrid + OKF curated)                      │
└─────────────────────────────────────────────────────────────────┘

─────────────────────── BACKGROUND / AUTOMATION ───────────────────────
┌─────────────────────────────────────────────────────────────────┐
│                     Celery Queue System                          │
│  Beat scheduler (IST) → Redis broker → Worker × 4               │
│  leadgen_worker · worker_heavy · worker_video · scheduler       │
│  ~37 scheduled jobs · DLQ :20 sweep · acks_late=False           │
└───────────────┬─────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Flow Runner                                  │
│  Visual builder (/app/explorer) → process-as-code execution     │
│  FLOW_RUNNER gated · linear + DAG (branch/merge/conditions)     │
│  flow_store · flow_compiler · dag_engine · flow_dispatch        │
│  flow_triggers · flow_http · customer_flows · growth_process    │
└─────────────────────────────────────────────────────────────────┘

─────────────────────── MONITORING ────────────────────────────────────
┌─────────────────────────────────────────────────────────────────┐
│                   Monitoring Stack                               │
│  Prometheus · Grafana · Loki · Tempo · ntfy · Flower            │
│  Sentry (error tracking) · PostHog (analytics)                  │
│  Cross-Path Audit (telephony lifecycle parity)                  │
│  Final Integration Check (wiring + deep_wiring + smoke)         │
│  Architecture Explorer Sync (85/85 engines, 0 orphans)          │
└─────────────────────────────────────────────────────────────────┘

─────────────────────── EXTERNAL ───────────────────────────────────────
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ Vobiz    │ │Hostinger │ │GoogleMaps│ │Pollinations│ │SearXNG  │
│Telephony │ │SMTP/IMAP │ │Places    │ │AI Images  │ │Websearch │
└──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│HubSpot   │ │ Zoho CRM │ │ WhatsApp │ │ Stripe   │ │ Postiz   │
│(intl)    │ │ (India)  │ │WAHA:3111 │ │(intl)    │ │(social)  │
└──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
```

---

## AUTOMATION VIEW — 85 engine modules (all green)

| Engine | Type | Schedule | Purpose |
|--------|------|----------|---------|
| **self_improve** | AI loop | every 180s | Continuous pick→exec→learn→requeue |
| **growth_engine** | AI loop | every 15min | Quantity heal (prospecting + outreach) |
| **growth_optimizer** | AI loop | daily | Strategy/weakest-stage optimization |
| **process_tick** | Platform | every 10s | Running flow processes advance |
| **prospector** | Platform | daily/hourly | Google Maps lead harvest |
| **auto_outreach** | Marketing | daily | Email outreach + follow-ups |
| **reply_agent** | Platform | hourly | IMAP inbox → reply triage + drafts |
| **whatsapp_campaign** | Marketing | on-demand | WA campaign drafts (1-click send) |
| **auto_content** | Marketing | daily | AI content generation per client |
| **seo_blog** | Marketing | daily | Programmatic SEO blog posts |
| **social_engine** | Social | daily | Postiz auto-publish (5 channels) |
| **customer_delivery** | Marketing | weekly | Delivery sweep + weekly digests |
| **client_report** | Marketing | monthly | Monthly client reports |
| **kb_refresh** | Platform | weekly | Qdrant KB per-niche refresh |
| **team_scheduler** | Platform | IST-aligned | 37 scheduled jobs dispatcher |
| **trainer** | AI | nightly | Auto-train voice agent models |
| **qa** | Voice | on-demand | Voice self-test QA suite |
| **ops_watchdog** | Platform | hourly | Health + dead-man checks |
| **telephony_readiness** | Voice | hourly | Vobiz balance + trunk status |
| **automation_health** | Platform | daily | All-job heartbeats dashboard |
| **lead_harvester** | Platform | daily | Harvest + score + dedup leads |
| **sales_pipeline** | CRM | daily | Deals progression + hot-leads |
| **cadence** | CRM | daily | Timed follow-up sequence engine |
| **journeys** | CRM | on-trigger | Rule-based omnichannel journeys |
| **booking** | Platform | on-demand | Calendly-lite booking system |
| **brand_pulse** | Marketing | weekly | Online presence/reputation scan |
| **review_monitor** | Marketing | daily | Review monitoring + AI replies |
| **eval_gate** | AI | daily | DeepEval close-the-loop reward |
| **rl_flywheel** | AI | daily | RL self-improvement reward spine |
| **code_upgrader** | AI | daily | Code patch proposals (draft-safe) |
| **engineer_agents** | Platform | daily | SRE/FinOps/Security daily runs |
| **office_briefing** | Platform | daily | Morning briefing (LLM + TTS) |
| **dunning** | Billing | daily | Payment retry + expiration |
| **winback** | Billing | daily | Churned customer reactivation |
| **usage_alerts** | Billing | daily | Meter cap warnings |
| **payment_recon** | Billing | daily | UPI/Stripe reconciliation |
| **monthly_receipt** | Billing | monthly | GST receipt sweep |
| **lifecycle_nurture** | Marketing | daily | Nurture + re-engagement |
| **newsletter** | Marketing | weekly | Client newsletter compose |
| **content_schedule** | Marketing | daily | Scheduled content publish |
| **festival_autoschedule** | Marketing | on-festival | Festival post auto-queue |
| **team_report** | Marketing | weekly | Weekly team story + stats |
| **client_health** | Platform | daily | Client health score + risk |
| **deliverability** | Platform | daily | Email deliverability monitor |
| **pipeline_ops** | Platform | daily | Pipeline hygiene + cleanup |
| **scheduled_ops** | Platform | evening/weekly | Wrap-up + weekly marketing |
| **customer_autopilot** | Platform | daily | Auto-onboard sweep |
| **dlq_retry** | Platform | hourly :20 | Dead-letter queue retry |
| **infra_handler** | Platform | hourly | Hermes infra scanner |
| **integration_health** | Platform | hourly | Integration probe |
| **obsidian_sync** | Platform | nightly | Brain-vault sync |
| **memory_vault** | Platform | on-demand | Compounding prospect memory |
| **call_prep** | Platform | on-demand | Pre-call brief builder |
| **live_eval** | AI | nightly | Real transcript quality eval |
| **post_call_hooks** | Voice | per-call | Meter+qualify+report after call |
| **call_analytics** | Voice | daily | Call KPIs (Lekha) |
| **voice_followup** | Voice | on-demand | Post-call follow-up workflows |
| **voice_launch** | Voice | gated | Controlled outbound call campaign |
| **platform_dial** | Voice | LIVE (supersedes HARD OFF — 2026-08-02; per-run cap `PLATFORM_DIAL_LIMIT`=100, boolean `PLATFORM_DIAL_DAILY`) | Self-sale daily campaign |

---

## DATA CONTRACTS — Key API domains

| Domain | Prefix | Routes | Auth | Purpose |
|--------|--------|--------|------|---------|
| Admin Core | /api/admin/* | ~80 | require_admin | User mgmt, audit logs, settings |
| Admin Dashboard | /api/admin/* | ~30 | require_admin | KPIs, clients, delivery, revenue |
| Admin Ops | /api/admin/* | ~40 | require_admin | Campaign, UPI, voice, trust, system |
| Owner OS | /api/admin/owner-os/* | 30 | require_admin | Command console, agents, kills |
| Billing | /api/billing/* | ~20 | Mixed | Plans, subscription, invoices, usage |
| Customer Dashboard | /api/customer/* | ~50 | require_customer | Portal, delivery, GMB, profile |
| Customer Marketing | /api/customer/studio/* | ~90 | require_customer | AI content tools (91 endpoints) |
| Growth | /api/growth/* | ~100 | Mixed | Leads, scoring, outreach, cadence |
| Marketing | /api/marketing/* | ~30 | Mixed | Posts, images, chatbots, calendar |
| Platform | /api/platform/* | ~15 | Mixed | Team, office, tenants |
| Public Site | /api/public/* | ~10 | None | Inquiry, audit, signup, AI demo |
| Voice AI | /api/voice/* /api/voiceai/* | ~20 | Mixed | Packages, quota, transfer, ask-AI |
| Agents | /agents/* /api/agents-ext/* | ~30 | require_admin | Supervisor, council, code-exec |
| Telephony | /api/telephony/* | ~10 | Mixed | Vobiz webhooks, stream, SIP |
| Events | /api/events/* | ~5 | Mixed | SSE real-time feed |
| Integrations | /api/{wa,hubspot,zoho,whatsapp}/* | ~30 | Mixed | External connector APIs |
| MCP Product | /api/mcp-product/* /mcp | ~15 | Token/allowlist | MCP server + A2A |

---

## FRONTEND PAGE MAP — 48 pages (0 wiring gaps)

```
PUBLIC (no auth):
  / /pricing /start /audit /site-audit /demo /blog /b/{slug}
  /geo-check /compare /voice-agent /privacy /terms /refund
  /app/login /status /robots.txt /sitemap.xml

CUSTOMER (lgai_token):
  /app/customer[/marketing|voice|flows|pipeline|office]

ADMIN (accessToken):
  PRIMARY:  /app/admin (Full Console) /app/owner (Owner OS)
            /app/delivery-command-center /app/clients
  COCKPITS: /app/automation (Mission Control) /app/office (HQ Map)
            /app/control-center (Enterprise CC) /app/agent-tools (Dev)
  INTERNAL: /app/explorer /app/marketing /app/studio /app/calendar
            /app/outreach /app/inbox /app/conversations /app/dialer
            /app/deals /app/journeys /app/segments /app/growth-tools
            /app/whatsapp /app/minisite-builder /app/onboard
            /app/team /app/agents /app/brain /app/assistant
            /app/team-access /app/voice-keys /app/analytics
            /app/dashboards /app/ops /app/battlecard
            /app/test-call /app/impersonate /app/dev-control
            /app/admin-login /app/admin/db
```

---

## INFRA CONTAINERS (docker-compose.vps.yml)

```
leadgen_app          :8000 (host) / :8080 (in-network)  — FastAPI
leadgen_worker       :—        — Celery worker (default queue)
leadgen_worker_heavy :—        — Celery worker (heavy jobs: qa, training)
leadgen_worker_video :—        — Celery worker (video generation)
leadgen_scheduler    :—        — Celery beat (IST timezone)
leadgen_db           :5432     — Postgres 15
pgbouncer            :6432     — Connection pooler
leadgen_redis        :6379     — Redis (broker + call-state + DLQ)
redis-cache           :6380    — Redis (read cache)
qdrant               :6333     — Vector DB (RAG)
leadgen_postiz       :5000     — Social publisher
leadgen_waha         :3111     — WhatsApp HTTP API
+ observability stack (Prometheus, Grafana, Loki, Tempo, Alertmanager, Uptime, Gatus)
```

---

## CRITICAL PATHS — Money flow

```
Landing → /audit (free lead magnet) → inquiry → /pricing →
/start (signup) → UPI QR manual pay → admin /api/admin/upi/activate →
plan activated → JWT issued → /app/customer → content delivery →
approvals → published → client dashboard
```

## CRITICAL PATHS — Voice call flow

```
Prospect list → compliance gate (DND+time+consent) → Vobiz place call →
WS stream → Groq STT (PCM16→text) → TelecallerBrain (LLM+RAG) →
EdgeTTS (text→mp3) → Vobiz play → post_call_hooks
(record_disposition + meter + qualify)
```
