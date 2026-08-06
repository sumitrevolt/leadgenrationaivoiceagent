# Roadmap 2026 — Production-Ready + Full-Automation + Revenue Engine
**Project:** leadsgenai.in (LeadGen + AI Voice + Marketing Automation)
**Date:** 2026-06-09 · **Focus (user priority):** Deeper Automation → Revenue Systems → Production Hardening
**Constraint:** FREE stack only (no paid STT/TTS/LLM). Single Hostinger VPS (Mumbai, Docker).
**Rule:** Rebuild MAT karo — grep pehle. Test→deploy loop follow karo. Live prod safe rakho.

---

## 0) TL;DR (1-minute read)

Tumhara code **already prod-grade** hai (FastAPI + Postgres + Redis + Docker live, Sentry + Prometheus + /health/ready, 278 routes, 27 test files, Celery worker built). Gap **code me nahi — DEPLOYMENT + AUTOMATION GLUE + REVENUE LOOP me** hai. 3 cheezein project ko "completely automated revenue process" banati hain:

1. **Revenue loop band hai** — self-serve signup→pay→provision page NAHI hai (sirf `login.html` + `customer_dashboard.html`; koi `pricing/signup/checkout` page nahi). Payment modal dormant (UPI_VPA unset), Stripe/Razorpay webhook **built hai par keys unset**. Yeh #1 paisa-blocker.
2. **Automation durable nahi hai** — pipelines APScheduler in-process (single-point) + `.jsonl` best-effort pe chalti hain. App restart pe job double/miss ho sakta. Koi durable retry/checkpoint nahi. Celery built hai par active path nahi.
3. **Deploy + observability manual** — CI auto-deploy `DEPLOY_ENABLED` pe gated (OFF), stale `.pyc` hard-reload manual, OTel tracing app-level nahi, alerting sirf email-watchdog.

**Strategy:** Pehle ek chhota **Foundation (Phase 0)** — CI auto-deploy + durable scheduler + backup/DR + alerting. Fir **Revenue loop (Phase 1)** band karo (yeh turant paisa). Fir **Deep automation (Phase 2)**. Heavy naya infra mat add karo — jo hai (Celery/Redis/Postgres) usko harden karo, sirf 2-3 light free tools add karo.

| # | Track | Sabse bada gap | Pehla fix | ROI |
|---|-------|----------------|-----------|-----|
| A | **Revenue** | Self-serve signup→pay→provision missing; payments dormant | Pricing/checkout page + payment go-live + dunning | 🟢🟢🟢 |
| B | **Automation** | Pipelines in-process + jsonl, no durable retry | Celery harden → durable jobs → AI SDR reply-to-book loop | 🟢🟢🟢 |
| C | **Hardening** | CI gated, scheduler single-point, no PITR, no tracing | Auto-deploy + Barman PITR + OTel + Alertmanager | 🟢🟢 |

---

## 1) Current State — kya already strong hai (REBUILD MAT KARO)

Yeh sab confirmed hai (code survey + CLAUDE.md). Inhe dobara mat banao:

- **Infra:** Dockerized live — `leadgen_app:8000` + Postgres `leadgen_db` + Redis `leadgen_redis`, Caddy TLS host-proxy, `restart: unless-stopped`. Rollback 2-level (systemd + SQLite). Nightly `pg_backup.sh` cron.
- **Observability (partial):** Sentry wired (FastAPI/Celery/Redis/SQLAlchemy integrations), Prometheus `/metrics`, `/health/ready` (db+redis). `deploy/compose/docker-compose.observability.yml` (Prometheus+Grafana+Uptime Kuma) opt-in.
- **AI stack (free):** Cerebras→Groq→OpenRouter→Gemini LLM chain + circuit-breaker; EdgeTTS; Groq Whisper STT; Qdrant RAG (multi-model embed fallback); faster-whisper local.
- **Automation built:** Celery `app/worker.py` exists; APScheduler in-process (8 AI-staff jobs IST-scheduled); reply-agent, ops-watchdog, auto-onboard, growth-pulse all coded + gated.
- **Revenue built (dormant):** `app/api/billing.py` (Stripe 8 refs + Razorpay 11 refs, webhooks), `usage.py` minute-metering + enforcement, packages ₹999/2499/5999, customer-auth JWT portal, mini-site builder.
- **Lead-gen built:** Google Maps Places API live, email outreach (Hostinger SMTP, MX-verify, SPF/DKIM/DMARC set), prospector→DB, IMAP reply-triage.
- **Tests:** 27 files, prod_check 278 routes, pytest ~80+ green.

