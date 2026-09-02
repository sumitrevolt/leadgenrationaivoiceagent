# PROJECT SOP — LeadsGenAI (leadgenrationaivoiceagent)

> **Standard Operating Procedure** — engineering + business dono. Single source of "kaise kaam karna hai".
> Live: https://leadsgenai.in · Repo: github.com/sumitrevolt/leadgenrationaivoiceagent (main) · VPS: Hostinger Mumbai
> Last updated: 2026-06-22 · Owner: Sumit · **2026-06-22 Final Advancement Council = GREEN** (no procedure change — gates clean, lever = GTM; verdict `PROJECT_HANDOFF.md` §27)
>
> **Scope note:** Yeh SOP *procedure* batata hai. Current-state facts (pricing/infra/env) ka source-of-truth `CLAUDE.md` hai — koi conflict ho to CLAUDE.md jeetta hai. Detailed history `docs/SESSION_LOG.md`.

---

## 0. Products (ek line me clarity)

DO alag products hain — kabhi "bundle" mat bolo:

1. **AI Automated Marketing** = MAIN product (chhote local businesses ke liye). AI voice agent iske Advanced tier ka *ek feature* hai (inquiry callback, qualification, follow-up).
2. **AI Voice Calling Agent** = ALAG standalone product (full AI telecaller, DLT-gated).

---

# PART A — ENGINEERING SOP

## A1. Environment & Access (pehle yeh samjho)

| Cheez | Rule |
|---|---|
| **Source of truth** | **Windows file-system.** Sab edit Windows file-tools (Read/Write/Edit) ya Desktop Commander se. |
| **Sandbox mount** | Edits ke baad **STALE** ho jata hai — verify hamesha Windows side pe. |
| **CLAUDE.md / SESSION_LOG** | SIRF Windows file-tools (Edit) se. **Bash-append KABHI nahi** (mid-file corruption hota hai). |
| **Git** | Windows git: `C:\PROGRA~1\Git\cmd\git.exe`. Sandbox git index unreadable. |
| **SSH** | Windows OpenSSH broken → **Git ka ssh** use karo: `C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204` |
| **Secrets** | SIRF `.env` (gitignored) me. Code/CLAUDE.md/scripts me KABHI nahi. `scripts/check_secrets.py` se verify. |

## A2. Work Quality Gate — HAR code task pe (USER-MANDATE, skip mat karo)

Yeh gate isliye hai kyunki aadhe context pe edit = galat output. Sequence:

1. **Context-first:** Edit se PEHLE `Grep`/`Glob` se SAARE touch-points dhoondo (callers, routes, similar feature, tests) + relevant files **PURA** padho. FastAPI **first-route-wins** → duplicate `@router`/`@app` route check zaroori.
2. **Source-of-truth = Windows:** Edit se theek pehle file Read karo (stale sandbox content pe edit mat karo).
3. **Pattern-match + additive:** padosi code ka convention copy karo. Working code rewrite risky → additive prefer.
4. **Verify before "done":** change ke baad `/verify` (prod_check + targeted tests) chalao. "Ho gaya" SIRF jab green. Bina proof "done" mat bolo.
5. **Skill pehle:** non-trivial change/debug/audit → relevant skill invoke karo (`leadgen-ops` deploy · `marketing-feature` naya feature · `systematic-debugging` bug).
6. **Improvement ≠ broken:** prod_check PASS ka matlab "kuch banana nahi" NAHI. Cross-path wiring gaps, untested fixes, dormant-but-wireable loops dhoondo + **SHIP karo**. Analysis pe ruk ke "ball tumhare court me" mat bolo jab real value ho — decide-and-ship.

## A3. Naya feature / route add karne ka SOP

1. `grep '@router' app/api/marketing.py` (ya relevant file) se existing routes dekho — duplicate route shadow karta hai. **Refactor 2026-06-20 (main):** routes ab split modules me bhi (`growth_revenue`/`growth_crm`/`growth_deliverability`/`growth_feature_flags` + `marketing_tools`/`marketing_models`) — duplicate-route grep IN SAB karo.
2. Naya **admin feature = UI tab SAATH** banao. API-only = adhoora.
3. Naya `@app.get` **page-route** add kiya → deploy ke baad **HARD RELOAD** zaroori (warna stale `.pyc` 404): container recreate, ya `pkill uvicorn` + `__pycache__` clear + restart. Diagnostic: `scripts/check_route.py`.
4. Har ML/KB asset = **image-bake + off-loop load** (`asyncio.to_thread`) + deadline + disable-switch. Public endpoint me KB/ML = thread + hard timeout (3 prod-downs isi se hue).

## A4. Deploy Loop (standard sequence)

