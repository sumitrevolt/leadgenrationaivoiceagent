---
name: fable-operating-manual
description: Is project ka proven operating playbook — kaise audit karo, root-cause pakdo, kaha verify karo (Windows = truth vs sandbox = stale), loops complete karo, test karo, commit/deploy karo. Use when koi bhi non-trivial change/debug/audit/automation karna ho, "ye theek se wired hai?" check karna ho, ya jab "best kya hai project ke liye" decide karna ho. Agents iss manual ko default operating-discipline ki tarah follow karein.
---

# Fable Operating Manual (project ke liye)

Yeh is project pe kaam karne ka distilled tareeka hai — jisse changes safe, root-caused, aur verified rehte hain. Naya kaam shuru karne se pehle relevant section padho.

## 0. Golden rules (sabse upar)
1. **Audit pehle, edit baad me.** Koi cheez "incomplete/broken" lagti hai to pehle MEASURE karo (scan/grep/test), assume mat karo. Ek working system ko bina evidence ke mat chhedo.
2. **Root cause, not symptom.** Symptom fix karne se pehle "kyun" 1 baar zaroor pakdo. Galat fix asli bug chhupa deta hai (e.g., niche count test ko 39 karne se pehle git dekha ki 42→39 intentional tha — regression nahi).
3. **Never-raise + gated + inert-without-creds.** Har naya loop/integration: try/except (kabhi crash na kare), env-flag se gated (default OFF = zero behaviour change), creds/flag bina inert.
4. **Additive > destructive.** Purane working code ko replace karne se pehle confirm. Naya feature add karna safe hai; rewrite risky.

## 0.5 Pre-flight har code task (context-first — Cursor-grade)
Cursor accha isliye karta hai ki woh pura codebase index karke relevant files khud uthata hai. Wahi **manually** karo — edit se PEHLE:
1. **Locate (saare touch-points):** `Grep`/`Glob` se feature/function ke saare references dhoondo — definition, callers, routes (`@router`/`@app`), templates/JS, aur related tests. Ek bhi miss = regression.
2. **Read full, snippet nahi:** jo files chhooni hain unhe PURA padho — imports, padosi functions, error handling, naming convention. Aadha-padha context = galat edit ka #1 reason.
3. **Intent confirm:** "ye toota hai" assume mat karo — git log / AGENTS.md / test se dekho behaviour intentional hai ya bug (e.g. 42→39 niche = intentional, regression nahi).
4. **Touch-point plan:** edit se pehle likho — kaun si files + kya change + kaun se test cover karenge. Bada/multi-file → `plan-then-build`.
5. **Edit Windows-side, Read-before-Edit:** har Edit se theek pehle file Read (stale-mount safety). Same file pe parallel multi-edit mat do (truncation hazard).
6. **Verify before done:** `/verify` (prod_check + targeted tests + import). Green = done; warna `systematic-debugging`. Bina proof "ho gaya" mat bolo.

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
App = **Docker container `leadgen_app`** (`docker-compose.vps.yml`); systemd `leadgen` DISABLED (rollback only). Loop: `python scripts/prod_check.py` → changed-file tests → Windows git push → VPS pull + `docker compose build app` + `up -d --no-deps app` (= **hard reload**, stale .pyc se naya `@app.get` page-route 404 deta — container recreate isko clear karta) → `/health` = `environment:production` verify (sleep 16 + 2x check). `app/`+`frontend/`+`.Codex/skills/` image me BAKED (rebuild chahiye); `data/`+`logs/` bind-mount (no rebuild). CI deploy-gated (`DEPLOY_ENABLED`) — push se auto-deploy nahi hota.

## 6. Commit discipline
- Ek commit = ek coherent change-set. Critical bug-fix ko bade frontend chunk ke saath bundle mat karo.
- Secrets KABHI committed file me nahi — sirf `.env` (gitignored).
- Untracked unrelated files (e.g. `vps_*.sh`) ko apne commit me mat ghaseeto — explicit `git add <files>` karo.

## 7. Pricing / niche model (current truth — galat assume mat karo)
- Niches: **39 curated builtin** (S=8, A=14, B=17). Purane real_estate/wedding_venues REMOVED (intentional rebuild). `lead_band(key)` → A/B/C.
- Voice product: **FLAT MONTHLY per band** (A ₹4,999 / B ₹9,999 / C ₹19,999; annual=10×; free pilot). `voice_packages.BANDS` + `VOICE_PLAN_IDS`. Per-lead/per-10-lead system HATA diya gaya — `VOICE_TIERS`/`PACK_SIZE=10` ab nahi. Quota flat = UNLIMITED_QUOTA.
- Marketing product: Starter ₹1,199 / Growth ₹2,999 / Advanced ₹6,999. `packages.py` = single source of truth; pricing change = `packages.py` + `test_billing_truth_2026` SAATH.

## 8. Decision-making (jab "best kya hai" poocha jaye)
- Revenue-blocking + user-action (payments/DLT/KYC) = highest priority flag karo, par wo user ke haath me hai.
- Code-level: incomplete loops complete karo, hidden bugs (truncation/wiring) fix karo, tests green rakho.
- Ambiguous product decision (niche count, pricing) = git history/AGENTS.md se intent confirm karo; nahi to user se 1 focused sawaal.
- Har session ke end pe: prod_check + targeted tests + commit + user ko deploy step yaad dilao.