> **Takeaway:** 80% machinery already hai. Kaam = **wiring + go-live + durability**, naya banana nahi.

---

## 2) Gap Analysis — "kya kamiya hai" (prioritized)

### 🔴 P0 — Production-ready + revenue ke liye BLOCKERS

| Gap | Detail | Impact |
|-----|--------|--------|
| **Self-serve revenue flow missing** | Koi public `pricing→signup→checkout→auto-provision` page nahi. `frontend/` me sirf `login.html`, `customer_dashboard.html`. | Paisa manually hi aata hai. Scale = 0. |
| **Payments dormant** | `UPI_VPA` unset → pay-modal `enabled:false`. Stripe/Razorpay keys unset → webhooks inert. | Customer chahe bhi self-pay nahi kar sakta. |
| **CI auto-deploy OFF** | `deploy-vps.yml` `if: vars.DEPLOY_ENABLED == 'true'` (unset). Deploy = manual SSH + manual hard-reload (stale `.pyc` gotcha). | Har deploy risky + slow + human-dependent. |
| **Scheduler single-point** | `RUN_IN_PROCESS_SCHEDULER=1` APScheduler in app process. Restart/crash pe jobs miss/double. No durable retry. | Automation reliable nahi — "fire and forget". |
| **No PITR / tested restore** | `pg_dump` nightly hai par WAL-archiving/point-in-time recovery nahi; restore-drill kabhi test nahi. | Data-loss window = 24h. DR untested. |

### 🟠 P1 — Automation depth + reliability

| Gap | Detail | Impact |
|-----|--------|--------|
| **Pipelines durable nahi** | outreach/onboarding/content `.jsonl` + best-effort. No checkpoint, no idempotent retry, no dead-letter. | Failure pe silently drop. |
| **App-level tracing nahi** | OTel sirf `voice_agent/observability.py` me; FastAPI request→DB→LLM end-to-end trace nahi. | Slow/failed request ka "kyun/kahan" pata nahi. |
| **Alerting weak** | Sirf email ops-watchdog. No Alertmanager rules (error-rate, p95 latency, queue-depth, payment-fail). | Problem customer-se-pehle nahi pakadte. |
| **No reply→book→pay closed loop** | reply-agent intent classify karta, par auto demo-book + payment-link send + onboard tak chain nahi. | Hot lead manual follow pe atakta. |
| **Conversion analytics nahi** | `/app/analytics` admin KPIs hai par funnel/activation/churn product-analytics nahi. | Kya optimize karna pata nahi. |

### 🟡 P2 — Scale + polish (baad me)

| Gap | Detail |
|-----|--------|
| No load/capacity testing (Locust/k6) — concurrency limit unknown. |
| Secrets sirf `.env` (no SOPS/vault) — solo OK, team-scale gap. |
| Coverage gate CI me nahi (`--cov-fail-under` absent). |
| Multi-worker scale OFF (`WEB_CONCURRENCY=1`, single uvicorn). |
| Voice: custom pipeline; Pipecat/LiveKit migration optional (tumne prioritize nahi kiya). |

### ⛔ External blockers (CODE se fix NAHI hote — paperwork/approval)

- **DLT** (cold-calling Advanced tier) — Udyam cert se re-apply pending.
- **Vobiz** telephony recharge + DID — trial khatam.
- **Meta/FB-IG + GBP API** auto-post — app-review/60-din approval.

> In par token mat jalao jab tak unlock na ho. Inhe roadmap me "gated, ready-to-flip" rakho.

---

## 3) Recommended Stack — kya ADD karein (FREE, GitHub repos ke saath)

**Philosophy:** Single VPS pe heavy naya infra (Temporal 4GB / PostHog ClickHouse+Kafka 16GB) mat thopo. Jo hai (Celery/Redis/Postgres) harden karo + sirf **light free tools** add karo. Heavy cheez chahiye to **managed free-tier** use karo (PostHog Cloud 1M events free, Grafana Cloud free) — self-host RAM bachao.

### A. Durable jobs / workflow engine

