# CLAUDE.md — LeadGen AI Platform (enterprise onboarding + lean working memory)

> **Token discipline:** Yeh file har turn load hoti hai — lean rakho. Dated history → `docs/SESSION_LOG.md` (auto-load NAHI). Deep knowledge → `memory/` (section 9). Build/incident logs YAHAN mat likho. **Code vs memory conflict = code wins — phir memory fix karo.**
> Naya session / cold-start? **`docs/HANDOFF.md`** = master handoff (infra map, sharp edges, SOP pointers). (2026-07-05)

## 0. LOOP ENGINEER MODE (triggers: /loop /audit /fix /harden /production-ready /scheduler /agent-loop)

On any trigger above — or auto when tests/build/lint/a-page/workflow/scheduler break — enter **Loop Engineer mode**: **inspect → plan → implement → test → verify → record → fix → repeat** until a stop rule is *proven*. **Never "done" without evidence; never stop at planning/audit — implement + verify.**
- **Wear all 8 hats every loop** (a change ships only if it passes ALL): Principal SaaS Architect · Staff Backend Engineer · AI Agent Architect · Voice AI Engineer · SRE · Security Engineer · QA Lead · Product Engineer. Full role defs = `docs/LOOP_ENGINEER.md`.
- **Permanent rules:** never stop at audit · never "done" without proof · no fake/stubbed/placeholder work passed off as working (real `/demo`/SVG-fallback/INERT-flag/test-double = fine) · never weaken a compliance gate (§5) or security · never ignore existing architecture (copy neighbour) · never duplicate routes/pages/workflows (grep all split routers first) · always check the affected cross-system touch-points (callers/routes/tests/scheduler/workers/Postgres/Redis/Qdrant/voice-both-paths/dashboards/admin/billing).
- **Read first:** `progress.md` (loop ledger) + this file, before touching anything.
- **After every loop:** append a `## Loop Run` block to `progress.md` (Date / Goal / Inspected / Problems Found / Changed / Tests Run / Verification Evidence / Risks / Remaining / Next Highest Priority).
- **Verify checkpoint each loop:** targeted pytest + `prod_check.py` + `/health`=`environment:production` (§6 Definition of Done). Reply in the CANONICAL 9-field loop format (`docs/LOOP_ENGINEER.md`): Goal / Inspected / Problems Found / Changed / Tests Run / Verification Evidence / Risks / Remaining / Next Highest Priority.
- **Highest-impact order** = `docs/LOOP_ENGINEER.md`, BUT `## Current State` sprint goal wins when it conflicts.
- **Stays inside the gates:** §5 compliance + secrets, §6 DoD, §8 no commit/push/deploy without the user asking. A "fix" that weakens a compliance gate = **ABORT**, not a fix.
- **Full spec** (8 role defs · permanent rules · loop anatomy · cross-system inspect list · 15-item production-ready checklist · canonical 9-field output format): `docs/LOOP_ENGINEER.md`.

## 1. PROJECT CHARTER