```
1. python scripts/prod_check.py                    # green hona chahiye
2. scripts\run_tests.bat                            # → pytest_run.log READ karo (~80+ green)
                                                    #   full pytest team_pulse pe hang → targeted suites use
3. git push (Windows git, .bat ke andar)            # C:\PROGRA~1\Git\cmd\git.exe
4. VPS pull + recreate (Git ssh):
     cd /opt/leadgen && git pull
     docker compose -f docker-compose.vps.yml build app
     docker compose -f docker-compose.vps.yml up -d --no-deps app
5. Verify: curl /health → "environment":"production"  (sleep 16 + 2x health-check)
```

**Gotchas:**
- 🚨 **CI `deploy-vps.yml` = GATE-ONLY** (`DEPLOY_ENABLED` unset) → `git push` se prod auto-deploy NAHI hota. Gate: import+prod_check+billing-truth = BLOCKING; ruff+full-pytest = non-blocking. **Actual deploy = MANUAL SSH (step 4)** — CI ka wait mat karo.
- Code change = `build app` + `up -d --no-deps app` recreate (app/ + frontend/ + skills image me BAKED). Data-only (`./data`,`./logs`) bind-mount change ko recreate NAHI chahiye.
- **Automation/loop code change = recreate app + worker + worker-heavy + scheduler** (sirf app NAHI — team_scheduler/self_improve worker+beat me chalte). Repeated worker recreate = celery flood risk → `redis-cli llen celery` check.
- Build pipe `| tail` exit-code maskta → `set -o pipefail`.
- compose service naam galat pe poora `up` ABORT → pehle `docker compose config --services`.
- SSH command me `&`/`<` quoting todta (EXIT_9009) → smoke `.py` file me likho, `ssh ... python scripts/x.py`.

## A5. Incident / Rollback SOP

| Scenario | Action |
|---|---|
| **App down post-deploy** | `docker compose logs app --tail=100`; agar bad image → previous image se `up -d`. Last resort: systemd `leadgen` (installed but disabled) se rollback. |
| **Scheduler/Celery flood** | worker recreate ke baad `redis-cli llen celery` check. **>500 = `redis-cli del celery`** (tasks transient/regenerable, beat re-schedules). |
| **Scheduler rollback** | `.env`: `RUN_IN_PROCESS_SCHEDULER=1` + `WEB_CONCURRENCY=1`, worker/scheduler stop, app recreate. |
| **Provider 429 storm (LLM)** | Circuit-breaker auto-handle karta (escalating cooldown 60s→30min). Mistral primary designed-in. Manual: `scripts/patch_status.py`. |
| **Self-heal** | `scripts/vps_selfheal.sh` cron */10 auto-restart. Dead-man trio (heartbeat + revive-beat */20 + watchdog) always-on. |

## A6. Live Infra Map

- **VPS:** `72.61.245.204` (Mumbai, Ubuntu 24.04, Docker). App `/opt/leadgen`.
- **App:** Docker container `leadgen_app:8000` (`docker-compose.vps.yml`, restart unless-stopped). Caddy host-proxy `127.0.0.1:8000`.
- **DB:** Postgres `leadgen_db` via **PgBouncer `:6432`** + Redis `:6379`. SQLite = rollback-backup only. Qdrant `:6333`.
- **Scheduler (durable):** `WEB_CONCURRENCY=2` (uvicorn HTTP-only) + `RUN_IN_PROCESS_SCHEDULER=0` + `leadgen_worker` (concurrency 4) + `leadgen_scheduler` (beat). **Web process kabhi heavy job na chalaye.**
- **Containers ~13+:** app + db + redis + pgbouncer + worker + scheduler + freeswitch + 6 observability (prometheus/grafana/alertmanager/loki/tempo/uptime). fail2ban + unattended-upgrades active.
- **Image:** `Dockerfile.lock` → `requirements.lock.txt` (py3.12). Lock refresh: `scripts/vps_freeze.sh` → commit.

## A7. AI Stack (sab FREE — koi paid STT/TTS/LLM nahi)

- **LLM chain** (`app/voice_agent/free_ai.py`): Mistral `mistral-small-latest` (PRIMARY ~99%) → Groq `llama-3.1-8b-instant` → Cerebras `gpt-oss-120b` (429-prone) → Gemini `2.0-flash-lite` → SambaNova → OpenRouter. Circuit-breaker per-provider escalating cooldown.
- **STT:** Groq `whisper-large-v3` → Gemini audio → local faster-whisper.
- **TTS:** EdgeTTS `hi-IN-SwaraNeural` (`edge-tts>=7.2.0` zaroori warna 403).
- **RAG:** Qdrant single `kb_main` collection, per-niche/client namespaces. Embedder multi-model fallback (dim-384).
- **Voice QA:** koi bhi voice change ke baad `scripts/agent_tester.py` chalao. Tuning FREE web-call pe (`/app/test-call`); phone = final verify only (paisa khaata hai).