| Option | Kab use karo | RAM | Repo |
|--------|--------------|-----|------|
| **Celery + Redis (already hai) — HARDEN** | ✅ Default. Beat scheduler + result backend + `acks_late` + autoretry + dead-letter. Naya dep zero. | ~0 extra | (built-in `app/worker.py`) |
| **Windmill** (later, ops-glue) | Python-native scripts→durable workflows + UI + cron. Checkpoint retry <5s. Light (Postgres-backed). | ~512MB–1GB | `windmill-labs/windmill` |
| **Temporal** | Sirf agar mission-critical multi-step exact-once chahiye (overkill abhi). | 4GB+, 4 containers | `temporalio/temporal` |
| **n8n** | Visual glue agar non-dev workflows chahiye (400+ nodes). | 256MB | `n8n-io/n8n` |

**Decision:** Phase-0 me **Celery harden** (zero new infra). Phase-2 me agar business-ops glue chahiye to **Windmill** (Python + light + tumhare stack se match).

### B. Observability (3 pillars) — tumhare Sentry/Prometheus ke upar

- **OTel auto-instrumentation** → FastAPI request→DB→LLM→TTS end-to-end trace. Deps: `opentelemetry-instrumentation-fastapi`, `-sqlalchemy`, `-redis`, `-httpx`.
- **LGTM stack** (Loki logs + Grafana + Tempo traces + Prometheus) — tumhare `deploy/compose/docker-compose.observability.yml` me Loki+Tempo add karo, ya light `grafana/otel-lgtm` all-in-one image.
- **Reference repos (copy-paste grade):** `blueswen/fastapi-observability`, `googollee/fastapi-observability-otel`, `TechWithTy/fastapi-loki-observability`. Grafana dashboard ID **16110** (FastAPI Observability).
- **Alerting:** Prometheus **Alertmanager** rules (error-rate >2%, p95 >2s, Celery queue-depth, payment-webhook-fail, disk >80%) → email/Telegram. Uptime Kuma already hai (uptime).
- **VPS-light alternative:** Grafana Cloud free tier (10k series, 50GB logs) — self-host RAM bachega.

### C. Revenue / billing automation

- **Dunning + smart-retry:** Razorpay Subscriptions me built-in dunning + retry ON karo (tum India-first ho). Stripe side **Smart Retries** (failure-type + issuer + time-of-day signals → 60–80% recovery vs 20–30% basic). Dunning = retry + email + in-app + WhatsApp reminder. Industry: failed-payment se ~9% MRR loss; dunning se 70% recover.
- **Self-serve checkout:** Razorpay Payment Links / Checkout (India UPI+card) — webhook already built (`/api/billing/webhooks/razorpay`) → `usage.activate_plan()`. Bas keys + ek pricing/checkout page.
- **Concept refs:** Stripe Revenue Recovery docs, Baremetrics/Churnbuster dunning playbook (sirf logic copy, tool nahi).

### D. Product / conversion analytics

| Option | Fit | RAM | Repo |
|--------|-----|-----|------|
| **PostHog Cloud (free 1M events/mo)** | ✅ Best — funnels, retention, session replay, feature flags, A/B. Self-host heavy (ClickHouse+Kafka) → **Cloud free** lo. | 0 (managed) | `PostHog/posthog` |
| **Umami** (self-host) | Light web-analytics, Postgres-backed (tumhare DB me fit). Privacy-first. | ~128MB | `umami-software/umami` |
| **Metabase** | Postgres pe direct BI dashboards (tumhare leads/billing tables pe). | ~1GB | `metabase/metabase` |

**Decision:** **PostHog Cloud free** (funnel/activation) + **Metabase** self-host (internal revenue BI on Postgres).

### E. Lead-gen / AI SDR automation (free, defensive)

- **AI SDR loop refs:** `MatthewDailey/open-sdr` (research + outbound + MCP server), `iPythoning/b2b-sdr-agent-template` (10-stage pipeline, multi-channel WA+email+Telegram, cron), `Salesably/awesome-ai-agents-for-sales` (curated). Pattern lo — tumhare free-LLM chain pe chalao, naya paid tool nahi.
- **Email infra (already strong):** Mautic/Listmonk sirf tab agar volume bahut badhe; abhi Hostinger SMTP + MX-verify kaafi. `PaulleDemon/Email-automation` (Django+Celery sequences) = followup-logic reference.

### F. Backup / DR (Postgres)

