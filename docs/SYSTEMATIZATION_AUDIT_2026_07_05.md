# SYSTEMATIZATION AUDIT — 2026-07-05

> **Kya hai ye doc:** Poore repo ka consolidated "sab mess hai" audit — 3 parallel read-only sweeps
> (backend structure / feature completeness / docs-tests-ops hygiene) ka merged single source.
> **Fix tracker = `docs/GAP_REGISTER_2026_07_05.md`** (living doc — status wahan update hota hai, yahan nahi).
> Ye audit report point-in-time snapshot hai; findings yahan freeze hain.
> Supersedes (by reference — koi doc delete nahi hua): 7 purane production-readiness docs
> (`PRODUCTION_READINESS_2026.md`, `PRODUCTION_READINESS_AUDIT_2026_06_21.md`, `..._06_24.md`,
> `Production_Readiness_Analysis_2026-06-24.md`, root `PRODUCTION_AUDIT_REPORT.md`,
> `PRODUCTION_CHECKLIST.md`, `PRODUCTION_CUTOVER.md`) ka "current gaps" hissa.

## TL;DR

Codebase **breadth-heavy + flag-dark** hai. Verdict teen line me:

1. **Features zyada tar BANE hue hain** — 680 frontend fetches me se broken UI→API reference **zero** mila. Dominant pattern = built-and-wired-but-flag-OFF (owner-gated by design, gap NAHI).
2. **Organization inconsistent hai** — config 3 idioms me bikhra, router registration 3 idioms me, docs ke 3 competing indexes, CI ke 4 overlapping workflows, `scripts/` 278-file junk drawer.
3. **Genuinely missing/adhoora**: 6 registry-invisible flags, 6 API-routers-bina-UI, customer-webhook billing emits documented-par-unwired, 4 real stubs, 5 untested dormant engines, `.env.example` me 305 undocumented keys.

## Method

3 parallel read-only audits (2026-07-05): (A) backend structural disorganization, (B) half-built/missing
features, (C) docs/tests/ops/config hygiene. Sab findings file:line evidence ke saath. Koi code change nahi hua audit me.

---

## A. Backend structure (mess hai, par mostly LATENT risk — koi live breakage nahi mila)

**Scale:** 593 Python files, ~195k lines, ~1030 routes.

### A1. Godfiles (top offenders)

| Lines | File | Note |
|---|---|---|
| 3023 | `app/telephony/vobiz_stream.py` | refactor DEFERRED (voice-unsafe, ADR) |
| 2811 | `app/voice_agent/telecaller_brain.py` | refactor DEFERRED (voice-unsafe) |
| 2025 | `app/main.py` | 79 `include_router` + **78 inline `@app.get` frontend HTML routes** (~600 lines jo pages-router me belong karti hain) |
| 2000 | `app/api/customer_marketing_studio.py` | routes + logic co-located |
| 1992 | `app/platform/office_hq.py` | (iska thin router `app/api/office_hq.py` me hai — yehi INTENDED pattern hai jo baaki jagah apply nahi hua) |
| 1876 | `app/api/web_call.py` | routes + heavy inline logic |
| 1547 | `app/agents/self_improve.py` | |
| 1441 | `app/api/growth.py` | + 9 growth_* sub-routers ka aggregator |
| 1319 | `app/api/billing.py` | billing concern 4 jagah split: `app/billing/`, `api/billing.py`, `api/billing_models.py`, `api/upi_payments.py` |

Plus ~15 files 900–1200 lines (`admin.py` 1047, `admin_ops.py` 1004, `auto_outreach.py` 1126, `team_scheduler.py` 1122, …).

### A2. Config chaos (sabse bada inconsistency)