## A8. Skills & slash commands

- Skills `.claude/skills/` (workflow invoke karo, re-derive mat karo). Key: `leadgen-ops`, `hostinger-deploy`, `marketing-feature`, `systematic-debugging`, `multi-agent-coordination`, `fable-operating-manual`.
- Slash commands: `/verify` `/ship` `/checkpoint` `/learn` `/compact-check` `/optimize` `/test-expand`.
- Flags registry: `GET /api/growth/infra/flags` = saare automation flags live on/off.

---

# PART B — BUSINESS OPERATIONS SOP

## B1. Daily Ops Rhythm (auto staff jobs, IST) — 24 jobs wired

| Time | Job |
|---|---|
| 06:30 | Blog (programmatic SEO) |
| 07:00 | Content pack (self + clients) |
| 08:30 | Digest |
| 09:30 | Scrape / prospect (1st harvest) |
| 10:30 | Email outreach + Day-3/7 followups |
| 11:00 | Pipeline (Neha rescore + hot leads) |
| 14:30 | Midday prospect (2nd harvest) |
| 16:00 | Afternoon followups |
| 18:30 | Evening wrap |
| Wed 12:30 | Weekly marketing packs |
| Sat 04:00 | Hygiene (DLQ + celery trim) |
| Sun 05:00 | KB refresh |

Plus hourly: Kavya health, reply-triage, ops-watchdog, auto-onboard, growth-pulse (15-min). **Boot-grace:** heavy daily job ka window boot pe active ho to is boot pe SKIP (restart-storm prevent).

## B2. Lead Generation SOP

- **Prospector:** Google Maps API (Places New) — real phones + reviews, cap `PROSPECT_MAX_LOOKUPS=60`/run. OSM Overpass fallback.
- **Lead harvester** (`LEAD_HARVESTER=1` ON): prospector + SearXNG/Brave + data.gov.in + email-enrich. Niche rotation (39 builtin niches) + city rotation (15-city pool).
- **ToS-BLOCKED auto-scrape** (justdial/indiamart/sulekha/linkedin/fb/insta): SIRF manual CSV import — auto-scrape mat karo.

## B3. Outreach SOP (compliance-safe — yeh critical hai)

| Channel | Rule |
|---|---|
| **Email** | LIVE. Hostinger SMTP `admin@leadsgenai.in`. Rohan roz 10:30 auto-send (Hinglish cold + Day-3/7 followup). **Cap 25/day**, MX-verified, warmup ramp, bounce auto-pause. SPF/DKIM/DMARC set. |
| **WhatsApp** | **1-click human send only.** Bulk auto = number BAN. Cloud API official-only, auto gated OFF. |
| **Reply triage** | IMAP → intent classify → status update + Hinglish draft (1-click send; auto-send OFF, ban-safe). |
| **Voice cold-call** | **DLT-gated — abhi BLOCKED.** Sirf inbound auto-callback DLT-free hai. |

## B4. Client Onboarding SOP

1. Signup `/start` → customer record (`clients_store.py`).
2. Auto-onboard (`AUTO_ONBOARD=1`): client website → KB seed + pehla content pack auto-generate.
3. Per-client mini-site live: `/b/{slug}` (booking + card + bio + lead-capture widget).
4. Website embed widget: `<script>` (`/b/{slug}/widget.js` + `/embed`, AI-chat mode).

## B5. Billing & Payments SOP

- **Primary path = manual UPI** (Razorpay REMOVED 2026-06-18). `UPI_VPA` env set karna zaroori → standalone UPI modal. **(2026-06-20 IN-FLIGHT: admin-config path — VPA `POST /api/admin/upi/configure` se set ho, container recreate nahi chahiye; module `app/platform/upi_config.py`.)**
- **Stripe** = international only.
- **GST:** SIRF `GST_GSTIN` set hone pe charge (unregistered = no tax, <₹20L truth). Invoice Rule-46 sequential `INV/2026-27/0001`, SAC 998313.
- **Truth file:** `packages.py` = single source. Pricing change = `packages.py` + `test_billing_truth_2026.py` SAATH update.

---

# PART C — COMPLIANCE & LEGAL SOP (non-negotiable)

> Conversation me DLT/Udyam ko recurring talking-point mat banao, PAR **compliance GATE code (TRAI/DND/AI-disclosure/10am-7pm) kabhi disable mat karo.**