- **PITR:** `pg_dump` se upgrade → **Barman** (Python, EnterpriseDB-backed, naye deployments ke liye recommended) ya **WAL-G** (strong all-rounder, cloud-native). pgBackRest kaam karta hai par **Apr 2026 se unmaintained** — naya mat chuno.
- **Offsite:** tumhare `pg_backup.sh` me rclone R2/B2 hook already hai — WAL archiving add karke PITR enable karo.
- **Drill:** monthly automated **restore-test** (alag container me restore → row-count verify). Untested backup = no backup.

### G. Voice (OPTIONAL — tumne prioritize nahi kiya)

- `pipecat-ai/pipecat` (v1.0 Apr 2026, 10k★, pipeline-clarity) ya `livekit/agents` (~9.2k★, WebRTC low-latency). Migration bada kaam — abhi tumhara custom pipeline + Phase-3 turn-detector kaafi. Future note.

---

## 4) Phased Build Plan (effort: S=½–1 din, M=2–4 din, L=1+ hafta)

### ⚙️ PHASE 0 — Foundation (yeh sab ke neeche; chhota par critical) · ~3–5 din

Yeh ROI-multiplier hai: iske bina automation + revenue dono unreliable rahenge.

1. **CI auto-deploy ON** *(S)* — `DEPLOY_ENABLED=true` repo-var + secrets (VPS_HOST/USER/SSH_KEY/GHCR_PAT). `deploy-vps.yml` already GHCR→SSH ready. **Stale-`.pyc` fix build-step me bake karo** (deploy ke baad `find app -name __pycache__ -prune -exec rm -rf` + hard restart) — manual gotcha khatam.
2. **Durable scheduler** *(M)* — APScheduler in-process se **Celery Beat** pe move (worker already hai). `acks_late=True`, `task_autoretry_for`, max-retries + exponential backoff, **dead-letter queue**. `RUN_IN_PROCESS_SCHEDULER=0` + dedicated beat container (`--profile celery` already compose me). Single-point khatam.
3. **Postgres PITR** *(M)* — Barman ya WAL-G se WAL-archiving + nightly base-backup → R2/B2 (rclone hook hai). **Monthly restore-drill** script (alag container, row-count assert).
4. **OTel + Alerting** *(M)* — `opentelemetry-instrumentation-fastapi/-sqlalchemy/-redis` add → traces. Loki+Tempo `deploy/compose/docker-compose.observability.yml` me. **Alertmanager** rules: error-rate, p95, queue-depth, payment-fail, disk. → Telegram/email.

**Exit:** `git push` → auto test→build→deploy→verify, zero manual SSH. Koi job miss nahi. 24h se kam data-loss window. Problem alert customer-se-pehle.

### 💰 PHASE 1 — Revenue Loop band karo (turant paisa) · ~5–8 din

Tumne Revenue ko top-2 priority diya — aur yahi sabse fast ROI hai.

1. **Pricing → Checkout page** *(M)* — `frontend/pricing.html` + `signup.html` (packages `/api/marketing/packages` se render). CTA → Razorpay Payment Link/Checkout (India UPI+card). **Naya backend nahi** — `/api/billing/webhooks/razorpay` already `usage.activate_plan()` call karta.
2. **Payments GO-LIVE** *(S)* — `UPI_VPA` set (modal enable) + `RAZORPAY_KEY_ID/SECRET` + webhook URL register. Stripe optional (foreign). Test-mode → live-mode smoke.
3. **Self-serve provision** *(M)* — pay-success → `clients_store.onboard()` + `customer_auth.set-password` auto + `onboarding.py` sweep (KB seed + first content). **Sab built hai** — bas chain karo: webhook→provision→welcome-email.
4. **Dunning + recovery** *(M)* — Razorpay Subscriptions dunning ON + smart-retry. Failed-pay → retry schedule + email + WhatsApp 1-click reminder (`whatsapp_campaign.py` hai). Grace-period + auto-pause (`usage.py` enforcement hai).
5. **Conversion analytics** *(S)* — PostHog Cloud snippet landing+app me → funnel: visit→audit→inquiry→signup→pay→active. Activation + drop-off dikhega.

**Exit:** Stranger landing pe aaye → pricing → UPI pay → 2-min me account+KB+content ready → dunning auto-recover. **Human touch zero. Yeh "revenue generating process" hai.**

### 🤖 PHASE 2 — Deep Automation (scale, kam manual) · ~1–2 hafta

