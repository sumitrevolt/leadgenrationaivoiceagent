# PROJECT HANDOFF — LeadGenAI (leadgenrationaivoiceagent)

> **Purpose:** Complete all-in-one handoff. Ek naya developer YA naya AI-agent isse padh ke poora project samajh sake aur takeover kar sake — product, tech, infra, deploy, blockers, legal, gotchas, sab.
> **Generated:** 2026-06-20 · **Last updated:** 2026-06-20 PM — godfile wave-1 merged · UPI admin-config in-flight · 06-20 hardening shipped · Source of truth: `CLAUDE.md` (lean working memory) + `docs/SESSION_LOG.md` (full dated history).
> **Language:** Hinglish (project convention) — technical terms/commands/paths English me.

---

## 0. 30-Second Summary

LeadGenAI = **do alag SaaS products** chhote Indian local businesses ke liye, ek hi FastAPI platform pe:

1. **AI Automated Marketing** (MAIN product) — Dhanda/EZO-jaisa marketing automation. Advanced tier me AI voice agent sirf EK feature.
2. **AI Voice Calling Agent** (standalone) — full AI telecaller, DLT-gated.

- **LIVE:** https://leadsgenai.in (Hostinger VPS Mumbai, Docker).
- **Repo:** github.com/sumitrevolt/leadgenrationaivoiceagent (`main` branch).
- **Stack:** FastAPI · Postgres+PgBouncer+Redis · Qdrant · Celery · ~464 Python files · ~761 routes · 50 HTML pages.
- **AI = 100% FREE stack** (koi paid STT/TTS/LLM nahi — hard user decision).
- **Status:** Platform live + marketing tiers sellable ABHI. Voice cold-calling **DLT + Vobiz recharge pe blocked** (neeche dekho).

**⚠️ Sabse pehle padho:** Section 11 (Blockers), Section 13 (Gotchas), Section 14 (Onboarding Day-1).

---

## 1. Products (USER-CLARIFIED — galat framing mat karo)

**DO ALAG products hain. "Marketing + voice bundle/ek-saath" USP framing GALAT hai — kabhi use mat karo.**

### Product 1 — AI Automated Marketing (MAIN, "Dhanda-jaisa")
Chhote local businesses ke liye marketing automation. AI content, social drafts, mini-sites, lead capture, AI image-gen, campaigns. **Advanced tier me AI voice agent ek FEATURE hai** (inbound inquiry callback, qualification, follow-ups) — standalone telecaller nahi.

### Product 2 — AI Voice Calling Agent (standalone)
Full AI telecaller — outbound cold-calling, qualification, CRM push. **DLT-gated** (cold-calling bina DLT = ₹10L TRAI risk). Inbound auto-callback DLT-free chal sakta.

- **39 builtin niches** (`app/niches.py` `NICHES` dict + runtime custom merge). Categories: marketing / leadgen / both. Har niche `lead_band` A/B/C. API: `/api/data/niches?tier=S|A|B`.
- Helpers: `lead_band()` · `niches_for_product()` · `niche_products()`.

