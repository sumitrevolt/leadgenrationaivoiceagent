# Project Memory — leadgenrationaivoiceagent (LEAN working memory)

> **Token discipline (IMPORTANT):** Yeh file har turn load hoti hai — isliye SIRF lean working-memory rakho.
> Detailed dated history → `docs/SESSION_LOG.md` (auto-load NAHI hota). Naya milestone wahan append karo, yahan sirf 1-2 line update.
> Naya task = naya chat (memory persist karti hai). Heavy sub-agents kam — wahi token jalate hain.
> **Build/incident/batch logs yahan MAT likho — woh SESSION_LOG me jaate. Yahan sirf CURRENT-STATE facts (product/pricing/infra/env/blockers/gotchas).**

## User Preferences
- **Hinglish (Roman script) me HI reply karo** — har baar. Concise + direct, kam formatting.
- Sab **free stack** — koi paid STT/TTS/LLM nahi (user decision). Phone-call paisa khaata hai → tuning FREE web-call pe.

## Product (current direction — MARKETING-FIRST pivot)
- **USER-CLARIFIED (2026-06-11): DO alag products.** (1) **AI Automated Marketing** = MAIN product (Dhanda-jaisa) chhote local businesses ke liye — iske Advanced tier me AI voice agent sirf EK FEATURE hai (inquiry callback, qualification, follow-ups). (2) **AI Voice Calling Agent** = ALAG standalone product (full AI telecaller, DLT-gated). **"Marketing + voice dono ek saath/bundle" USP framing GALAT hai — use mat karo.**
- FastAPI platform, **LIVE: https://leadsgenai.in** (Hostinger VPS Mumbai). Repo: github.com/sumitrevolt/leadgenrationaivoiceagent (main).
- **42 niches** (`app/niches.py`), categories: marketing / leadgen / both. API `/api/data/niches?tier=S|A|B`. Niche `lead_band` A/B/C (helpers `lead_band()`/`niches_for_product()`/`niche_products()`).
- **AI image generation**: `app/marketing/ai_image.py` — Pollinations API `gen.pollinations.ai`. Key env `POLLINATIONS_API_KEY` (legacy `POLLINATIONS_TOKEN` fallback). **KEY-SAFETY**: `pk_` = client-safe → direct URL embed; `sk_` = KABHI URL me nahi → `GET /api/marketing/ai-image-proxy` (server Authorization header + disk-cache `data/ai_images/`). `video_url()` bhi hai. Bina key 402 → frontend graceful. SVG posters = fallback.
- **Marketing routes ~600+; marketing.html 28 tabs + /app/automation Mission Control (23 tabs; Growth Lab=optimizer+experiments) + /app/growth-tools (18 tabs).** Naya marketing feature add karne se pehle `grep '@router' app/api/marketing.py` se existing routes dekho (FastAPI first-route-wins = duplicate shadow karta). Naya admin feature = UI tab SAATH hi banao (API-only = adhoora).
- Core public pages: `/audit` (#1 lead magnet) · `/site-audit` (lead-magnet #2) · `/demo` (AI-demo) · `/compare` (DO products) · `/blog` (programmatic SEO) · `/b/{slug}` (per-client mini-site+booking+card+bio) · `/pricing` · `/start` (signup). Website lead-capture widget (`<script>` embed, `/b/{slug}/widget.js` + `/embed`, AI-chat mode).

## Paid Tiers — DO products (ADR-009; doc: `docs/ADR_2026_06_11_Product_Split_Pricing.md`) — LIVE
- **Product 1 Marketing** (`packages.py`, `/api/marketing/packages`): Starter **₹1,199** · Growth **₹2,999** · Advanced **₹6,999** (voice FEATURE, 500 min/mo + minute top-ups). Yearly = price_inr_year (2 mahine free): **9990/24990/59990**. Top-up packs (`TOPUP_PACKS`): 100/250/500 min = ₹1499/3499/5999.
- **Product 2 Voice Agent** (`voice_packages.py`, `/api/voice/packages`, page **`/voice-agent`**): **PER-NICHE per-10-qualified-leads** (per-lead system REMOVED). Tiers (quota/mo × band A/B/C): vstarter 10 = ₹3,999/9,999/24,999 · vgrowth 30 = ₹9,999/26,999/69,999 · vpro 60 = ₹17,999/49,999/1,29,999 · 10-lead top-up ₹4,499/11,999/29,999 (period-expire). Billable unit = call_qualifier "interested" → `app/billing/lead_usage.py` meter (jsonl, FAIL-OPEN). Plans sync `subscription._sync_voice_plans` (9 ids `voice_*_{a,b,c}`).
- **billing-truth RULE**: `packages.py` = single source of truth (`subscription._sync_plans_from_packages`). `/billing/plans` sirf public 3. GST sirf `GST_GSTIN` set pe charge (unregistered = no tax, <₹20L truth). Pricing change = `packages.py` + `test_billing_truth_2026.py` SAATH. GST invoice: Rule-46 sequential `INV/2026-27/0001`, SAC 998313.
- **Launch NOW possible**: marketing tiers + inbound callbacks ko DLT/telephony NAHI chahiye. Sirf voice cold-calling DLT pe atki.

## Live Infra
- VPS **72.61.245.204** (Mumbai, Ubuntu 24.04, Docker). App `/opt/leadgen`. **App = Docker container `leadgen_app` :8000** (`docker compose -f docker-compose.vps.yml`, restart:unless-stopped); systemd `leadgen` DISABLED (rollback ke liye installed). Caddy host-proxy 127.0.0.1:8000 (Traefik conflict — hostinger-deploy skill dekho).
- **DB = Postgres (`leadgen_db`) via PgBouncer (`pgbouncer:6432`) + Redis (`leadgen_redis` :6379)**. SQLite `/opt/leadgen/leadgen.db` = rollback-backup only. Qdrant docker `127.0.0.1:6333`.
- **Scheduler LIVE = Celery durable**: `WEB_CONCURRENCY=2` (uvicorn HTTP-only) + `RUN_IN_PROCESS_SCHEDULER=0` + `leadgen_worker` (concurrency=4) + `leadgen_scheduler` (beat) containers (`--profile celery`). Web process KABHI heavy job na chalaye. worker.py default sirf 12 `staff-*` jobs (legacy beat `ENABLE_LEGACY_BEAT=1` gated). DLQ → Redis `dlq:failed_tasks`. **ROLLBACK**: `.env` `RUN_IN_PROCESS_SCHEDULER=1`+`WEB_CONCURRENCY=1`, stop worker/scheduler, app recreate.
- **App image** (`Dockerfile.lock`): live-venv `requirements.lock.txt` se `--no-deps` (py3.12). app/ + frontend/ + `.claude/skills/` image me BAKED — code change = `docker compose build app` + `up -d --no-deps app` recreate (data-only `./data`+`./logs` bind-mount change ko NAHI). ML assets BAKED (fastembed 241M `/opt/fastembed_cache`, silero-vad torch-CPU). Lock refresh: `scripts/vps_freeze.sh` → commit `requirements.lock.txt`.
- **Containers ~13+**: app+db+redis+pgbouncer+worker+scheduler+freeswitch+6 obs (prometheus/grafana/alertmanager/loki/tempo/uptime/gatus). Self-heal cron `scripts/vps_selfheal.sh` */10. Offsite email-backup cron (Hostinger mail). fail2ban + unattended-upgrades active.
- Other pages: `/app/marketing` · `/app/clients` · `/app/outreach` · `/app/team` · `/app/agents` · `/app/ops` (Mission Control) · `/app/automation` · `/app/test-call` (FREE voice tuning) · `/app/admin` · `/app/customer` · `/app/login` (customer) · `/app/admin-login` · `/app/team-access` (RBAC) · `/status` (public). Legal: `/privacy /terms /refund`. SEO: `/robots.txt /sitemap.xml`. `/mcp` MCP server mounted.

## AI Stack (all free, `app/voice_agent/free_ai.py` multi-provider chain)
- **LLM**: Cerebras `gpt-oss-120b` (WORKING, free-unlimited) → groq → xai(no credits) → openrouter → Gemini. **Circuit-breaker**: provider 429/quota pe ESCALATING cooldown 60s→2x..→30min cap, "per day/TPD/limit reached" wording = seedha 30min, success pe reset. **GOTCHA: Groq TPD (daily-token) content-heavy days pe khatam ho sakta — fallbacks + breaker designed-in.** `scripts/patch_status.py` = container me patch approve/reject CLI.
- **STT**: Groq `whisper-large-v3` (GROQ_API_KEY SET ✓) → Gemini audio → local faster-whisper (Hindi weak). Web-call + phone-paths dono Groq PRIMARY.
- **TTS**: EdgeTTS `hi-IN-SwaraNeural` (`edge-tts>=7.2.0` zaroori, warna 403). Prosody env knobs `PHONE_TTS_RATE`/`PHONE_TTS_PITCH` (vobiz +8%).
- **RAG**: Qdrant single `kb_main` collection, per-niche namespaces (`niche:` + `client:<id>` + "skills" ns). Embedder multi-model fallback (`paraphrase-multilingual-MiniLM-L12-v2` dim-384; fastembed version-proof, REAL dim auto-detect). **RULE: har ML asset = image-bake + off-loop load (`asyncio.to_thread`) + deadline + disable-switch.** Public endpoint me KB/ML = thread + hard timeout (3 prod-downs isi se).
- **RAG upgrades (optional, OFF default)**: `agentic_rag.py` (CRAG, `USE_AGENTIC_RAG=1` ON) + `graph_rag.py` (LightRAG, `USE_LIGHTRAG=1` OFF). `structured.py` (Instructor, `USE_STRUCTURED_CONTENT=1` ON) · `web_extract.py` (trafilatura, ACTIVE in prospector) · `seo_tools.py`/`to_markdown.py`/`deep_extract.py` (installed, opt-in). Docs: `docs/RAG_KnowledgeGraph_Agentic.md`, `docs/Automation_Marketing_Repos.md`.
- **Voice brain**: `telecaller_brain.py` (KB-grounded, ACP pattern, ≤2 sentences/1 question) + `niche_scripts.py`. Tuning FREE web-call pe; phone = final verify only.
- **Turn-taking (WIRED, OFF default)**: `turn_detector.py` SileroSpeechGate/SmartTurnDetector in vobiz_stream (16k) + phone_stream (8k) + pipeline.py `confirm_end_of_turn()`. Enable: `USE_SILERO_VAD=1` / `USE_SMART_TURN=1` (heavy deps). Bina dep/flag = graceful RMS fallback.
- **QA**: koi bhi voice change ke baad `scripts/agent_tester.py` chalao (free scorecard: double/empty/repeat/long/slow).
- **Exotel Voicebot stream** (LIVE WS): `app/voice_agent/exotel_stream.py` `ExotelVoicebotSession(PhoneCallSession)` — applet URL `wss://leadsgenai.in/ws/exotel-voicebot?sample-rate=16000`. PCM16 slin → 8k resample → parent VAD/STT/LLM/TTS reuse.

## AI Staff Team (product framing) — `app/platform/team.py` + `team_scheduler.py`
**14 staff** (split by `product`): marketing (isha/dev/rohan) · voice (swara/tara/arjun/meera) · platform (boss/kavya/nikhil/Hermes-infra_handler · Guru/Vikram-code_upgrader · hostinger_hermes Apprentice). `staff_for_product()`, `/api/platform/team?product=`. Events → `agent_events` table. Dashboard `/app/team`. team_status 3-tier (working≤20min / active≤16h / offline); `team_pulse()` rotates cheap REAL monitors.
**Auto-schedule (IST)**: 06:30 blog · 07:00 content(self+clients) · 08:30 digest · 09:30 scrape/prospect · 10:30 email outreach+followups · hourly Kavya health · 02:30 Arjun QA · 03:00 Meera trainer · 15-min growth-pulse · hourly reply-triage · hourly ops-watchdog · hourly auto-onboard · ~04:00 backups. **boot-grace**: heavy daily job (qa/trainer/blog/content/digest/prospect/email_outreach) ka window boot pe active ho to is boot pe SKIP (restart-storm prevent — prod-down lesson).
**Multi-agent (free-stack)**: `coordinator.py` (planner/handoff/fanout/Reflexion `coordinate_advanced`/critic/debate/hierarchical) · `process_engine.py` (process-as-code, event-sourced journal, deterministic gates, human breakpoints) · `self_improve.py` (task→task FOREVER Celery-requeue loop, `SELF_IMPROVE_LOOP=1` ON) · `sales_team.py` (5-agent BANT deep-dive, `SALES_TEAM=1` ON) · `fde.py` (FDE deploy agents). execute-mode safe-default = drafts; rohan/swara side-effect agents = draft-only by design. Optional: `staff_supervisor.py` langgraph (`USE_LANGGRAPH_SUPERVISOR=1`). Decision matrix: `docs/AUTOMATION.md` + `multi-agent-coordination` skill.
**Dead-man trio** (always-on loops): heartbeat (`data/job_heartbeats.json`) + revive-beat */20min + watchdog ensure_alive. **RULE: worker recreate ke baad `redis-cli llen celery` check; >500 = `del celery`** (tasks transient/regenerable, beat re-schedules). **WINDOWS LESSON: `os.kill(pid,0)` Windows pe CTRL_C bhejta — `_pid_alive` ctypes OpenProcess use karta, idiom dobara KABHI nahi.**

## Outbound/Growth (working)
- **Email outreach LIVE**: Hostinger SMTP `admin@leadsgenai.in` (`smtp.hostinger.com:465`). `AUTO_EMAIL_OUTREACH=true` → Rohan roz 10:30 auto-sends personalized Hinglish cold-emails + Day-3/7 followups. Cap 25/day, MX-verified (`OUTREACH_VERIFY_MX=1`). Warmup ramp + bounce auto-pause (`EMAIL_WARMUP=1`, `WARMUP_START_DATE`). Email auth SPF/DKIM/DMARC ALL SET.
- **Google Maps API LIVE** (Places API New). Prospector real phones+reviews (cap `PROSPECT_MAX_LOOKUPS=60`/run). OSM Overpass fallback. **Lead harvester** (`platform/lead_harvester.py`, `LEAD_HARVESTER=1` ON): prospector + SearXNG/Brave websearch + data.gov.in + email-enrich. **ToS-BLOCKED auto-scrape**: justdial/indiamart/sulekha/linkedin/fb/insta (manual CSV import hi unka path). Niche rotation (`NICHE_ROTATION=1`, 42 niches) + city rotation (15-city pool).
- **AI reply triage** (`reply_agent.py`, `REPLY_AGENT=1` ON): IMAP → intent classify → status update + Hinglish draft (1-click send, auto-send OFF ban-safe). `_is_bulk_sender()` guard (unknown+bulk = skip, deal sirf known prospect).
- **Omnichannel cadence** (`cadence.py`, `CADENCE_ENGINE=1` ON): per-lead multi-channel sequence drafts. **Sales pipeline** (`SALES_ENGINE=1` ON) + auto-proposal + AI sales-closer. **Apollo-style**: prospect search/saved-lists/CSV-import/email-finder.
- **Revenue automation** (ON): dunning (`DUNNING_ENGINE`), lifecycle nurture, client-health alerts, revenue digest. Channel experiments bandit (`CHANNEL_EXPERIMENTS=1` ON, 17 free+legal channels, auto-POST kahin NAHI). Growth optimizer (`GROWTH_OPTIMIZER=1` ON).
- **WhatsApp = 1-click human send** (bulk auto = ban). Cloud API official-only, auto-send gated `WHATSAPP_AUTO_SEND=1`+creds+approved-template (OFF). **Telegram** = pehla TRUE auto-post (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_AUTO_PUBLISH=1`).
- **Native CRM sync** (`crm_sync.py`, `CRM_SYNC` OFF): Zoho (India DC) + HubSpot, per-client ya global creds. UI: growth-tools "CRM Sync" tab.
- **Self-hosted tools** (`docker-compose.tools.yml`): SearXNG (free web-search, ON) · ntfy phone-push (`https://ntfy.leadsgenai.in`, ON) · changedetection.io.
- Per-client: `clients_store.py` + `auto_content.py` + `mini_site.py` (`/b/{slug}`) + `onboarding.py` (`AUTO_ONBOARD=1` ON: website→KB seed + first content pack).

## Infra Additions (2026-06-15 — see docs/INFRA_UPGRADE_2026.md for full detail)
- **docker-compose.addons.yml** (NEW): `celery-exporter` (:9808 Prometheus) + `flower` (:5555 task UI) + `minio` (:9000 S3 API / :9001 console). Activate: `docker compose -f docker-compose.addons.yml up -d`
- **prometheus.yml**: celery + flower scrape targets ADDED (docker-compose.addons.yml up hone ke baad active).
- **Grafana auto-provisioning**: `monitoring/grafana/provisioning/` + `monitoring/grafana/dashboards/celery_tasks.json` (restart karne pe Celery dashboard auto-load).
- **`app/middleware/__init__.py`**: `PlanTierRateLimitMiddleware` ADDED (Starter 60rpm / Growth 200rpm / Advanced 500rpm). Activate: `PLAN_RATE_LIMIT=1` in `.env`.
- **`app/storage/minio_client.py`** (NEW): S3-compatible storage layer, local-disk fallback. `from app.storage import get_storage`.
- **Wired-but-OFF (just need .env keys)**: PostHog (`POSTHOG_API_KEY`), Sentry (`SENTRY_DSN`), LiteLLM (`LITELLM_MASTER_KEY`), Cloudflare (`CLOUDFLARE_TUNNEL_TOKEN`), OTel (`ENABLE_OTEL=1`), RequestGuard (`REQUEST_GUARD=1`).
- **Activation checklist**: `docs/INFRA_UPGRADE_2026.md` Part 8.

## Active Blockers / USER-ACTION pending (env-unset = dormant, graceful skip)
- **🚨 Razorpay 401 (ROOT CAUSE PROVEN 2026-06-14)**: `.env` me PLACEHOLDER values hain — `RAZORPAY_KEY_ID=rzp_test_you...`, `RAZORPAY_KEY_SECRET=your-razorpa...`. Real keys kabhi set hi nahi hue (code bug NAHI, revoked NAHI). **FIX = .env me asli `rzp_live_...` keys daalo → recreate app → webhook register** (`POST /api/billing/webhooks/razorpay` + `RAZORPAY_WEBHOOK_SECRET`). Bina iske checkout/payment-links/topup/dunning sab dead. Grace guard built (commit 0e6d6ee, deploy deferred — agle clean rebuild pe auto). **Pehla paid customer aane se pehle MUST fix.**
- **UPI_VPA UNSET** (standalone UPI modal off; Razorpay ke andar UPI phir bhi chalta). **NOTIFY_EMAIL=admin@leadsgenai.in** SET (inquiry alerts).
- **DLT**: individual request REJECTED → user ko **Udyam (MSME, FREE, udyamregistration.gov.in)** cert se Proprietorship re-apply (Udyam cert ready). DLT sirf cold-calling (Advanced) ke liye.
- **Vobiz telephony**: trial ~khatam. Recharge → DID kharido → `VOBIZ_CALLER_ID=+91<DID>` + restart. Cost ladder: Plivo ₹0.60 → Vobiz ₹0.45 → operator-direct ₹0.30-0.40.
- **Exotel**: ACTIVE+AUTH'd (test calls PROVEN). Account Type=Trial, **KYC=notstarted** (sirf verified numbers callable). Balance ~₹494. Voicebot applet enable + 2nd ExoPhone = Exotel support (support email sent). KYC+recharge + DLT = user paperwork.
- **Future (EXTERNAL-BLOCKED — user paperwork/approval)**: missed-call callback (Vobiz DID + webhook), GBP API auto-post (Google 60-din approval), Meta/FB-IG auto-posting (app-review), R2/B2 offsite (creds), HA/2nd-server (spend), Exotel key rotate (dashboard). In par token mat jalao jab tak unlock na ho.

## Telephony (production-hardened) — current state
- `telephony/webhooks.py` `/api/webhooks` pe MOUNTED (Twilio/Exotel voice+status, signature-verified Depends, lazy-init). Sentry FastApiIntegration global.
- **Exotel** = active provider (`TELEPHONY_PROVIDER=exotel`, host `api.exotel.com`, modern API-Key:API-Token basic-auth). `EXOTEL_CALLER_ID=01141189204`, `EXOTEL_APP_ID=1265199`. ExoPhone StatusCallback → `/api/webhooks/exotel/status`. Balance/readiness wired (`telephony_readiness.py` Tara agent, low-balance alert `EXOTEL_LOW_BALANCE`). `scripts/exotel_setup_audit.py` = account/kyc/balance/calls + `--call`.
- **AMD**: Twilio AnsweredBy machine → voicemail-drop (`AMD_LEAVE_VOICEMAIL=1`) ya hangup. **DND fail-CLOSED** (TRAI): lookup fail = promotional BLOCK (`dnd_lookup_failed`). Transactional unaffected. **Consent ledger** (`consent_ledger.py`): opt-out→INSTANT suppression cross-channel + 90-din recording retention. **Distributed call state** (Redis, local in-memory fallback). `CallRequest.call_type` (promotional default; transactional looser gate). Human transfer gated `CALL_TRANSFER` (OFF; callers `flow_state["owner_phone"]` + Exotel KYC chahiye). Minute metering (`usage.record_call_usage`, FAIL-OPEN). Multi-tenant white-label (`middleware/tenant.py`, FAIL-OPEN, subdomain + custom_domain).

## Legal (CONFIRMED)
- TRAI: 140-series + DLT + DND scrub + 10am-7pm + AI disclosure mandatory, penalty ₹10L. Foreign trunks (Twilio/Telnyx/Vonage) India-domestic = ILLEGAL. AI-disclosure greetings wired ("ek AI assistant"). DPDP Act 2023 rights + Grievance Officer in /privacy.
- Pure minutes-resale bina license = Telegraph Act violation. Legal resale = **SaaS bundle** (DLT/140 CLIENT ke naam) — industry standard.
- WhatsApp bulk auto-send = number ban. Cold auto-calls bina DLT = ₹10L risk → sirf inbound auto-callback.

## Deploy loop (detail → `leadgen-ops` + `hostinger-deploy` skills)
1. `python scripts/prod_check.py` → 2. `scripts\run_tests.bat` (**pytest_run.log Read karo**, ~80+ green; full pytest team_pulse area pe hang ho sakta — targeted suites use) → 3. Windows git `C:\PROGRA~1\Git\cmd\git.exe` push (bat ke andar) → 4. VPS pull via **Git ka ssh** `C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204` + `docker compose build app` + `up -d --no-deps app` → verify `/health` = `environment:production`.
- **Naye `@app.get` page-route add karne ke baad HARD RELOAD zaroori** (warna stale .pyc 404): `systemctl stop leadgen; pkill -9 -f uvicorn; find /opt/leadgen/app -name __pycache__ -type d -prune -exec rm -rf {} +; systemctl start leadgen` — ya container recreate. Diagnostic: `scripts/check_route.py`.
- Deploy verify me `sleep 16` + 2x health-check rakho. Build pipe `| tail` exit-code maskta → `set -o pipefail`. **Dockerfile `RUN chown -R /app` slow/stall-prone (giant layer) — future fix `COPY --chown` use karo.** compose service `worker-heavy` (hyphen) — galat naam pe poora `up` ABORT; pehle `config --services`.

## Critical Env Gotchas
- **Sandbox mount STALE** ho jata hai file-tool edits ke baad → Windows side (Read/Write/Edit, Desktop Commander) = source of truth. Verify Windows pe (bat chala ke log Read karo).
- 🚨 **CLAUDE.md/SESSION_LOG sandbox-bash append KABHI nahi** (stale mount = mid-file corruption hua) — memory files SIRF Windows file-tools (Edit) se.
- Sandbox **git index unreadable** → Windows git via Desktop Commander.
- Windows **OpenSSH broken** → Git ka ssh.exe use karo.
- `.bat`: npm/git `.cmd` ko `call` ke saath; `timeout /t` fail → `ping -n N 127.0.0.1`. DC one-liner quoting mangle → complex cmd `.bat` me likho, output log me, log Read karo. SSH command me `&`/`<` quoting todta (EXIT_9009) → smoke `.py` file me likho, ssh se `python scripts/x.py`.
- **Bade multi-file edits same file pe parallel mat do** — file truncate ho jati hai.
- **Secrets kabhi committed file/CLAUDE.md/scripts me mat likho — sirf .env** (gitignored). `scripts/check_secrets.py` (/verify step-4 me WIRED; false-positive = line pe `nosecret`).

## Skills (`.claude/skills/` + `data/skills_extra/` — workflow invoke karo, re-derive mat karo)
- **skill_pack** (`platform/skill_pack.py`, `SKILL_PACK=1` ON): VPS agents ko `find/snippet_for` + KB "skills" ns ingest. Total **241 skills** = 61 project + 141 agency-agents pack + 39 ECC pack (`data/skills_extra/*.md`, data-only = git pull pe live, NO rebuild). Project skills cover: session bootstrap, ops/verify/deploy, hostinger gotchas, marketing-feature, telephony, automation-pipeline/flags, FDE, multi-agent-coordination, agent-loop-design, self-improve, parity/parallel-batch, RBAC, debugging/TDD/review, pricing/copy/churn, voice-humanization, web-call-triage, etc.
- **Slash commands** (`.claude/commands/`, 7): `/verify` `/ship` `/checkpoint` `/learn` `/compact-check` `/optimize` `/test-expand`.
- **Automation loops doc**: `docs/AUTOMATION.md` (self-improve · coordinator 4-modes · process-engine — decision tree). `self-improve-control` skill (monitor + safety matrix + `scripts/selfimprove_audit.py`). Safety: `SELFIMPROVE_COST_CAP=50`, `SELF_IMPROVE_APPROVAL=1` (optional).
- **code_upgrader** (Vikram, `CODE_UPGRADER=1` ON): signals → free-LLM patch PROPOSALS (`data/code_patches.jsonl` + email) → admin approve API; core code KABHI auto-apply nahi.
- **Flags registry**: `GET /api/growth/infra/flags` = saare automation flags live on/off (AUTOMATION_FLAGS list in growth.py — naya flag wahan add karo). Detail: `automation-flags` skill.

## History & Research
- Full dated history: **`docs/SESSION_LOG.md`** (build/incident/batch logs yahan archive hote). Research: `docs/Architecture_Research_RAG_Agents_MCP.md`, `docs/P3_Own_Telephony_Stack_Plan.md`, `docs/Marketing_Kit_LeadGenAI.md`, `docs/Sales_Kit_Hinglish.md`, `docs/THREE_BRAIN_ARCHITECTURE.md`, `docs/API.md`, `docs/Competitor_Top20_Feature_Gap_2026.md`, `docs/PRODUCTION_READINESS_2026.md`. Pricing: `Niche_Pricing_Research.xlsx`. Production cutover: `docs/PRODUCTION_CUTOVER.md`. Infra hardening: `docs/INFRA_HARDENING_GUIDE.md`.