- **672 raw `os.getenv`/`os.environ` reads across 232 files** vs `app/config.py` pydantic Settings (**121 fields**, sirf 105 files import karti hain).
- **64 files DONO idiom same file me mix karti hain** (e.g. `app/api/admin.py`, `app/api/customer_auth.py`, `app/agents/self_improve.py`).
- Worst raw-env consumers: `vobiz_stream.py` (26 reads), `web_call.py` (20), `admin_ops.py` (19).
- ⚠️ Migration Phase-4 deferred hai kyunki semantics alag hain: `os.getenv` = live-at-call-time (VPS flag-flip bina redeploy kaam karta hai), `settings` = boot-frozen. Blind migration prod workflow todegi.

### A3. Route registration — 3 idioms, latent duplicate-route risk

- Idiom 1: direct `app.include_router()` in `main.py` (79 calls, kai flag-gated `if` blocks me).
- Idiom 2: nested aggregator — `growth.py` khud 9 `growth_*` sub-routers mount karta hai (`growth.py:550,785,791,1050,1092`…).
- Idiom 3: multi-router-per-file — `conversion.py:49-50` me 2 routers.
- **Shared-prefix collision surface**: `/api/admin` prefix **3 files** declare karti hain (`admin_dashboard.py:39`, `admin_ops.py:30`, `system_health.py:18`); `/api/customer` 3 files; `/public` 2 files. Aaj disjoint hain (koi LIVE shadow nahi), par first-route-wins landmine documented hai aur **flag-OFF mounts CI ke runtime dup-check (`prod_check.py:127-136`) ko invisible hain** → static guard chahiye (GAP R-02, Phase 1 me fix).
- `/me` 3× aur `/dashboard` 4× defined hain (alag prefixes se safe — prefix change hote hi collision).

### A4. Debt markers ~zero

Poore repo me 1 TODO, 0 FIXME/HACK/XXX — **mess silent hai, grep-able nahi.** Isliye ye audit + gap register hi triage surface hai.

---

## B. Feature completeness ("missing bahot kuch" ka asli shape)

### B1. Registry-invisible flags (code me hain, `app/api/automation_flags.py` me NAHI → flags UI me invisible/untoggleable)

| Flag | Read location | Default |
|---|---|---|
| `LLM_COUNCIL` | `app/agents/llm_council.py:37` | ON |
| `CUSTOMER_OFFICE` | `app/api/customer_dashboard.py:128` | ON |
| `ADMIN_OFFICE` | `app/api/admin_ops.py:616` | ON |
| `SESSION_MEMORY` | `app/voice_agent/agent_memory.py:588` | OFF |
| `DLT_APPROVED` | `app/platform/setup_status.py:106` + `app/telephony/compliance.py:208` | OFF |
| `PROMETHEUS_HTTP_METRICS` | `app/middleware/http_metrics.py:46` + `app/main.py:375` | — |

Yehi bug pehle bhi tha — `OBSIDIAN_SYNC`/`COMBO_PRODUCT` 2026-07-04 audit tak registry-invisible the. (Fix = GAP R-01, Phase 1.)

### B2. API-without-UI routers (project rule: API-only = adhoora)

| Router | Endpoints | Gap detail |
|---|---|---|
| `app/api/leads.py` | CRUD + `/scrape` + stats | koi frontend reference nahi; shayad `/api/growth/*` + `/api/customer/leads` se superseded — decide: UI ya deprecation note |
| `app/api/campaigns.py` | CRUD + start/pause/stats | koi frontend ref nahi; admin campaign-control `/api/admin/campaign/*` (admin_ops) se hota hai |
| `app/api/niche_db.py` | 11 endpoints | **double gap: no UI + no tests** |
| `app/api/widgets.py` | 13 endpoints (popup pack, wheel coupons, bio-link, beacon) | embed scripts customer-sites ke liye hain, par admin/customer CONFIG tab hi nahi |
| `app/api/conversion.py:425,442` | admin widget-form builder GET/POST | public widget-chat USED hai; admin builder ka UI nahi |
| `app/api/booking.py` | slots/book/cancel | sirf mini-site server-HTML use karta hai; admin tab nahi (calendar page `/api/growth/bookings` use karta hai) |