**Core public pages:** `/audit` (#1 lead magnet) · `/site-audit` (lead magnet #2) · `/demo` (AI demo) · `/compare` (do products) · `/blog` (programmatic SEO) · `/b/{slug}` (per-client mini-site + booking + card + bio) · `/pricing` · `/start` (signup) · `/voice-agent` (Product 2 page). Website lead-capture widget embed (`/b/{slug}/widget.js` + `/embed`, AI-chat mode).

---

## 2. Pricing & Billing (ADR-009 — LIVE)

> **billing-truth RULE:** `app/billing/packages.py` = SINGLE source of truth (`subscription._sync_plans_from_packages`). Pricing change = `packages.py` + `test_billing_truth_2026.py` SAATH update. Warna CI block.

### Product 1 — Marketing (`packages.py`, `/api/marketing/packages`)
| Tier | Monthly | Yearly (2 months free = 10×) |
|---|---|---|
| Starter | ₹1,199 | ₹11,990 |
| Growth | ₹2,999 | ₹29,990 |
| Advanced | ₹6,999 (voice feature, 500 min/mo) | ₹69,990 |

Top-up minute packs (`TOPUP_PACKS`): 100/250/500 min = ₹1,499 / ₹3,499 / ₹5,999.

### Product 2 — Voice Agent (`voice_packages.py`, `/api/voice/packages`, page `/voice-agent`)
**FLAT MONTHLY per niche-band** (unlimited AI calls, no lead-counting/disputes):
| Band | Monthly | Annual (10×) |
|---|---|---|
| Band A | ₹4,999 | ₹49,990 |
| Band B | ₹9,999 | ₹99,990 |
| Band C | ₹19,999 | ₹1,99,990 |

FREE pilot: 7 din / 50 calls (`voice_pilot`, ₹0). Niche→band mapping = `app/niches.py` `lead_band`. Sync: `subscription._sync_voice_plans` (7 plan ids). Meter `app/billing/lead_usage.py` = UNLIMITED_QUOTA (FAIL-OPEN).

### Billing infra
- `/billing/plans` sirf public 3 marketing tiers dikhata.
- **GST sirf `GST_GSTIN` env set hone pe charge** (unregistered <₹20L = no tax — legally correct). Invoice: Rule-46 sequential `INV/2026-27/0001` (atomic, `threading.Lock`), SAC 998313.
- **Payments = manual UPI** (`UPI_VPA` env). **Razorpay ENTIRELY REMOVED 2026-06-18** (code-level — gateway/webhooks/verify sab deleted ya inert stub). Stripe path intact (international only). Unconfigured checkout → clean 503 + UPI fallback.

---

## 3. Tech Stack & Architecture

| Layer | Tech |
|---|---|
| Web framework | FastAPI (async), uvicorn HTTP-only (`WEB_CONCURRENCY=2`) |
| DB | Postgres (`leadgen_db`) via PgBouncer (`pgbouncer:6432`) |
| Cache/queue | Redis (`leadgen_redis:6379`) |
| Task queue | Celery (durable) — `leadgen_worker` (concurrency=4) + `leadgen_scheduler` (beat) |
| Vector DB | Qdrant (`127.0.0.1:6333`), single `kb_main` collection, per-niche/client namespaces |
| Migrations | Alembic (Postgres stamped, head `005`+) — schema change = `alembic revision --autogenerate` + `upgrade head` |
| Frontend | Server-rendered HTML (50 files in `frontend/`), no SPA framework |
| Telephony | Vobiz (FreeSWITCH container), WS bidirectional L16/16k |
| Container | Docker Compose (`docker-compose.vps.yml` + profiles) |
| MCP | `/mcp` server mounted (MCP-as-product `/api/mcp-product/v1/*` + A2A card `/.well-known/agent.json`) |

**Route layout (~761 `@router`/`@app` decorators):**
- Naya marketing feature add karne se pehle: `grep '@router' app/api/marketing.py` — **FastAPI first-route-wins**, duplicate route silently shadow karta.
- `marketing.html` = 28 tabs · `/app/automation` Mission Control = 28 tabs (Growth Lab = optimizer+experiments) · `/app/growth-tools` = 18 tabs.
- **RULE:** naya admin feature = UI tab SAATH banao. API-only = adhoora.

**App-internal pages:** `/app/marketing` · `/app/clients` · `/app/outreach` · `/app/team` · `/app/agents` · `/app/ops` (Mission Control) · `/app/automation` · `/app/test-call` (FREE voice tuning) · `/app/admin` · `/app/customer` · `/app/login` · `/app/admin-login` · `/app/team-access` (RBAC) · `/app/battlecard` (internal sales intel) · `/app/explorer` (architecture graph) · `/status` (public). Legal: `/privacy /terms /refund`. SEO: `/robots.txt /sitemap.xml`.

---

## 4. Live Infrastructure

- **VPS:** `72.61.245.204` (Hostinger, Mumbai, Ubuntu 24.04, Docker). App dir `/opt/leadgen`.
- **App = Docker container `leadgen_app` :8000** (`docker compose -f docker-compose.vps.yml`, `restart: unless-stopped`). systemd `leadgen` DISABLED (rollback ke liye installed).
- **Proxy:** Caddy host-proxy → `127.0.0.1:8000` (Traefik conflict tha — `hostinger-deploy` skill dekho).
- **Scheduler = Celery durable:** `RUN_IN_PROCESS_SCHEDULER=0` + worker + beat containers (`--profile celery`). Web process KABHI heavy job na chalaye.
- **~13+ containers:** app + db + redis + pgbouncer + worker + scheduler + freeswitch + 6 observability (prometheus/grafana/alertmanager/loki/tempo/uptime/gatus).
- **Self-heal:** cron `scripts/vps_selfheal.sh` (*/10 min). Offsite email-backup cron (Hostinger mail). fail2ban + unattended-upgrades active.
- **App image** (`Dockerfile.lock`): live-venv from `requirements.lock.txt` (`--no-deps`, py3.12). `app/` + `frontend/` + `.claude/skills/` BAKED into image. ML assets BAKED (fastembed 241M `/opt/fastembed_cache`, silero-vad torch-CPU). Lock refresh: `scripts/vps_freeze.sh` → commit `requirements.lock.txt`.
- **Rollback path:** `.env` set `RUN_IN_PROCESS_SCHEDULER=1` + `WEB_CONCURRENCY=1`, stop worker/scheduler, recreate app. SQLite `/opt/leadgen/leadgen.db` = rollback-backup only (live DB = Postgres).
- **Addons** (`docker-compose.addons.yml`, optional): celery-exporter (:9808) + flower (:5555) + minio (S3 :9000/:9001). Activate: `docker compose -f docker-compose.addons.yml up -d`.

---

## 5. AI Stack (ALL FREE — `app/voice_agent/free_ai.py` multi-provider chain)

> **Hard constraint:** koi paid STT/TTS/LLM nahi. Phone-call paisa khaata → voice tuning FREE web-call pe (`/app/test-call`), phone sirf final verify.

**LLM chain** (`free_ai.py` ~line 420, live ok-rate tuned):
`[Ollama if OLLAMA_PRIMARY]` → **Mistral `mistral-small-latest` (PRIMARY ~99%)** → **Groq `llama-3.1-8b-instant` (~96%)** → Cerebras `gpt-oss-120b` (free 120B, 429-prone) → `[Ollama floor]` → Gemini `gemini-2.0-flash-lite` → SambaNova → OpenRouter (deepseek/llama free).
- **Circuit-breaker:** provider 429/quota → escalating cooldown 60s→2x→30min cap. "per day/TPD/limit reached" = direct 30min. Success = reset.
- **GOTCHA:** Groq TPD (daily token budget) content-heavy days pe khatam ho sakta — isliye Mistral-primary + breaker designed-in.

**STT:** Groq `whisper-large-v3` (`GROQ_API_KEY` set ✓) → Gemini audio → local faster-whisper (Hindi weak). Web + phone dono Groq primary.

**TTS:** EdgeTTS `hi-IN-SwaraNeural` (**`edge-tts>=7.2.0` zaroori** warna 403). Prosody env: `PHONE_TTS_RATE` / `PHONE_TTS_PITCH`.

**RAG:** Qdrant single `kb_main`, per-niche namespaces (`niche:` + `client:<id>` + "skills"). Embedder multi-model fallback (`paraphrase-multilingual-MiniLM-L12-v2`, dim-384, fastembed version-proof).
- **RULE:** har ML asset = image-bake + off-loop load (`asyncio.to_thread`) + deadline + disable-switch. Public endpoint me KB/ML = thread + hard timeout (3 prod-downs isi se hue).
- Optional RAG upgrades (mostly OFF): `agentic_rag.py` (CRAG, `USE_AGENTIC_RAG=1` ON) · `graph_rag.py` (LightRAG, OFF) · `structured.py` (Instructor, ON) · `web_extract.py` (trafilatura, active in prospector).

**Voice brain:** `telecaller_brain.py` (KB-grounded, ACP pattern, ≤2 sentences / 1 question) + `niche_scripts.py`.

**Turn-taking** (WIRED, OFF default): `turn_detector.py` Silero/SmartTurn in vobiz_stream (16k) + phone_stream (8k). Enable: `USE_SILERO_VAD=1` / `USE_SMART_TURN=1`. Bina dep = graceful RMS fallback.

**QA:** koi bhi voice change ke baad `scripts/agent_tester.py` chalao (free scorecard: double/empty/repeat/long/slow).

---

## 6. Telephony (production-hardened)

- **Active provider = Vobiz** (`TELEPHONY_PROVIDER=vobiz`). `app/telephony/vobiz_handler.py` `VobizClient.place_call(...)`, env `VOBIZ_AUTH_ID` / `VOBIZ_AUTH_TOKEN` / `VOBIZ_CALLER_ID`.
- **LIVE WS stream:** `app/telephony/vobiz_stream.py` `VobizStreamSession` — `wss://leadsgenai.in/api/telephony/vobiz/stream/{token}`, L16/16k bidirectional, parent VAD/STT/LLM/TTS reuse.
- **Cross-path parity (2026-06-18):** `_cleanup` → `post_call_hooks.meter_call_completion` (minute billing + `call.completed` webhook, idempotent) + `_auto_qualify` → `apply_qualified_downstream` (CRM/sales/cadence). Guard: `scripts/cross_path_audit.py` wired in `final_integration_check`.
- **Twilio** = international fallback only (India-domestic foreign-trunk = ILLEGAL).
- **Exotel DELETED 2026-06-18** (handler/stream/account stubbed; `/ws/exotel-voicebot` retired).
- **Webhooks** (`telephony/webhooks.py` @ `/api/webhooks`): Twilio voice+status signature-verified; Vobiz `/vobiz/answer` + `/vobiz/status`. Signatures **fail-CLOSED in production** (503 when secret unset).
- **AMD:** Twilio machine → voicemail-drop (`AMD_LEAVE_VOICEMAIL=1`) or hangup.
- **DND fail-CLOSED** (TRAI): lookup fail = promotional BLOCK. Transactional unaffected.
- **Consent ledger** (`consent_ledger.py`): opt-out → instant cross-channel suppression + 90-day recording retention.
- Distributed call state (Redis, in-memory fallback). Minute metering (`usage.record_call_usage`, FAIL-OPEN). Multi-tenant white-label (`middleware/tenant.py`, FAIL-OPEN, subdomain + custom_domain).

---

## 7. AI Staff Team & Automation

**`app/platform/team.py` + `team_scheduler.py` — 15+ AI staff** (split by `product`):
- **Marketing:** Isha · Dev · Rohan · Neha (pipeline_ops)
- **Voice:** Swara · Tara · Arjun · Meera
- **Platform:** Boss · Kavya · Nikhil · Hermes (infra) · Guru/Vikram (code_upgrader) · Pranav/Vidya/Arnav (KPI engineers) · hostinger_hermes (apprentice)

Helpers: `staff_for_product()` · `/api/platform/team?product=`. Events → `agent_events` table. Dashboard `/app/team`. 3-tier status (working ≤20min / active ≤16h / offline).

**Auto-schedule (IST, 24 staff jobs total):** 06:30 blog · 07:00 content · 08:30 digest · 09:30 scrape/prospect · 10:30 email outreach+followups · 11:00 pipeline (Neha) · 14:30 midday-prospect · 16:00 afternoon-followups · 18:30 evening-wrap · Wed 12:30 weekly-marketing · Sat 04:00 hygiene (DLQ + celery trim) · Sun 05:00 kb-refresh · hourly Kavya health · 02:30 Arjun QA · 03:00 Meera trainer · 15-min growth-pulse · hourly reply-triage / ops-watchdog / auto-onboard · ~04:00 backups.
- **boot-grace:** heavy daily job ka window boot pe active ho to is boot pe SKIP (restart-storm prevent).

**Multi-agent (free-stack):** `coordinator.py` (planner/handoff/fanout/Reflexion/critic/debate/hierarchical) · `process_engine.py` (process-as-code, event-sourced journal, deterministic gates, human breakpoints) · `self_improve.py` (task→task FOREVER Celery-requeue loop, `SELF_IMPROVE_LOOP=1` ON, 15 actions) · `sales_team.py` (5-agent BANT, `SALES_TEAM=1` ON) · `fde.py`.
- Decision matrix: `docs/AUTOMATION.md` + `multi-agent-coordination` skill.

**Dead-man trio** (always-on): heartbeat (`data/job_heartbeats.json`) + revive-beat (*/20min) + watchdog `ensure_alive`.
- **RULE:** worker recreate ke baad `redis-cli llen celery` check; >500 = `del celery` (tasks transient/regenerable, beat re-schedules). `saturday_hygiene` auto-trims >800.

---

## 8. Outbound / Growth Engines (working)

- **Email outreach LIVE:** Hostinger SMTP `admin@leadsgenai.in` (`smtp.hostinger.com:465`). `AUTO_EMAIL_OUTREACH=true` → Rohan roz 10:30 personalized Hinglish cold-emails + Day-3/7 followups. Cap 25/day, MX-verified, warmup ramp + bounce auto-pause. SPF/DKIM/DMARC ALL SET.
- **Google Maps API LIVE** (Places API New) — prospector real phones+reviews (cap `PROSPECT_MAX_LOOKUPS=60`/run). OSM Overpass fallback.
- **Lead harvester** (`platform/lead_harvester.py`, `LEAD_HARVESTER=1` ON): prospector + SearXNG/Brave + data.gov.in + email-enrich. Niche rotation (39 niches) + city rotation (15-city pool).
- **⚠️ ToS-BLOCKED auto-scrape:** justdial/indiamart/sulekha/linkedin/fb/insta — auto-scrape KABHI nahi (manual CSV import hi unka path).
- **AI reply triage** (`reply_agent.py`, `REPLY_AGENT=1` ON): IMAP → intent classify → status + Hinglish draft (auto-send OFF ban-safe).
- **Omnichannel cadence** (`cadence.py`, ON) · **Sales pipeline** (`SALES_ENGINE=1` ON) + auto-proposal + AI closer.
- **Revenue automation** (ON): dunning · lifecycle nurture · client-health alerts · revenue digest · channel-experiments bandit (17 free+legal channels, auto-POST kahin NAHI) · growth optimizer.
- **WhatsApp = 1-click human send** (bulk auto = ban). **Telegram = first TRUE auto-post** (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_AUTO_PUBLISH=1`).
- **Native CRM sync** (`crm_sync.py`, `CRM_SYNC` OFF): Zoho (India DC) + HubSpot. UI: growth-tools "CRM Sync" tab.
- **Self-hosted tools** (`docker-compose.tools.yml`): SearXNG (ON) · ntfy phone-push `https://ntfy.leadsgenai.in` (ON) · changedetection.io.
- **Per-client:** `clients_store.py` + `auto_content.py` + `mini_site.py` (`/b/{slug}`) + `onboarding.py` (`AUTO_ONBOARD=1` ON: website → KB seed + first content pack).

---

## 9. Deploy Loop (detail → `leadgen-ops` + `hostinger-deploy` skills)

> **Source-of-truth = Windows.** Sandbox mount STALE ho jata hai. Memory/code edit SIRF Windows file-tools se.

1. `python scripts/prod_check.py`
2. `scripts\run_tests.bat` → **`pytest_run.log` Read karo** (~80+ green; full pytest team_pulse area pe hang ho sakta — targeted suites use karo)
3. Windows git push: `C:\PROGRA~1\Git\cmd\git.exe` (bat ke andar)
4. VPS pull via Git ka ssh: `C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204`
   - `cd /opt/leadgen && git pull`
   - `docker compose -f docker-compose.vps.yml build app`
   - `docker compose -f docker-compose.vps.yml up -d --no-deps app`
   - verify `/health` = `environment: production`
5. Verify me `sleep 16` + 2x health-check rakho.

**Deploy gotchas:**
- **Naya `@app.get` page-route add karne ke baad HARD RELOAD zaroori** (warna stale `.pyc` 404): container recreate, ya `pkill -9 -f uvicorn; find /opt/leadgen/app -name __pycache__ -prune -exec rm -rf {} +; restart`. Diagnostic: `scripts/check_route.py`.
- **Automation/loop code change = recreate app + worker + worker-heavy + scheduler** (sirf app NAHI — team_scheduler/self_improve worker+beat me run hote).
- Build pipe `| tail` exit-code maskta → `set -o pipefail`.
- compose service `worker-heavy` (hyphen) — galat naam pe poora `up` ABORT; pehle `config --services`.
- `Dockerfile RUN chown -R /app` slow/stall-prone — future fix `COPY --chown`.
- **Repeated worker recreate = celery flood risk** → `redis-cli llen celery` check.
- **CI** (`deploy-vps.yml`) = **GATE-ONLY**: build+deploy jobs `if: vars.DEPLOY_ENABLED=='true'` (UNSET) → `git push` se prod auto-deploy NAHI hota. Gate me import+prod_check+billing-truth = BLOCKING; ruff + full-pytest = non-blocking. Actual deploy = **MANUAL SSH (step 4)** — CI ka wait mat karo.

---

## 10. Work Quality Gate (HAR code task — MANDATORY)

> User feedback: same task Cursor sahi karta tha, yeh agent galat — wajah = Cursor pura repo index karta, yeh manually. Isliye yeh gate har code task pe.

1. **Context-first:** edit se PEHLE `Grep`/`Glob` se SAARE touch-points (callers, routes, similar feature, tests) dhoondo + relevant files PURA padho. FastAPI first-route-wins → duplicate route check.
2. **Source-of-truth = Windows:** edit se theek pehle file Read karo (stale sandbox content pe edit MAT karo).
3. **Pattern-match + additive:** padosi code ka convention copy; working code rewrite risky → additive prefer.
4. **Verify before "done":** change ke baad `/verify` (prod_check + targeted tests). "Ho gaya" sirf jab green.
5. Non-trivial change/debug/audit → pehle skill `fable-operating-manual` invoke (+ `leadgen-ops` deploy · `marketing-feature` naya feature · `systematic-debugging` bug).
6. **Improvement ≠ broken:** `prod_check` PASS ≠ "kuch banana nahi". Cross-path wiring gaps, untested fixes, dormant-but-wireable loops dhoondo + **SHIP karo**. Analysis pe ruk ke "ball tumhare court me" mat bolo jab real wireable value ho. Decide-and-ship.

---

## 11. Active Blockers / Pending USER-ACTION

> Env-unset = dormant + graceful skip (kuch toot-ta nahi). Inpe token mat jalao jab tak unlock na ho.

| Blocker | State | USER-ACTION needed |
|---|---|---|
| **Payments** | Razorpay removed 2026-06-18; manual UPI ab PRIMARY. **UPI admin-config path wiring IN-FLIGHT** (06-20, Section 19) — VPA dashboard se set, no recreate. | Feature verify+ship → `UPI_VPA` (ya admin UI) set karo. Pehle paid customer se pehle zaroori. |
| **DLT** | Individual request REJECTED | Udyam (MSME, FREE, udyamregistration.gov.in) cert se Proprietorship re-apply. Cert ready hai. DLT sirf cold-calling (Advanced) ke liye. |
| **Vobiz telephony** | Trial ~khatam | Recharge → DID kharido → `VOBIZ_CALLER_ID=+91<DID>` + restart. Cost ladder: Plivo ₹0.60 → Vobiz ₹0.45 → operator-direct ₹0.30-0.40. |
| **Calls untestable** | Vobiz recharge + DLT dono pending | Dono unlock hone tak outbound calling test nahi ho sakti. |

**External-blocked (user paperwork/approval — abhi mat chhuo):** missed-call callback (Vobiz DID + webhook) · GBP API auto-post (Google 60-day approval) · Meta/FB-IG auto-posting (app-review) · R2/B2 offsite (creds) · HA/2nd-server (spend).

**✅ Launch NOW possible:** Marketing tiers + inbound callbacks ko DLT/telephony NAHI chahiye. Sirf voice cold-calling DLT pe atki.

---

## 12. Legal & Compliance (CONFIRMED — compliance GATE code KABHI disable mat karo)

> NOTE: DLT/Udyam paperwork ko outbound conversation me recurring talking-point mat banao (user ko pata hai). PAR compliance GATE code (TRAI/DND/AI-disclosure/10am-7pm window) hamesha INTACT rakhna.

- **TRAI:** 140-series + DLT + DND scrub + 10am-7pm window + AI disclosure mandatory. Penalty ₹10L. AI-disclosure greetings wired ("ek AI assistant").
- **Foreign trunks** (Twilio/Telnyx/Vonage) India-domestic = ILLEGAL.
- **Pure minutes-resale bina license** = Telegraph Act violation. Legal resale = SaaS bundle (DLT/140 CLIENT ke naam) — industry standard.
- **WhatsApp bulk auto-send** = number ban. Cold auto-calls bina DLT = ₹10L risk → sirf inbound auto-callback.
- **DPDP Act 2023** rights + Grievance Officer in `/privacy`. Consent ledger + 90-day retention + right-to-be-forgotten purge (`agent_memory` + consent_ledger bridge).

---

## 13. Critical Gotchas & Hard-Won Lessons

**Environment/sandbox:**
- 🚨 **CLAUDE.md / SESSION_LOG sandbox-bash append KABHI nahi** (stale mount = mid-file corruption hua). Memory files SIRF Windows file-tools (Edit) se.
- Sandbox mount STALE ho jata file-tool edits ke baad → Windows side = source of truth. Verify Windows pe (bat chala ke log Read karo).
- Sandbox git index unreadable → Windows git via file-tools/Desktop Commander.
- Windows OpenSSH broken → Git ka `ssh.exe` use karo.
- **Bade multi-file edits same file pe parallel mat do** — file truncate ho jati hai.
- **Secrets KABHI committed file/CLAUDE.md/scripts me mat likho — sirf `.env`** (gitignored). `scripts/check_secrets.py` (/verify step-4 me wired; false-positive = line pe `# nosecret`).

**Code/runtime:**
- 🚨 **Windows `os.kill(pid, 0)` CTRL_C bhejta** — `_pid_alive` ctypes `OpenProcess` use karta. Yeh idiom dobara KABHI nahi.
- **Celery flood:** worker restart × `acks_late` redelivery → queue flood. `self_improve_tick` ab `acks_late=False` + Redis NX single-chain lock. Recreate ke baad `llen celery` check.
- **Public endpoint me KB/ML = thread + hard timeout** (3 prod-downs isi se).
- `.bat`: npm/git `.cmd` ko `call` ke saath; `timeout /t` fail → `ping -n N 127.0.0.1`. SSH command me `&`/`<` quoting todta (EXIT_9009) → smoke `.py` file me likho, ssh se chalao.
- **Worker asyncio teardown:** `_run_async` asyncio.run-style cleanup (cancel pending + gather + `shutdown_asyncgens` + `set_event_loop(None)`) — warna "Event loop is closed" log spam.

---

## 14. Onboarding Checklist — New Owner Day 1

1. **Padho:** yeh handoff → `CLAUDE.md` (lean memory, har turn load) → `docs/SESSION_LOG.md` tail (recent history).
2. **Access:** GitHub repo (`main`) · VPS SSH (`root@72.61.245.204`, key `C:\Users\Ratanshila\.ssh\id_rsa`) · Hostinger panel · domain DNS · `.env` on VPS (`/opt/leadgen/.env` — saare secrets yahin).
3. **Health check:** `curl https://leadsgenai.in/health` → `environment: production` hona chahiye.
4. **Local setup:** repo clone → `requirements.txt` → `python scripts/prod_check.py` se sanity.
5. **Samajh:** `app/main.py` (route mounts) → `app/api/marketing.py` (28-tab backend) → `app/billing/packages.py` (pricing truth) → `app/voice_agent/free_ai.py` (AI chain) → `app/platform/team.py` (staff).
6. **Pehla revenue unblock:** `UPI_VPA` set → marketing tiers sellable. (Voice = DLT + Vobiz recharge ka wait.)
7. **Flags dekho:** `GET /api/growth/infra/flags` = saare automation flags live on/off.
8. **Activation runbook:** `docs/SESSION_ACTIVATION_RUNBOOK_2026_06_16.md` (5 phases, env key + verify curl per item).

---

## 15. Key Files & Docs Map

**Code entry points:**
- `app/main.py` — route mounts, page routes
- `app/api/marketing.py` — marketing backend (28 tabs)
- `app/billing/packages.py` — **pricing single source of truth**
- `app/voice_agent/free_ai.py` — multi-provider AI chain
- `app/platform/team.py` + `team_scheduler.py` — AI staff + cron
- `app/niches.py` — 39 niches + band mapping
- `app/telephony/vobiz_handler.py` + `vobiz_stream.py` — calling
- `app/agents/` — coordinator, process_engine, self_improve, sales_team

**Must-read docs:**
- `CLAUDE.md` — lean working memory (authoritative current state)
- `docs/SESSION_LOG.md` — full dated history
- `docs/ADR_2026_06_11_Product_Split_Pricing.md` — pricing decision
- `docs/AUTOMATION.md` — automation loops decision tree
- `docs/SESSION_ACTIVATION_RUNBOOK_2026_06_16.md` — go-live checklist
- `docs/PRODUCTION_CUTOVER.md` · `docs/INFRA_HARDENING_GUIDE.md` · `docs/INFRA_UPGRADE_2026.md`
- `docs/API.md` · `docs/Competitor_Top20_Feature_Gap_2026.md` · `docs/PRODUCTION_READINESS_2026.md`
- Pricing research: `Niche_Pricing_Research.xlsx` · `LeadGen_Costing_Model.xlsx`
- Sales/marketing kits: `docs/Marketing_Kit_LeadGenAI.md` · `docs/Sales_Kit_Hinglish.md` · `Business_Playbook_Hinglish.md`

---

## 16. Skills & Slash Commands

- **skill_pack** (`platform/skill_pack.py`, `SKILL_PACK=1` ON): VPS agents ko `find/snippet_for`. **241 skills total** = 61 project + 141 agency-agents + 39 ECC pack (`data/skills_extra/*.md`, data-only = git pull pe live, NO rebuild).
- **Slash commands** (`.claude/commands/`, 7): `/verify` `/ship` `/checkpoint` `/learn` `/compact-check` `/optimize` `/test-expand`.
- **code_upgrader** (Vikram, `CODE_UPGRADER=1` ON): signals → free-LLM patch PROPOSALS (`data/code_patches.jsonl` + email) → admin approve API. Core code KABHI auto-apply nahi.
- **Flags registry:** `GET /api/growth/infra/flags` (AUTOMATION_FLAGS in growth.py — naya flag wahan add karo).
- Self-improve safety: `SELFIMPROVE_COST_CAP=50`, `SELF_IMPROVE_APPROVAL=1` (optional). Audit: `scripts/selfimprove_audit.py`.

---

## 17. Roadmap / Backlog (priority order)

**P0 (revenue-unblock, ₹0 cost):**
1. UPI admin-config feature verify+commit+deploy → VPA set → marketing tiers live-sellable (in-flight, Section 19).
2. Godfile wave-2 merge + Dependabot triage · Dashboard MUST-HAVEs remaining: filters · bulk actions · activity timeline. *(Speed-to-lead / round-robin / revenue-analytics already built per 06-20 audit.)*

**P1 (after DLT/Vobiz unlock):**
3. Voice cold-calling go-live (Udyam → DLT re-apply → Vobiz recharge + DID).
4. Missed-call callback wiring (Vobiz DID + webhook).
5. GEO visibility score (#11).

**P2 (external-blocked, wait for approval):**
6. GBP auto-post · Meta/FB-IG auto-posting · R2/B2 offsite backup · HA/2nd-server.

**Detail:** `docs/PRIORITIZED_BACKLOG.md` · `docs/ADVANCEMENT_ROADMAP_2026.md`.

---

## 18. Goals & Current State — Where The Project Stands (2026-06-20)

### North-star / mission
Indian local SMBs (chhote businesses) ke liye **₹0-marginal-cost SaaS** — sab AI free-stack pe — taaki industry-grade features competitor se sasta diye ja sakein (Dhanda/EZO · AdBanao · MyOperator · Vodex · GoHighLevel). Do products: Marketing automation + AI voice telecaller.

### Current standing (honest assessment)
- **Platform LIVE + stable:** leadsgenai.in, ~761 route-decorators (prod_check 752 routes), ~464 py files, 50 pages, Postgres+Celery+Qdrant, 13+ containers, monitoring + self-heal + backups.
- **"Sab free-buildable features DONE"** — SESSION_LOG repeated audits ka verdict (06-20 audit: NO HIGH security defects; speed-to-lead, lead round-robin, revenue analytics MRR/churn/LTV **already built+wired**). Jo bacha = external-blocked (paperwork/approval) YA polish.
- **Recent (06-20):** godfile refactor wave-1 main me merged (growth/marketing split) · Stripe webhook fail-CLOSED + 3 HIGH audit gaps closed (`test_hardening_gaps_2026.py`) · **UPI admin-config path wiring IN-FLIGHT** (Section 19).
- **Product 1 (Marketing): sellable ABHI.** Sirf UPI VPA unset = first-payment block (wiring in-flight). Sab content/social/mini-site/lead-capture/AI-image engines live.
- **Product 2 (Voice): code production-ready + cross-path-verified**, par commercially blocked — DLT (rejected → Udyam re-apply) + Vobiz recharge+DID. Calls tab tak untestable.
- **AI staff automation chal raha:** 24 scheduled jobs, self-improve forever-loop, multi-agent coordinator, daily email outreach + lead harvester + Telegram auto-post.

### Immediate goals (revenue-first, priority order)
1. **Pehla paid customer (Product 1)** — UPI admin-config feature verify+commit+deploy (Section 19) → VPA set → marketing tiers bech do. ₹0 cost.
2. **Voice unblock** — Udyam cert → DLT re-apply → Vobiz recharge + DID kharido → end-to-end call test → Product 2 go-live.
3. **Godfile refactor wave-2 merge** (niches/niche_knowledge/niche_scripts data-dict extraction — 4 commits on branch) → verify → merge to main.
4. **Dashboard MUST-HAVEs (remaining):** multi-condition filters · bulk client actions · client activity timeline/audit log. *(Speed-to-lead, round-robin, revenue analytics MRR/churn/LTV — already built per 06-20 audit.)*

### Medium-term goals
- Cold-email deliverability harden (dedicated cold-email domain + warmup; SPF/DKIM/DMARC already set).
- Voice latency upgrade (Silero/Smart-turn — needs torch install, OOM-careful, capacity-check first).
- External approvals jaise-jaise unlock: GBP auto-post · Meta/FB-IG auto-post · missed-call callback.

### Scale / north-star
- Multi-tenant white-label reseller (middleware fail-open already wired).
- MCP-as-product + A2A agent card (shipped) → API/agent-economy revenue channel.
- HA / 2nd server jab spend justify ho.

**Success metric:** first ₹ revenue → repeatable acquisition (AI staff already auto-prospect+outreach) → voice unlock = double product surface.

---

## 19. Files In Flight — WIP (as of 2026-06-20 PM)

### 🔴 Uncommitted — UPI admin-config feature (addresses #1 blocker; NOT committed yet)
Active in-flight work taaki UPI **bina redeploy** payable ho — yeh seedha first-revenue unblock karta:
- **`app/platform/upi_config.py`** (NEW, 127 lines) — runtime UPI VPA: env-first (`UPI_VPA`) + admin data-file fallback (`data/platform_upi.json` via `POST /api/admin/upi/configure`), taaki VPA dashboard se set ho — container recreate nahi chahiye.
- **`scripts/vps_set_upi_smoke.py`** + **`tests/test_upi_config.py`** (NEW) — smoke + unit tests.
- Modified (same feature): `app/api/activation.py` · `admin_ops.py` · `growth.py` · `marketing.py` · `public_site.py` · `webhooks.py` · `frontend/admin_dashboard.html` · `scripts/production_ready.py` · `tests/test_activation_readiness.py` · `tests/test_production_gaps.py`.
- **Next:** verify (prod_check + tests) → commit → deploy → VPA set → pehla customer payable.

### Other uncommitted
- **`scripts/vps_deploy_automation_fix.py`** (untracked) — one-shot deploy helper: boot-grace fix `52a27c4` cherry-pick + worker/app rebuild + catch-up jobs.
- **`docs/PROJECT_HANDOFF.md`** (yeh doc) · `.superpowers/` (tooling dir) · `CLAUDE.md` + `docs/SESSION_LOG.md` modified (06-20 entries logged).
- **`docs/PROJECT_SOP.md` ab COMMITTED hai** (repo me tracked) — pehle uncommitted tha.

### Godfile refactor — wave-1 MERGED ✓, wave-2 branch pe
- **Wave-1 (MERGED to main @ `32c229f`):** `growth.py` −797 / `marketing.py` −1060 → split into `growth_revenue` / `growth_crm` / `growth_deliverability` / `growth_feature_flags` + `marketing_tools` / `marketing_models`. **Landmine avoided** — branch main ke LLM-stream-TTS prod commits se PEHLE fork hua tha; isolated worktree me reconcile (pehle main→branch merge, symbols verify, fir ff-promote). Ab main pe live.
- **Wave-2 (`refactor/godfiles-2026-06-20`, 4 commits, UNMERGED):** data-dict extraction — `NICHES` → `niches_data.py` · `NICHE_KNOWLEDGE` → `niche_knowledge_data.py` · `NICHE_SCRIPTS`/`NICHE_CALL_SCHEMA` → `*_data.py`. Verify + merge pending.

### Other branches / Dependabot
- `feature/readiness-infra-2026-06-20` (0 unmerged vs main) · `2026-06-17-yezh`, `copilot/vscode-mjy4va0d-lafx` (stale) · 2× `worktree-2026-01-03T*` (stale Jan → cleanup).
- **Dependabot PRs (origin):** python 3.14-slim · elevenlabs 2.53.0 · mypy 2.1.0 · packaging 26.2 · appleboy/ssh-action 1.2.5 · docker/login-action 4 · setup-buildx-action 4 · google deploy-cloudrun 3 · setup-gcloud 3 · 2× python-minor-patch → review/merge ya close.

---

## 20. What We Tried But Failed — Dead Ends & Hard Lessons

> Yeh section isliye taaki naya owner usi deewar pe sar na maare. Format: **kya try kiya → kyun fail → ab kya.**

### Telephony / calling (sabse zyada dead-ends)
1. **DLT Principal Entity — REJECTED** (Tata DLT Ref `100000000046604`): reason "Request cannot be raised by Individuals". Individual PAN (BONPD6321P) se apply kiya tha. → **Fix path:** Udyam (MSME, free) cert se Proprietorship → re-apply.
2. **Caller-ID spoof / unverified DID** (2026-06-07): Vobiz Call API → `"from parameter leadgenfs is not a valid number"`; FreeSWITCH originate spoof → `RECOVERY_ON_TIMER_EXPIRE` (Vobiz INVITE drop). → **Lesson:** verified DID + KYC + recharge zaroori; spoofing kaam nahi karta.
3. **Foreign trunks (Twilio/Telnyx/Vonage) India-domestic** = ILLEGAL (ILD toll-bypass, DLT impossible). Twilio sirf international fallback.
4. **SIM box / GSM gateway / personal-SIM auto-dialer** — criminal (raids) / FUP disconnect+blacklist. Outright rejected.
5. **Exotel** — KYC stuck `notstarted`; Voicebot applet ka **koi public API nahi** (dashboard/support-only); support emailed par unblock nahi hua → **Exotel ENTIRELY DELETED 2026-06-18**, Vobiz pe switch.
6. **Vobiz Speak XML** — voice/language attributes unsupported (sirf minimal `<Speak>text</Speak>`), default TTS robotic → streaming + EdgeTTS pe shift.

### Payments
7. **Razorpay** — API ne 401 auth-failed diya (payment-recon ne pakda); key-regen se bhi stabilize nahi hua → **Razorpay ENTIRELY REMOVED 2026-06-18**. Ab manual UPI (`UPI_VPA`). Stripe international ke liye intact. **NOTE:** stale `GO_LIVE_CHECKLIST.md` abhi bhi Razorpay creds list karta — ignore karo, superseded.

### AI providers (free-tier walls)
8. **Gemini free-tier per-MODEL quota** — gemini-2.5-flash sirf 20 req/day, khatam → default `gemini-2.5-flash-lite` (highest free quota).
9. **Cerebras 429 `queue_exceeded`** burst pe — primary nahi ban saka; low-priority fallback rakha (Groq/Mistral catch karte). Circuit-breaker added.
10. **Pollinations image** — anonymous ab **402 Payment Required** → `POLLINATIONS_API_KEY` token chahiye; bina key SVG-poster fallback.
11. **Premium STT/TTS** — user ne REJECT kiya. Free-only = hard constraint (gap nahi).
12. **6s LLM timeout** experiment — Cerebras kat-ta tha, weak fallbacks → revert to 8s.

### RAG / architecture choices abandoned
13. **GraphRAG** — hundreds of LLM calls = free quota udao → rejected. **Graphiti** — Neo4j infra chahiye → skip. → **LightRAG** chuna (incremental, free-embed), opt-in OFF.

### Infra / deploy traps (fix ho gaye, par real time khaaya)
14. **edge-tts 6.1.9 → HTTP 403** (MS ne Sec-MS-GEC token rotate kiya) → pin `edge-tts>=7.2.0`.
15. **Stale `.pyc` 404s** — naye page-routes 404 dete the despite correct code (P2/P7 login/analytics pe laga); normal `systemctl restart` kaafi nahi → **HARD RELOAD** (`pkill -9 uvicorn` + `rm __pycache__`). Ab documented gotcha.
16. **Cloud-logging init bina GCP creds** startup minutes block karta tha → attempted-flag + creds-check.
17. **Celery queue flood** (2501 `self_improve_tick`) — `acks_late` redelivery × repeated worker restart → `acks_late=False` + Redis NX single-chain lock.
18. **Hostinger SMTP** — pehle 2 attempt fail (typo/truncated password); titan.email fail (Hostinger native mail, Titan nahi) → 3rd sahi password OK.
19. **`auto_callback.py` (CallManager path)** banaya phir DELETE kiya — existing inquiry-callback se redundant + missed-call DID-blocked. (Lesson: dead/dup code mat chhodo.)

### Can't-auto (policy / ToS walls)
20. **JustDial / IndiaMART / Sulekha / LinkedIn / FB / Insta scraping** — anti-bot + IT-Act/ToS → auto-scrape KABHI nahi; **manual CSV import hi ekmaatra path**.
21. **Torch/Silero VAD install** — VPS pe install NAHI kiya (current RAM pe OOM risk); user go-ahead + capacity-check pending.

### External-blocked (code se complete nahi ho sakta — third-party pe wait)
22. **Missed-call callback** (Vobiz DID + webhook) · **GBP auto-post** (Google 60-day approval) · **Meta/FB-IG auto-post** (app-review) · **R2/B2 offsite backup** (creds) · **HA / 2nd-server** (spend).

---

## Appendix — Quick Reference Card

```
LIVE URL      : https://leadsgenai.in
REPO          : github.com/sumitrevolt/leadgenrationaivoiceagent (main)
VPS           : root@72.61.245.204 (Mumbai, /opt/leadgen)
SSH           : C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204
HEALTH        : curl https://leadsgenai.in/health  (expect environment:production)
SECRETS       : /opt/leadgen/.env (VPS) — NEVER in repo/CLAUDE.md
PRICING TRUTH : app/billing/packages.py
AI CHAIN      : app/voice_agent/free_ai.py
FLAGS         : GET /api/growth/infra/flags
DEPLOY        : prod_check → run_tests.bat → git push → VPS pull+build+recreate app → /health
PROVIDER      : Vobiz (telephony) · Mistral (LLM) · Groq (STT) · EdgeTTS (TTS) — ALL FREE
PAYMENTS      : Manual UPI (Razorpay removed) · Stripe international
BLOCKERS      : UPI_VPA unset · DLT rejected (Udyam re-apply) · Vobiz recharge pending
```

---

*End of handoff. Current-state facts `CLAUDE.md` se; agar koi cheez purani lage to `CLAUDE.md` + `docs/SESSION_LOG.md` tail authoritative hai.*