1. **Reply→Book→Pay closed loop** *(L)* — `reply_agent.py` intent=interested → auto **demo-slot offer** (`/api/booking` hai) → confirm → payment-link → onboard. Aaj manual; isko durable Celery chain banao (idempotent + retry).
2. **Durable outreach sequences** *(M)* — prospect→email→Day3→Day7 followup ko `.jsonl` se **Celery-backed state machine** (per-lead status, retry, dead-letter). `open-sdr` / `b2b-sdr-agent-template` pattern, free-LLM pe.
3. **AI SDR enrichment** *(M)* — pre-outreach: lead website→KB→pain-point→personalized hook (free-LLM + `web_extract` hai). Reply rate up.
4. **Content + festival full-auto** *(M)* — `content_schedule.run_due()` + `festival-autoschedule` ko durable banao; 1-click→auto-ready pipeline harden. (Meta auto-publish blocked = gated.)
5. **Self-healing ops** *(S)* — `ops_watchdog` + Alertmanager → auto-restart/auto-rollback hooks (container unhealthy → recreate).

**Exit:** Lead aata hai → enrich → outreach → reply → qualify → book → pay → onboard → content deliver — **mostly bina human**, sirf legal-gated steps (DLT call, Meta post) manual.

### 📈 PHASE 3 — Scale + Polish (jab traction aaye) · ongoing

- **Load test** *(M)* — Locust/k6 → concurrency ceiling + p95 under load. Fir `WEB_CONCURRENCY=N` + Celery scale.
- **Coverage gate** *(S)* — CI me `--cov-fail-under=70`.
- **Secrets** *(S)* — SOPS/age ya Infisical (team-scale).
- **Voice upgrade** *(L, optional)* — Pipecat/LiveKit evaluate (sirf agar voice USP push karna ho).
- **Multi-tenant white-label scale** — `TenantBrandingMiddleware` hai; reseller self-serve banao.

---

## 5) Sequenced Checklist (copy-paste priority order)

```
PHASE 0  [ ] CI auto-deploy ON + stale-pyc bake     (S)  ← unblocks everything
         [ ] Celery Beat durable scheduler + DLQ     (M)
         [ ] Barman/WAL-G PITR + monthly restore-drill(M)
         [ ] OTel tracing + Alertmanager + Loki/Tempo (M)
PHASE 1  [ ] pricing.html + signup/checkout page      (M) ← #1 money
         [ ] Payments live (UPI + Razorpay keys)      (S)
         [ ] pay→auto-provision chain                 (M)
         [ ] Dunning + smart-retry + WA reminder      (M)
         [ ] PostHog Cloud funnel analytics           (S)
PHASE 2  [ ] reply→book→pay closed loop (Celery)      (L)
         [ ] durable outreach state machine           (M)
         [ ] AI SDR enrichment (free-LLM)             (M)
         [ ] content/festival full-auto harden        (M)
PHASE 3  [ ] load test + multi-worker scale           (M)
         [ ] coverage gate + secrets mgr + voice eval (S/L)
```

---

## 6) ⚠️ Careful / Don't-do (tumhare CLAUDE.md rules)

- **Grep pehle, rebuild baad** — `grep '@router' app/api/marketing.py` etc. Pehle festival/review duplicate ban chuke the → revert karne pade. History repeat mat karo.
- **Heavy infra single VPS pe mat thopo** — Temporal/PostHog-self-host/full-LGTM RAM kha jayenge. Managed free-tier (PostHog Cloud, Grafana Cloud) lo jahan heavy ho.
- **Free-stack hard rule** — koi paid STT/TTS/LLM nahi. Sarvam/paid adapters OFF rakho.
- **Legal gates** — DLT/140-series/DND/10am-7pm/AI-disclosure (₹10L penalty). Cold-call automation DLT ke bina mat enable karo. WhatsApp bulk auto = ban → 1-click human ya official Cloud API only.
- **Deploy gotcha** — naye `@app.get` page-routes ke baad HARD RELOAD (Phase-0 CI me bake ho jayega).
- **Secrets** — sirf `.env` (gitignored). CLAUDE.md/scripts/commit me kabhi nahi.
- **Token discipline** — naya milestone `docs/SESSION_LOG.md`, yahan 1-2 line.

---

## 7) Main abhi kya implement kar sakta hoon (tumhare ok pe)

Sabse safe, high-ROI **Phase-0 + Phase-1 quick-wins** main directly bana sakta hoon (test→verify, live break nahi):