### B3. Documented-not-wired

- Customer webhooks `payment.received` / `subscription.*` emits — backlog me documented, code me emit calls NAHI (blocked on billing-webhook stabilization). `CUSTOMER_WEBHOOKS` flag + UI ready hai.

### B4. Real stubs

| Stub | Location | Disposition |
|---|---|---|
| LinkedIn scraper placeholder | `app/lead_scraper/linkedin.py:82-83,199` | **ToS-REFUSED invariant — tombstone karo, KABHI implement nahi** |
| Plivo carrier path | `app/telephony/carrier_router.py:149-179` | explicit tombstone docstring (Vobiz primary hai) |
| SIP ARI originate | `app/telephony/sip_handler.py:339` | explicit tombstone docstring |
| Duplicate `ZohoCRMIntegration` | `app/integrations/zoho_crm.py` vs `hubspot.py` | canonical pick + re-export shim |

### B5. Untested dormant engines (no dedicated test file)

`app/platform/gtm_targeting.py` · `app/platform/udyam_pipeline.py` · `app/platform/gap_analyzer.py` · `app/platform/icp_generator.py` (endpoint automation.html me LIVE hai!) · `app/api/niche_db.py`.

### B6. NOT gaps (deliberately so — inhe "missing" mat bolo)

- Dozens of engines flag-OFF by design (agent-extension suite, engineer agents, social engine, flow builder, control center, MCP-product, RL flywheel, CRM sync, growth revenue engines, customer autopilot…) — **owner-gated, flip = sirf user go-ahead** (`automation-flags` skill SOP).
- `platform_dial` HARD OFF = user-mandate (ADR-019).
- Voice godfile refactor deferred = voice-unsafe ADR.
- jsonl→Postgres = migrate-when-volume policy.
- Broken UI→API fetches: **zero mile** (680 fetches sab resolve hote hain).

---

## C. Hygiene (sabse concrete rot)

### C1. `.env.example` drift
235 keys vs **431 distinct getenv keys in code** → **305 undocumented** (incl. security-relevant `ADMIN_API_KEY`, `ADMIN_TOTP_SECRET`) + **~45 dead keys** incl. removed-stack (`DEEPGRAM_API_KEY`, `ELEVENLABS_*`, `AZURE_SPEECH_*`, commented Razorpay/Exotel/Plivo). Surgical fix = Phase 1 (R-03); full reconciliation = Phase 2 autogen `docs/ENV_REFERENCE.md` (R-10).

### C2. `scripts/` junk drawer — 278 files
64 `vps_*` one-offs · 53 `.bat` (Linux VPS pe useless) · 9 `_`-prefix temp files · `ci_repro{1,2,3}.bat` · `push_exotel_ws.bat` (removed-stack) · 7 throwaway git-push wrappers. Asli ops scripts (backups, `pg_restore_drill.sh`, `queue_depth_alert.py`) noise me dabi hain. **Fix = Phase 2 categorized attic list, execute sirf owner-approval pe** (R-13). ⚠️ prod_check-imported scripts (`deep_wiring_audit`, `automation_wiring_audit`, `cross_path_audit`, `explorer_sync`, `sync_api_docs`) + `run_tests.bat` KABHI attic nahi.

### C3. `docs/` — ~100 files, 3 competing indexes
- Indexes: `HANDOFF.md` (operator entry — CLAUDE.md-blessed master) vs `ENTERPRISE_DOC_INDEX.md` (~25 docs) vs `RESEARCH_DOCS_INDEX.md` — route count pe bhi disagree (1030 vs 761).
- **38 docs removed-stack reference karti hain**; active-ops offenders jo mislead karengi: `PRD.md`, `API.md` (75KB hand-maintained — OpenAPI truth hote hue), `PROJECT_SOP.md`, `PROJECT_HANDOFF.md` (77KB, HANDOFF.md se overlap), `OPERATIONAL_RUNBOOKS.md`, `runbooks/RUNBOOK_BILLING_INCIDENT.md`, `workflows/BILLING_PIPELINE.md`, `AGENT_SYSTEM_PROMPTS.md`.
- Duplicate families: 5+ handoff docs, 7 production-readiness docs, 2 runbook systems (`docs/runbooks/` vs `OPERATIONAL_RUNBOOKS.md`), ADR naming 3 conventions me.
- `SESSION_LOG.md` = 407KB unbounded append.
- ⚠️ `SESSION_ACTIVATION_RUNBOOK_2026_06_16.md` KABHI move nahi (`scripts/runbook_drift.py:24` hardcode).

