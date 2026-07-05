---
name: fable-operating-manual
description: Is project ka proven operating playbook — kaise audit karo, root-cause pakdo, kaha verify karo (Windows = truth vs sandbox = stale), change ko risk-tier karo, loops complete karo, test karo, evidence ke saath commit/deploy karo. Use when koi bhi non-trivial change/debug/audit/automation karna ho, "ye theek se wired hai?" check karna ho, ya jab "best kya hai project ke liye" decide karna ho. Agents iss manual ko default operating-discipline ki tarah follow karein.
---

# Fable Operating Manual (project ke liye)

Yeh is project pe kaam karne ka distilled, enterprise-grade tareeka hai — jisse changes safe, root-caused, risk-tiered, aur evidence-backed rehte hain. Naya kaam shuru karne se pehle relevant section padho.

## 0. Golden rules (sabse upar)
1. **Audit pehle, edit baad me.** Koi cheez "incomplete/broken" lagti hai to pehle MEASURE karo (scan/grep/test), assume mat karo. Ek working system ko bina evidence ke mat chhedo.
2. **Root cause, not symptom.** Symptom fix karne se pehle "kyun" 1 baar zaroor pakdo. Galat fix asli bug chhupa deta hai (e.g., niche count test ko 39 karne se pehle git dekha ki 42→39 intentional tha — regression nahi).
3. **Never-raise + gated + inert-without-creds.** Har naya loop/integration: try/except (kabhi crash na kare), env-flag se gated (default OFF = zero behaviour change), creds/flag bina inert.
4. **Additive > destructive.** Purane working code ko replace karne se pehle confirm. Naya feature add karna safe hai; rewrite risky.
5. **Done = evidence.** "Ho gaya" sirf jab proof ho (§0.5 phase 5). Bina artifact done KABHI mat bolo.