FastAPI SaaS (**LIVE: https://leadsgenai.in**, single Hostinger VPS Mumbai) that sells **DO alag products** to small Indian local businesses: (1) **AI Automated Marketing** = MAIN product — Main ₹1,999/mo + Combo/Advanced ₹5,999/mo (voice callback sirf ek FEATURE, 500 min); (2) **AI Voice Calling Agent** = standalone full AI telecaller, flat per niche-band ₹4,999/₹9,999/₹19,999/mo (DLT-gated for cold outbound). Money path: free lead magnets (`/audit`, `/site-audit`, `/demo`) + programmatic SEO + auto email-outreach → inquiry → `/pricing` → `/start` → **manual UPI (primary)** / Stripe (international only) → subscription + top-up minute packs. Entire AI stack = **FREE providers only** (user mandate — koi paid STT/TTS/LLM nahi). "Marketing + voice bundle" USP framing GALAT hai — use mat karo. Repo: github.com/sumitrevolt/leadgenrationaivoiceagent (main). Currently 1 real paying customer (jiya makeover); first invoice INV/2026-27/0001.

## 2. ARCHITECTURE MAP

```
Internet ──> Caddy (host, TLS leadsgenai.in) ──> leadgen_app :8000  (FastAPI, Docker, uvicorn WEB_CONCURRENCY=2, HTTP-only)
                                                    ├── Postgres leadgen_db  ── via PgBouncer :6432   (SQLite = rollback-backup only)
                                                    ├── Redis leadgen_redis :6379   (Celery broker + call-state + cache; DLQ = dlq:failed_tasks)
                                                    ├── Qdrant 127.0.0.1:6333       (RAG: single kb_main, namespaces niche:/client:<id>/skills)
                                                    ├── leadgen_worker (Celery, concurrency=4) + leadgen_scheduler (beat)  [--profile celery]
                                                    ├── FreeSWITCH  +  WS voice: /api/telephony/vobiz/stream/{token} (L16/16k)
                                                    └── Obs stack: Prometheus/Grafana/Alertmanager/Loki/Tempo/Uptime/Gatus (~13+ containers)
App ~700+ routes; frontend/ = server-rendered HTML (28-tab marketing.html, /app/automation Mission Control, /app/office HQ, 4 dashboards = 1 admin + 3 customer forks)
```

External deps (purpose · detail in `memory/integrations.md`): **Mistral** mistral-small-latest → LLM primary · **Groq** → LLM fallback + STT whisper-large-v3 primary · **Cerebras** → free 120B fallback (429-prone) · **Gemini** → VOICE-scoped primary (`VOICE_GEMINI_PRIMARY=1`, 9-key rotation pool `data/voice_gemini_keys.json`) + audio STT fallback · **NVIDIA NIM / SambaNova / OpenRouter** → deep-tail LLM · **EdgeTTS** hi-IN-SwaraNeural → TTS (free) · **Pollinations** → AI images/video · **Vobiz** → telephony provider (India SIP; Twilio = international-only fallback; Exotel DELETED) · **Hostinger SMTP/IMAP** admin@leadsgenai.in → outreach + reply-triage · **Google Maps Places (New)** → prospecting · **SearXNG** (self-host) → websearch · **ntfy** (self-host) → phone push · **WhatsApp** Meta Cloud + own WAHA :3111 → 1-click human send · **Stripe** → intl payments · **UPI manual** (`UPI_VPA`) → primary payments (Razorpay REMOVED) · **Sentry** → errors (ARMED) · **rclone → Google Drive** → offsite backup (LIVE, restore PROVEN) · **GHCR** → images. LLM chain lives in `app/voice_agent/free_ai.py` (~line 420) with escalating 429 circuit-breaker (60s→30min).

## 3. COMMANDS

- **Install (dev, py3.12):** `python -m venv .venv` then `.venv\Scripts\pip install --no-deps -r requirements.lock.txt` (lock = single source; requirements.txt/pyproject = reference only)
- **Run dev:** `.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000` [UNVERIFIED locally — import verified via prod_check]
- **Tests (full):** `scripts\run_tests.bat` → **phir `pytest_run.log` Read karo** (~80+ green; full suite team_pulse area pe HANG ho sakta — targeted suites prefer)
- **Test (targeted/contract):** `.venv\Scripts\python.exe -m pytest tests/test_billing_truth_2026.py -q`
- **Lint:** `.venv\Scripts\python.exe -m ruff check app` (CI me non-blocking)
- **Verify gate:** `.venv\Scripts\python.exe scripts\prod_check.py` + secrets scan `scripts\check_secrets.py` (ya `/verify` slash command)
- **Build+Deploy (MANUAL — CI `deploy-vps.yml` = GATE-ONLY, `DEPLOY_ENABLED` unset):** Windows git push (`C:\PROGRA~1\Git\cmd\git.exe`) → SSH `C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204` → `cd /opt/leadgen && git pull && docker compose -f docker-compose.vps.yml build app && docker compose -f docker-compose.vps.yml up -d --no-deps app` → verify `/health` = `environment:production` (sleep 16 + 2x check). Full runbook: `memory/playbooks.md` + `hostinger-deploy` skill.
- **Migrations:** `alembic upgrade head` (prod: container me; `DB_CREATE_ALL=0` = Alembic-only)

## 4. CODE STANDARDS (derived from codebase — impose mat karo, copy karo)

- Async FastAPI; domain routers in `app/api/` (godfile-split 2026-06-20: growth/marketing routes ab `growth_revenue`/`growth_crm`/`growth_deliverability`/`growth_feature_flags` + `marketing_tools`/`marketing_models` me bhi), engines in `app/platform/`, voice in `app/voice_agent/` + `app/telephony/`, billing in `app/billing/`.
- Naming: snake_case modules/functions, PascalCase classes; config via `app.config.settings` (pydantic-settings) + runtime flags via `os.getenv` at call-time.
- Error handling: defensive try/except + graceful degradation — external API call KABHI route crash nahi karta; **fail-OPEN** for billing meters/tenant middleware, **fail-CLOSED** for compliance (DND lookup) + webhook signatures in prod.
- Logging: `from app.utils.logger import setup_logger; logger = setup_logger(__name__)`; Sentry auto in production.
- Feature pattern: env-flag-gated, INERT default, additive over rewrite; comments often Hinglish; naya admin feature = UI tab SAATH hi (API-only = adhoora).
- ML assets: image-bake + off-loop load (`asyncio.to_thread`) + deadline + disable-switch — public endpoint me KB/ML = thread + hard timeout (3 prod-downs isi se).

## 5. CRITICAL INVARIANTS (NEVER break — compliance gates disable karna FORBIDDEN)

- **TRAI/telecom:** DND scrub **fail-CLOSED** (lookup fail = promotional BLOCK) · AI-disclosure at call start ("ek AI assistant") · promo calling-window **9am–7pm** (code-conservative; TRAI actual 9–9) · consent ledger opt-out = INSTANT cross-channel suppression · foreign trunks (Twilio etc.) India-domestic = ILLEGAL · cold auto-calls bina DLT = nahi (sirf inbound auto-callback) · pure minutes-resale = Telegraph Act violation; legal = SaaS bundle, DLT/140 CLIENT ke naam.
- **DPDP Act 2023:** purpose limitation + data minimisation + consent basis for first contact · 90-din recording retention · purge API + Grievance Officer in /privacy · lead data cross-client leak KABHI nahi (customer-isolation).
- **Billing truth:** `packages.py` = single source (sync via `subscription._sync_plans_from_packages`); pricing change = packages.py + `test_billing_truth_2026.py` SAATH; Growth ₹2,999 = LEGACY hidden (`get_public_packages()` use karo); GST sirf `GST_GSTIN` set pe; invoice Rule-46 sequential `INV/2026-27/0001`.
- **Secrets sirf `.env`** (gitignored) — kabhi committed file/CLAUDE.md/scripts me nahi; API keys env se only; `sk_` Pollinations key KABHI URL me nahi (proxy route only).
- **Ban-safety:** WhatsApp bulk auto-send = number ban (1-click human send only; auto gated OFF) · ToS-blocked auto-scrape (justdial/indiamart/sulekha/linkedin/fb/insta) REFUSED — manual CSV hi path.
- 🚨 **platform_dial = HARD OFF (USER-MANDATE 2026-07-05)** — agent IVR/bots ko "interested" mark kar raha tha + real paisa burn. 3-layer kill (`PLATFORM_DIAL_DAILY=0` + `data/platform_dial.json enabled:false` + scheduler override paused). Re-enable SIRF user go-ahead + test-allowlist + bot/IVR detection ke baad.
- FastAPI **first-route-wins** — naya route add karne se pehle duplicate grep (saare split routers me). Web process KABHI heavy job na chalaye (Celery only). Never write prod DB from local. VPS pe `reset --hard`/blind rebuild KABHI nahi (tree chronically dirty — surgical deploy).

## 6. TESTING PROTOCOL (Definition of Done)

Change safe = **(1)** context-grep pehle (callers/routes/tests) **(2)** targeted pytest suite green (naya behaviour = naya test) **(3)** `prod_check.py` PASS **(4)** `check_secrets.py` clean diff **(5)** duplicate-route grep clean **(6)** voice change → `scripts/agent_tester.py` scorecard **(7)** deploy ke baad `/health` + smoke. Bina evidence "done" MAT bolo. Pricing/plan/public-API touch = contract test FIRST (tdd-contract-first skill). CI gate (import + prod_check + billing-truth) BLOCKING hai; full pytest CI me non-blocking — isliye local discipline hi asli gate hai.

## 7. KNOWN LANDMINES (yeh sab pehle toot chuke — `memory/incidents.md` me postmortems)

- Naya `@app.get` page-route → **stale .pyc 404** = hard reload zaroori (pycache purge ya container recreate). Deploy build pipe `| tail` exit-code mask karta → `set -o pipefail`.
- Sandbox mount STALE ho jata → **Windows file-tools = source of truth**; CLAUDE.md/SESSION_LOG bash-append KABHI nahi (mid-file corruption hua). Windows `os.kill(pid,0)` = CTRL_C bhejta (ctypes OpenProcess use). Bade multi-file edits same file pe parallel = truncation.
- **USE_SILERO_VAD=0 rakhna** (2026-07-03: =1 ne har phone call "deaf" bana diya — 64ms window real speech ko silence keh raha tha). EdgeTTS `>=7.2.0` warna 403. Har `reply()` guard `reply_stream_sentences()` me bhi mirror karo (close-signals stream path pe silently missing the).
- Rate limits: Groq TPD content-heavy days pe khatam · Cerebras 429-prone · NVIDIA 40 RPM + ~5k LIFETIME credits (deep-tail hi rakho) · Gemini free quota → 9-key rotation · email outreach cap 25/day + warmup · `PROSPECT_MAX_LOOKUPS=60`/run.
- Scheduler: boot-grace (heavy daily job window boot pe active → SKIP; restart-storm prod-down lesson) · worker recreate ke baad `redis-cli llen celery` >500 = `del celery` · cache TTL must EXCEED poll interval.
- `.env.example` + `pyproject.toml` DRIFTED hai (Deepgram/ElevenLabs/gemini-1.5 stale — real stack = section 2). `requirements.lock.txt` hi truth. Compose service `worker-heavy` (hyphen) — galat naam = poora `up` ABORT.
- Windows: OpenSSH broken → Git ka ssh.exe; `.bat` me `call` npm/git; SSH one-liner quoting todta → script file likho, log Read karo. Full list: `windows-dev-gotchas` skill.

## 8. AGENT OPERATING RULES (Claude Code is repo me aise kaam kare)

- **Hinglish (Roman) me HI reply** — concise, kam formatting. **Canary: HAR reply ke END me akeli line `🐦 pelican`** (model-emitted, hook se NAHI — context-drift check).
- **Work Quality Gate (har code task):** (1) context-first — edit se PEHLE parallel Grep/Glob se saare touch-points + files PURA padho (2) Edit se theek pehle Read (stale content pe edit mat karo) (3) padosi convention copy, additive prefer (4) `/verify` green hone tak "done" nahi (5) skills invoke karo: `fable-operating-manual` (non-trivial) / `context-first` (code edit) / `systematic-debugging` (bug) / `llm-council-decision` (ambiguous strategy) (6) dormant-but-wireable gaps SHIP karo — decide-and-ship, over-ask mat karo (7) Discover→Contract→Execute→Self-review→Evidence; automation change = flag+idempotency+retry/DLQ+metrics+rollback+runbook.
- **Never:** `.env` values touch/overwrite · destructive migration/`DROP`/`reset --hard` bina explicit user confirm · `git add -A` (parallel Cursor edits — shared files diff karo) · commit/push bina user ke kahe · secrets kisi file me.
- Plan before multi-file edits (`plan-then-build`); small reviewable diffs; naya flag `AUTOMATION_FLAGS` registry me add karo.
- **Architecture change = same session me CLAUDE.md ## Current State + `memory/` write-back** (incomplete session warna). AGENTS.md = CLAUDE.md ki byte-copy rakho (Copy-Item se re-sync).
- DLT/Udyam paperwork ko recurring talking-point mat banao (user ko pata hai) — par compliance GATES kabhi disable nahi. Free stack only — koi paid AI service add nahi.

## 9. MEMORY PROTOCOL

**Read `memory/INDEX.md` first** before any non-trivial task — load ONLY task-relevant files (decisions/glossary/integrations/incidents/playbooks/backlog). **Write-back same session:** naya decision → `decisions.md` (append-only ADR), incident → `incidents.md`, procedure → `playbooks.md`, parked idea → `backlog.md`. No secrets ever (env var NAMES ok, values never). Every entry dated YYYY-MM-DD + atomic. Code vs memory disagree = code wins, phir memory fix. Tiers: `## Current State` niche (hot cache, ≤40 lines) · `memory/` (repo knowledge base) · `docs/SESSION_LOG.md` (dated history archive) · `~/.claude/.../memory/` (Claude session auto-memory).

## Current State (Tier-1 working memory — max 40 lines, monthly prune → decisions.md)

**Sprint goal:** GTM 0→1 — pehle paid customers on Marketing product (jiya makeover = only real paying customer); mid-funnel bottleneck (Hot Queue `/app/inbox` + dialer sprint), 1st paid target ≤7d from 2026-07-02.

**Last 3 significant decisions:**
- 2026-07-10: **ADR-075 Control-plane atomicity + token-discipline layer, default-OFF.** dev_control me REAL race fixes: `claim`/`heartbeat` ab conditional-UPDATE atomic (lost-update + lease-steal band) + naya `POST /dev-tasks/claim-next` poll. NEW `claims.py`/`context_packets.py` (6k/12k/24k size-tier packets, sha256 cache key task+commit+file-hashes+contract, guardrails-reuse redaction, prior-failure carry-forward)/`budgets.py` (68k staged budgets, 70/85/100 checkpoints, 2-attempt-then-escalate, 12-field handoff)/`health.py` (free_ai breaker snapshot). ADR-073 ke "29/29 tests" tree me the hi NAHI — in-tree coverage 38 tests me restore/extend. Locked httpx-0.28 vs starlette-0.35 TestClient breakage = conftest signature-guarded shim (6 delivery tests RED→GREEN). Evidence: 96/96 targeted green, `prod_check.py` PASS (1065 routes/0 gaps), secrets clean. No commit/deploy.
- 2026-07-10: **ADR-074 Health-gated Hot Queue Revenue Brief, default-OFF — SHIPPED.** Council ranked health-gated revenue brief above brief-only and watchdog-only. Reuses `office_briefing` + `/app/inbox` at 08:15 IST; no duplicate queue or auto-contact channel. `HOT_QUEUE_BRIEF_DAILY` fail-closed on unknown queue/recent job failure, cross-process idempotent, retry/DLQ + dual boot-grace + Celery/in-process parity wired. FastAPI 0.139 lazy-route gate fixed (85→1064 routes, 628→0 wiring gaps). Deployed 2026-07-10 as 3 surgical commits `912536e` (ADR-074, 10 files/+575) + `32332bf` (route inspection, 6 files/+94) + `7db1fab` (import path stragglers, 3 files/+6) + earlier `4aaf804` (UPI 404 fix); VPS HEAD `7db1fab8`, 2x `/health = production` healthy, `POST /api/upi/submit` = 401 (auth-enforced). Flag OFF in prod env. **Worker + scheduler containers still on pre-ship image (only `app` rebuilt per §3 runbook) — must rebuild both before flipping `HOT_QUEUE_BRIEF_DAILY=1`.**
- 2026-07-10: **ADR-073 Hybrid Flagship Control Plane Phases 2-6 + enterprise invariant gate, default-OFF.** Planner(`route_preview`)/enforcer(gateway) split; `DevTaskUsage`+migration 016 ledger; draft-only `runner.py`+`locks.py`+`tasks/dev_worker.py` (REVIEW-ONLY, `apply_patch` REFUSES); `reconcile.py` DB-truth lease reclaim; `deploy.py` fail-closed human approval token; `delivery.py` evidence+draft notify; `/api/dev-tasks/*` + `/app/dev-control` cockpit; `dev_control_gate.py` (8 invariants) in `prod_check.py`. All OFF by default; no commit/deploy. (ADR-072 gateway detail → decisions.md.)
**Blockers / USER-action pending (env-unset = dormant, graceful skip):**
- ~~LIVE billing debt: `/api/upi/submit` = 404~~ — **SHIPPED 2026-07-10 (commit `4aaf8040`, HEAD on VPS)**: surgical +1 line (BaseModel import), 2x `/health = production` healthy, `POST /api/upi/submit` = HTTP 401 (auth-required, not 404). Payment collection unblocked.
- DLT cold-outbound: Udyam re-apply user-side pending (transactional/test calls work fine).
- Pending user keys/actions: `POSTHOG_API_KEY` · WAHA QR scan · `.codex` key rotate · `STUDIO_ENTITLEMENT_GATE` flip · `LEADGEN_SCHEDULER_SECRET` (unset = recovery endpoint dormant).
- EXTERNAL-blocked (token mat jalao): missed-call DID webhook, GBP API approval, Meta app-review, HA 2nd server.
- ~~`gh` CLI auth broken~~ — WORKAROUND FOUND 2026-07-07: `GITHUB_TOKEN`+`GITHUB_PAT` env vars invalid, injected fresh per-shell (not in any dotfile, can't unset permanently) — prefix `env -u GITHUB_TOKEN -u GITHUB_PAT` on any `gh` command to fall back to the valid `sumitrevolt` keyring login (verified with a real API call).

**Next action:** UPI 404 + ADR-074 + ADR-075 + route inspection + import fixes ALL SHIPPED as of 2026-07-10. VPS HEAD `7db1fab8` on `main`. Shared tree now clean of the ADR ships — remaining uncommitted = 3 untracked docs (`docs/superpowers/plans|specs/2026-07-10-product-one-video-creative-pipeline-*`, other-session WIP) + `.commandcode/` (unclear artefact). Big session-lesson: sandbox bash mount can systematically lie about file contents (73 "syntax broken" + 14 "null-byte" reports were all mount corruption, not real disk state); trust Windows Read/PowerShell as truth, verify with Windows Python `ast.parse` before ANY commit. Highest priority next = (1) rebuild worker + scheduler containers before flipping `HOT_QUEUE_BRIEF_DAILY=1` (docker compose build worker scheduler + up -d --no-deps worker scheduler) (2) NVIDIA key rotation (3) `/upi/pending` duplicate-route collision cleanup (admin_ops.py:522 vs upi_payments.py:87, pre-existing) (4) full `run_tests.bat` under project image. Keep `EMAIL_WARMUP`, WhatsApp auto-send, voice-close WhatsApp, and platform dial OFF.

**Ops facts (hot):** Company inboxes = `admin@leadsgenai.in`, `sunny@leadsgenai.in` only · `SOCIAL_PREFS_HONOR` default OFF (draft prefs dormant until operator flip) · Scheduler = Celery durable (`RUN_IN_PROCESS_SCHEDULER=0`, rollback = `=1`+`WEB_CONCURRENCY=1`) · 25 staff jobs (incl. new `hot_queue_brief` 08:15 IST, dormant flag OFF) + dead-man trio alive · WhatsApp auto-send OFF (`WHATSAPP_AUTO_SEND=0`, `VOICE_CLOSE_WHATSAPP=0`; 1-click only) · UPI pay-info ARMED + `/api/upi/submit` LIVE (401 with auth = correct, 404 fixed 2026-07-10 `4aaf8040`) · `HOT_QUEUE_BRIEF_DAILY` unset in prod (OFF — must rebuild worker+scheduler containers before flipping ON) · NOTIFY_EMAIL set · Sentry ARMED · offsite backup LIVE (restore proven) · MCP `/mcp` gated (`FASTAPI_MCP_TOKEN`/allowlist) · 250 skills in skill_pack · Slash commands: `/verify` `/ship` `/checkpoint` `/learn` `/compact-check` `/optimize` `/test-expand`.