1. **`frontend/pricing.html` + `signup.html`** — packages se render, Razorpay checkout CTA. (Revenue #1, koi backend risk nahi.)
2. **CI auto-deploy hardening** — `deploy-vps.yml` me stale-pyc bake + docs, `DEPLOY_ENABLED` flip-guide.
3. **Celery Beat migration plan + code** — APScheduler jobs → durable tasks, defensive (flag-gated, aaj jaisa default).
4. **OTel + Alertmanager wiring** — additive, OFF-by-default flag.
5. **Barman/WAL-G PITR script** — `pg_backup.sh` ke saath, restore-drill.

Bolo kaun sa pehle — main usi se shuru karun (ek-ek, test karke, push se pehle dikha ke).

---

## 8) Sources (research basis)

**Workflow / durable jobs:** [Temporal vs n8n self-host](https://earezki.com/ai-news/2026-03-12-temporal-vs-n8n-which-should-you-self-host/) · [Windmill vs peers](https://www.windmill.dev/docs/compared_to/peers) · [n8n vs Windmill vs Temporal](https://blog.arcbjorn.com/workflow-automation) · [Workflow tool choice](https://dev.to/frederic_zhou/workflows-windmill-vs-n8n-vs-langflow-vs-temporal-choosing-the-right-tool-for-the-job-23h5)
**Voice AI:** [Pipecat](https://github.com/pipecat-ai/pipecat) · [LiveKit Agents](https://github.com/livekit/agents) · [OSS Vapi alternatives 2026](https://blog.dograh.com/free-alternatives-to-vapi-4-oss-options-in-2026/) · [Production framework choice](https://webrtc.ventures/2026/03/choosing-a-voice-ai-agent-production-framework/)
**Lead-gen / AI SDR:** [open-sdr](https://github.com/MatthewDailey/open-sdr) · [b2b-sdr-agent-template](https://github.com/iPythoning/b2b-sdr-agent-template) · [awesome-ai-agents-for-sales](https://github.com/Salesably/awesome-ai-agents-for-sales) · [Email-automation](https://github.com/PaulleDemon/Email-automation) · [OSS email tools 2026](https://www.getinboxzero.com/blog/post/best-open-source-email-automation-tools-for-gmail)
**Observability:** [blueswen/fastapi-observability](https://github.com/blueswen/fastapi-observability) · [fastapi-observability-otel](https://github.com/googollee/fastapi-observability-otel) · [fastapi-loki-observability](https://github.com/TechWithTy/fastapi-loki-observability) · [Grafana FastAPI dashboard](https://grafana.com/grafana/dashboards/16110-fastapi-observability/)
**Analytics:** [PostHog](https://github.com/PostHog/posthog) · [Best OSS analytics self-host](https://posthog.com/blog/best-open-source-analytics-tools) · [Self-hosted product analytics 2026](https://openpanel.dev/articles/self-hosted-product-analytics)
**Dunning / revenue recovery:** [Stripe Smart Retries](https://docs.stripe.com/billing/revenue-recovery/smart-retries) · [Dunning guide 2026](https://baremetrics.com/blog/dunning-management) · [SaaS dunning automation](https://ustechautomations.com/resources/blog/saas-dunning-automation-how-to-recover-failed-payments) · [Razorpay SaaS gateways](https://razorpay.com/blog/payment-gateways-saas-startups-decision)
**PLG / self-serve:** [State of PLG 2026](https://userguiding.com/blog/state-of-plg-in-saas) · [Self-serve onboarding](https://productgrowth.in/insights/saas/self-serve-onboarding/) · [PLG automation ROI](https://ustechautomations.com/resources/blog/saas-product-led-growth-roi-analysis)
**Postgres DR:** [pgBackRest vs Barman](https://severalnines.com/blog/automating-backups-and-disaster-recovery-in-postgresql-at-scale-pgbackrest-vs-barman/) · [Top OSS Postgres backup 2026](https://www.bytebase.com/blog/top-open-source-postgres-backup-solution/) · [PITR with pgBackRest](https://mydba.dev/blog/postgres-point-in-time-recovery)

---
*Yeh roadmap research + live-code audit dono pe based hai. Implement karne se pehle har item `grep`-verify karo (kuch already ho sakta hai). Sequenced order ROI + dependency pe optimize kiya hai.*