## 0.5 The operating loop — Discover → Contract → Execute → Self-review → Evidence
Har non-trivial task isi 5-phase loop se chalao (CLAUDE.md gate #7 ka enforce-able roop). Cursor accha isliye karta hai ki woh pura codebase index karke relevant files khud uthata hai — yahi **manually** har phase me karo.

1. **Discover (context-first — edit se PEHLE):** `Grep`/`Glob` se feature/function ke SAARE touch-points dhoondo — definition, callers, routes (`@router`/`@app`), templates/JS, related tests. Ek bhi miss = regression. Jo files chhooni hain unhe PURA padho (imports, padosi fns, error handling, naming convention). Aadha-padha context = galat edit ka #1 reason. "Ye toota hai" assume mat karo — git log / CLAUDE.md / test se intent confirm karo (42→39 niche = intentional, regression nahi).
2. **Contract:** edit se pehle likho — kaun si files + kya change + kaun se test/evidence cover karenge + rollback kya hai. Change-risk tier (§0.6) decide karke uske gates lock karo. Bada/multi-file → `plan-then-build`.
3. **Execute:** Windows-side edit, har Edit se theek pehle file Read (stale-mount safety). Same file pe parallel multi-edit mat do (truncation hazard). Additive > rewrite. Naya loop/integration = never-raise + flag-gated + inert-without-creds.
4. **Self-review:** ship se pehle apna diff `self-code-review` lens se padho (bug / security / signature-drift / hot-path / test-gap). High-risk change (§0.6) → `security-review` bhi.
5. **Evidence (done ki definition):** `/verify` (prod_check + targeted tests + import) green + jo claim kiya uska artifact (test log / `/health`=production / cross_path_audit / metric/heartbeat). Bina evidence done KABHI mat bolo; warna `systematic-debugging`. Frontend/page change ka evidence = live-browser verification bhi: `cd frontend && python -m http.server 8123` se statically serve karke claude-in-chrome se drive karo (API-less preview path me bhi map/UI boot verify hota hai — 2026-07-05 office-upgrade pattern).

## 0.6 Change-risk tiering (pehle classify, phir gates lock)
Blast-radius se tier decide karo — over-process bhi waste hai, under-process bhi prod-down.

| Tier | Kya | Extra gates (Discover→Evidence ke upar) |
|------|-----|------|
| **Trivial** | docs/copy/comment, single non-hot-path fn | Read-before-Edit + 1 targeted test |
| **Standard** | naya endpoint/feature, non-billing logic, UI tab | `duplicate-route-guard` grep + flag-gate + changed-file tests + prod_check |
| **High-risk** | billing/pricing · public route · telephony/outbound · secrets/auth · automation loop · DB migration | per-domain gate (neeche) + §9 ka pura bar + named rollback + self+security review |

**High-risk per-domain gate:**
- **Billing/pricing** → `packages.py`/`voice_packages.py` = single source-of-truth; `test_billing_truth_2026` SAATH green.
- **Public route** → SSRF/auth/rate-limit check; deploy pe **hard-reload** (container recreate, warna stale .pyc 404).
- **Telephony/outbound** → TRAI/DND fail-CLOSED · 9am–7pm window · AI-disclosure-at-start · consent-ledger; bypass KABHI nahi.
- **Secrets** → sirf `.env` (gitignored); `scripts/check_secrets.py` (/verify step). Committed file/CLAUDE.md/script me KABHI nahi.
- **Automation loop** → idempotency + DLQ + retry + `automation_health` parity + flag-gated default-OFF (§9).
- **DB migration** → forward + rollback dono; data-repair path likha ho.

## 1. Kaha verify karo — Windows = truth, sandbox = STALE
**Sabse important gotcha.** Sandbox/Linux mount file-tool edits ke baad STALE ho jaata hai — wo TRUNCATED/purani file content serve karta hai. Isse jhoothe "syntax error / unterminated string / incomplete function" dikhte hain jabki Windows pe file bilkul sahi hai.
- **File content padhne/verify ka source-of-truth = Windows** (Read tool, Desktop Commander, Windows `git`/`python`).
- Sandbox bash sirf cheap exploration ke liye; koi bhi "ye file toot gayi" conclusion Windows pe confirm kiye bina mat do.
- App import/run/test KABHI sandbox python se mat karo (version + stale mount) — `.venv\Scripts\python.exe` Windows pe chalao.
- AST/scan scripts bhi Windows venv se chalao (warna 30 false-positive "syntax errors" milenge — saare stale-mount artifacts).

## 2. Loops / backend completeness audit (kaise check karo "sab wired hai")
- **Orphan loops**: har `run_*/run_due/run_if_enabled/*_sweep/pulse/optimize/tick` function ka koi call-site hona chahiye. AST/grep se defs vs call-sites compare karo — 0 orphans = wired.
- **Scheduler ↔ Celery parity**: `team_scheduler._run_job` ke jobs aur `worker.py` beat_schedule mirror hone chahiye. `automation_health.EXPECTED_GAP_MIN` me har job registered ho (dead-man switch).
- **Scheduler reality**: LIVE = **Celery durable** (`leadgen_worker` + `leadgen_scheduler` beat containers, `RUN_IN_PROCESS_SCHEDULER=0`). In-process APScheduler (`team_scheduler`, `main.py` lifespan `start_scheduler()`, gated `RUN_IN_PROCESS_SCHEDULER=1`) = **rollback path**, default nahi. DLQ → Redis `dlq:failed_tasks`.
- **Truncation guard**: AST se aise functions dhoondo jinka body sirf docstring ho ya last statement ek bare `Name`/`Attribute` ho (jaise `refresh_custom_nic` — `lead_band()` truncation bug). Ye "file truncate" hazard (bade multi-edit me file kat-ti hai) ka signature hai.

## 3. Naya loop / engine add karne ka pattern
1. Engine module me `async def run_due()/run_check()` likho — gated env-flag, daily/period dedupe (state file, success pe hi mark → fail pe next-tick retry), never-raise.
2. `team_scheduler._run_job` ke sahi job (content/digest/watchdog/prospect) me try/except ke saath wire karo.
3. Agar durable chahiye to `worker.py` beat me bhi mirror karo + `automation_health` gap registry me daalo.
4. Flag ko `AUTOMATION_FLAGS` registry (growth.py) me add karo taaki `/api/growth/infra/flags` pe dikhe.
5. **Admin feature = UI tab saath hi** (`/app/automation` me) — API-only = adhoora.

## 4. Testing — TARGETED suites, full suite offline-hangs
- **Full `pytest` offline-clean NAHI hai**: kai tests (test_agent_stack, test_2026_features, growth_engine self-heal) real LLM/embedder/network call karte hain → offline HANG. `socket.setdefaulttimeout` async httpx ko cover NAHI karta.
- **Isliye CHANGED files + relevant regression suites chalao**, poora suite nahi. `conftest` me `RUN_IN_PROCESS_SCHEDULER=0` + `TEAM_AUTOMATION=0` + socket timeout already set.
- Test isolation: jo test "empty → zeros" assert karta hai, usko saare data sources (jsonl + DB `get_db_session` + clients_store/seo_blog/auto_content) stub karne padte hain — warna shared test-DB ke leftover rows se fail.
- Pricing/contract changes ke baad `test_billing_truth_2026` zaroor green rakho.

## 5. Deploy loop (detail: leadgen-ops + hostinger-deploy skills)
App = **Docker container `leadgen_app`** (`docker-compose.vps.yml`); systemd `leadgen` DISABLED (rollback only). Loop: `python scripts/prod_check.py` → changed-file tests → Windows git push → VPS pull + `docker compose build app` + `up -d --no-deps app` (= **hard reload**, stale .pyc se naya `@app.get` page-route 404 deta — container recreate isko clear karta) → `/health` = `environment:production` verify (sleep 16 + 2x check). `app/`+`frontend/`+`.claude/skills/` image me BAKED (rebuild chahiye); `data/`+`logs/` bind-mount (no rebuild). CI deploy-gated (`DEPLOY_ENABLED`) — push se auto-deploy nahi hota. **Live-VPS deploy = explicit user-auth chahiye, infer mat karo.**

## 6. Commit discipline
- Ek commit = ek coherent change-set. Critical bug-fix ko bade frontend chunk ke saath bundle mat karo.
- Secrets KABHI committed file me nahi — sirf `.env` (gitignored).
- Untracked unrelated files (e.g. `vps_*.sh`) ko apne commit me mat ghaseeto — explicit `git add <files>` karo.
- Parallel-Cursor hazard: shared files commit se pehle `git status`/`diff` dekho; `git add -A` mat karo.

## 7. Pricing / niche model (current truth — galat assume mat karo)
- Niches: **39 curated builtin** (S=8, A=14, B=17). Purane real_estate/wedding_venues REMOVED (intentional rebuild). `lead_band(key)` → A/B/C.
- Voice product: **FLAT MONTHLY per band** (A ₹4,999 / B ₹9,999 / C ₹19,999; annual=10×; free pilot). `voice_packages.BANDS` + `VOICE_PLAN_IDS`. Per-lead/per-10-lead system HATA diya gaya — `VOICE_TIERS`/`PACK_SIZE=10` ab nahi. Quota flat = UNLIMITED_QUOTA.
- Marketing product (PUBLIC = 2 plans): **Main** (`starter`) ₹1,999/mo · **Combo/Advanced** (`advanced`, +500 voice min) ₹5,999/mo (annual 10× = 19,990/59,990). **Growth ₹2,999 (`growth`) = legacy HIDDEN (`public:False`) — public pricing me kabhi nahi → `get_public_packages()`.** `app/marketing/packages.py` = single source of truth; pricing change = packages.py + `test_billing_truth_2026` SAATH. (Number duplicate mat karo — source = packages.py.)

## 8. Decision-making (jab "best kya hai" poocha jaye)
- Revenue-blocking + user-action (payments/DLT/KYC) = highest priority flag karo, par wo user ke haath me hai.
- Code-level: incomplete loops complete karo, hidden bugs (truncation/wiring) fix karo, tests green rakho.
- Ambiguous product decision (niche count, pricing) = git history/CLAUDE.md se intent confirm karo; nahi to user se 1 focused sawaal. Ambiguous strategy/go-no-go → `llm-council-decision` (asking nahi).
- "Improvement ≠ broken": prod_check PASS ka matlab "kuch banana nahi" NAHI — cross-path wiring gaps, untested fixes, dormant-but-wireable loops dhoondo + SHIP karo (decide-and-ship, AskUserQuestion pe mat atko jab real wireable value ho).
- Har session ke end pe: prod_check + targeted tests + commit + user ko deploy step yaad dilao.

## 9. Enterprise gates — automation, runtime & compliance
Har automation, agent loop, scheduler job, webhook, integration, billing/outbound flow, ya production-runtime change pe yeh higher bar:

**Automation bar (10):**
1. Product outcome, owner, trigger, output, failure-behavior explicit.
2. Env flag/kill-switch; default safe + inert-without-creds.
3. Idempotency key/dedupe → duplicate email/call/bill/post/CRM-write na ho.
4. Provider/network work: timeout + bounded retry + DLQ/fail-record + never-raise wrapper.
5. Durable job → Scheduler/Celery/`automation_health` parity update.
6. Event/log/metric/heartbeat + admin/operator surface jahan useful.
7. Rollback path NAMED: flag OFF · container recreate · migration rollback · data repair.
8. Quota/cost fallback free-stack + graceful.
9. Auth/RBAC, TRAI/DND/AI-disclosure, DPDP, billing-truth, secret-safety — **fail-CLOSED** jahan required.
10. Test/smoke = happy path + 1 failure path + idempotency/dedupe.

**Fail-CLOSED non-negotiables** (bypass = legal/financial risk): TRAI calling-window 9am–7pm · DND scrub (lookup-fail = block) · AI-disclosure-at-start · DPDP consent/retention · billing GST-on-`GST_GSTIN`-only · secrets `.env`-only.

**Incident:** prod down/freeze/unhealthy → `prod-incident-triage` skill (detect → py-spy → recover → root-cause). Rollback pehle, root-cause baad me — par root-cause zaroor pakdo (symptom-only fix ban).