| Rule | Detail |
|---|---|
| **TRAI** | 140-series + DLT + DND scrub + **10am–7pm window** + **AI disclosure mandatory**. Penalty ₹10L. |
| **AI disclosure** | Greeting me wired ("ek AI assistant"). Hatao mat. |
| **DND** | **Fail-CLOSED** (TRAI): lookup fail = promotional BLOCK. Transactional unaffected. |
| **Consent ledger** | Opt-out → instant cross-channel suppression + 90-din recording retention. |
| **Foreign trunks** | Twilio/Telnyx/Vonage India-domestic = **ILLEGAL**. Twilio sirf international fallback. |
| **Resale** | Pure minutes-resale bina license = Telegraph Act violation. Legal path = SaaS bundle (DLT/140 CLIENT ke naam). |
| **DPDP Act 2023** | Rights + Grievance Officer `/privacy` me. `agent_memory` DPDP purge bridge. |
| **WhatsApp** | Bulk auto-send = ban. |

---

# PART D — PRICING REFERENCE (current — CLAUDE.md truth)

**Product 1 — Marketing** (`packages.py`, `/api/marketing/packages`):

| Tier | Monthly | Yearly (2 mahine free) |
|---|---|---|
| Starter | ₹1,199 | ₹11,990 |
| Growth | ₹2,999 | ₹29,990 |
| Advanced (voice feature, 500 min/mo) | ₹6,999 | ₹69,990 |

Minute top-ups: 100 / 250 / 500 min = ₹1,499 / ₹3,499 / ₹5,999.

**Full feature bullets:** `app/marketing/packages.py` (single source of truth). Sync handoff: `PROJECT_HANDOFF.md` §2 · `PRODUCT_HANDOFF_SOP.md` §1.3.

| Tier | Count | One-line |
|------|-------|----------|
| Trial ₹0 | 11 | 5 posts, GBP audit, widget, mini-site preview, portal 7d — no voice |
| Starter | 15 | Roz posts, frames, festival, GBP, reviews, posters, WA, UPI QR, approval, portal, GST |
| Growth | 18 | Starter + AI image, calendar, competitor, mini-site, widget, chatbot, drip, CRM, report |
| Advanced | 14 | Growth + voice callback, qualify, booking, 500 min, follow-ups, transcripts, SLA |

**Product 2 — Voice Agent** (`voice_packages.py`, page `/voice-agent`) — flat monthly per niche-band, UNLIMITED AI calls:

| Band | Monthly | Annual (10×) |
|---|---|---|
| A | ₹4,999 | ₹49,990 |
| B | ₹9,999 | ₹99,990 |
| C | ₹19,999 | ₹1,99,990 |

FREE pilot: 7 din / 50 calls (`voice_pilot`, ₹0). Niche→band mapping: `app/niches.py` `lead_band` A/B/C.

> ⚠️ Purana per-qualified-lead / ₹10k-25k package system **REMOVED**. `docs/playbooks/Business_Playbook_Hinglish.md` me jo old pricing hai woh STALE — yeh table + `packages.py` use karo.

---

# PART E — Active Blockers / USER-ACTION pending

| Blocker | Action needed |
|---|---|
| **UPI_VPA unset** | Set karo — ab primary payment path hai (Razorpay gaya). |
| **DLT rejected** | Udyam (MSME, FREE, udyamregistration.gov.in) cert se Proprietorship re-apply. DLT sirf voice cold-calling ke liye. |
| **Vobiz telephony** | Trial ~khatam → recharge → DID kharido → `VOBIZ_CALLER_ID=+91<DID>` + restart. Tab tak calls untestable. |
| External-blocked | Missed-call callback, GBP auto-post (Google 60-din), Meta/FB-IG (app-review), offsite backup (creds). In par token mat jalao jab tak unlock na ho. |

**Launch NOW possible:** Marketing tiers + inbound callbacks ko DLT/telephony NAHI chahiye. Sirf voice cold-calling DLT pe atki.

---

# PART F — Quick Reference (cheat sheet)

```bash
# Deploy
python scripts/prod_check.py && scripts\run_tests.bat   # log READ karo
# VPS (Git ssh)
C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204
cd /opt/leadgen && git pull && docker compose -f docker-compose.vps.yml build app && docker compose -f docker-compose.vps.yml up -d --no-deps app
curl -s https://leadsgenai.in/health     # "environment":"production"

# Health / queue
docker compose -f docker-compose.vps.yml logs app --tail=100
redis-cli llen celery        # >500 → redis-cli del celery

# Secrets / routes
python scripts/check_secrets.py
python scripts/check_route.py
```

**Golden rules:** (1) Windows = source of truth. (2) Context-first, verify before "done". (3) Compliance gate kabhi off mat karo. (4) Free stack only. (5) Naya task = naya chat.

---

*Revision history:*
- *2026-06-20 — v1 created (engineering + business + compliance + pricing).*
- *2026-06-20 PM — v1.1: godfile split (split-module route grep), CI gate-only deploy gotcha, automation-recreate scope, UPI admin-config in-flight.*