### C4. CI — 4 overlapping workflows (partially already fixed)
- `ci.yml` = REAL gate (compileall, check_secrets, security_scan, queue_idempotency_audit, mypy blocking; prod_check + full pytest `-m "not network"` blocking). `ruff || true` = non-gating.
- `deploy.yml` (GCP), `test.yml`, `ci-cd.yml` — **already `workflow_dispatch`-only disabled** (sirf deletion optional).
- `tests.yml` — abhi bhi push/PR pe fire hota hai (10-file narrow gate) = asli bacha hua overlap. Demote se pehle **branch-protection required-checks verify karo** (R-11).
- `deploy-vps.yml` — pytest `continue-on-error` (deploy test-gated NAHI; comment khud kehta hai "flip when green") (R-12).
- `ci.yml` me `paths-ignore: docs/**, **/*.md` → docs-only commits CI trigger nahi karte.

### C5. Root-dir clutter
- **`prospect_leads_export.csv` — 238KB LEAD PII git-tracked** (R-06, USER-CONFIRM: `git rm` vs history purge).
- 2 business `.xlsx` (owner assets — sirf owner decide kare), `debug_signup.py`, `test_phase7_inline.py` (pytest tree ke bahar), 4 stale report `.md` (`FIX_PLAN.md`, `PRODUCTION_AUDIT_REPORT.md`, `TEST_RESULTS.md`, `TASKS.md`), business content docs.
- 11 `docker-compose*.yml`, 6 `requirements*` variants (lock = truth), 3 Dockerfiles.

### C6. Tests
296 files / 2727 test functions — par **7 misplaced** (6 `scripts/` me — jinme se 3 live-API key-probes hain, 1 root pe). `testpaths=["tests"]` ki wajah se ye collect NAHI hote; move = CI blocking suite me add karna = per-file decision (R-14). `test_team_pulse.py` hang confirmed (deploy-vps.yml:36 comment) — **full local pytest kabhi mat chalao, targeted hi**.

### C7. `data/` jsonl sprawl — 164 runtime stores
Incl. PII/auth: `consent_ledger.jsonl`, `customer_auth.jsonl`, `customer_totp.jsonl`, `dpdp_*.jsonl`, `client_api_keys.jsonl`. Gitignored + offsite-backed (rclone LIVE, restore proven), par no schema/registry/indexing. Policy = migrate-when-volume; **abhi ka fix sirf inventory/registry doc** (Phase 2, R-16-adjacent), migration Phase 4 (R-31).

---

## Roadmap (4 phases — tracker = GAP_REGISTER)

- **Phase 1 (2026-07-05 execution):** zero-behaviour-change hygiene — R-01 flags, R-02 static route guard, R-03 env.example surgical, R-04 docs index, R-05 root archive.
- **Phase 2 (next approval):** env reference autogen, CI consolidation, scripts attic list, misplaced tests, docs quarantine, data-store inventory.
- **Phase 3 (per-item approval):** UI-or-deprecate 6 routers, webhook emits, stub tombstones, dormant-engine tests.
- **Phase 4 (explicit opt-in only):** main.py pages extraction, getenv→settings, godfile splits, jsonl→PG.

*Audit run: 2026-07-05 · read-only · evidence file:line ke saath. Status updates SIRF gap register me.*
