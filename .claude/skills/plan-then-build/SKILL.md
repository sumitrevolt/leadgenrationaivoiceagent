---
name: plan-then-build
description: Multi-step build se PEHLE lean plan doc + project pre-checks (duplicate-route grep, file-ownership matrix, flags registry) — fir plan ko exactly execute karo. Use when user says "plan banao", "ye feature batch banao", "roadmap se build", "spec hai implement karo", ya 3+ file/multi-feature koi bhi kaam shuru ho raha ho.
---

# Plan-Then-Build (plan doc → pre-checks → execute exactly)

Code touch karne se pehle plan likho — zero-context engineer bhi execute kar sake. Fir plan ko EXACTLY follow karo; blocker pe STOP+ask, guess nahi.

## Step 1: Pre-checks (in-bina plan likha to prod-down/revert hoga)
1. **Duplicate-route grep (festivals lesson 🚨)**: `grep '@router' app/api/marketing.py` (+ growth.py / jo bhi router touch hoga) + CLAUDE.md scan — feature PEHLE se to nahi? FastAPI first-route-wins se duplicate ne LIVE `/festivals` shadow kar diya tha → 5 module revert+delete. Existing module ke UPAR build karo, parallel duplicate kabhi nahi.
2. **Naya env flag?** → `app/api/growth.py` me `AUTOMATION_FLAGS` registry me add karo (warna `/api/growth/infra/flags` me invisible) + default OFF + CLAUDE.md gated-flags pattern.
3. **Heavy dep / hot-path?** — scheduler me ungated heavy job nahi (qa-job prod-down lesson); public endpoint me sync ML = thread+timeout.

## Step 2: Plan doc likho (lean, `docs/plans/YYYY-MM-DD-<feature>.md` ya TASKS.md section)
Yeh plan = operating loop ka **Contract** phase, likha-hua (`fable-operating-manual`). Har plan me ye 5 cheezein MANDATORY:
- **Goal** (1 line) + approach (2-3 lines).
- **Change-risk tier** (1 line, batch ke SABSE high-risk item se tier do — fable §0.6): Trivial / Standard / **High-risk**. High-risk (billing/public-route/telephony/secrets/auth/automation-loop/DB-migration) = per-domain gate + **named rollback** (flag OFF · container recreate · Alembic downgrade · data-repair) + self+security review plan me likho. Tier decide karta hai kaunse gate aur tests har task me chahiye.
- **File map** = ownership matrix. Har file ka EK owner. **Shared files (`app/main.py`, `app/api/growth.py`, `app/api/marketing.py`, `app/api/public_site.py`, `app/platform/team_scheduler.py`, `app/worker.py`, `docker-compose.vps.yml`, `requirements*.txt`) = sirf MAIN session sequentially** — parallel agents kabhi touch nahi karte (file-truncate lesson). Parallel batch ho to har agent: apna naya `app/api/<domain>.py` + apne modules + apna `tests/test_<domain>.py`.
- **Tasks bite-sized** (har task: exact paths, test-first step, run command + expected output, commit point). Placeholder = plan failure: "TBD", "add validation", "similar to Task N" — likhna mana hai, actual code/command likho. High-risk task ka test matrix = happy + 1 failure + idempotency/dedupe (agar send/call/bill/post).
- **Wiring section alag** — mounts, page routes (HARD RELOAD note), AUTOMATION_FLAGS, scheduler hooks (best-effort try/except) — ye main session ka sequential kaam hai.

## Step 3: Self-review (plan save karne se pehle, khud hi)
1. Spec ka har requirement → kisi task se map hota hai? Gap = task add karo.
2. Placeholder scan (upar wale red-flag words).
3. Naming/signature consistency tasks ke beech (Task 3 ka fn naam Task 7 me alag = bug).

## Step 4: Execute exactly
- Task-by-task, har task ke verification steps SKIP nahi. TaskCreate/TaskUpdate se track karo.
- **Blocker = STOP + user se poochho** (missing dep, unclear step, test repeated-fail). Guess karke aage mat badho.
- Plan se deviate karna pade → plan doc update karo PEHLE, fir code (doc = truth).
- Done = `python scripts/prod_check.py` → `scripts\run_tests.bat` + pytest_run.log Read → ship via `leadgen-ops` skill (deploy ke baad naye page-routes = HARD RELOAD).

Parallel multi-agent batch chal raha ho to sibling skill `parallel-batch-build` ke HARD RULES har agent prompt me paste karo. Naya marketing feature = `marketing-feature` skill ka pattern.

Adapted from obra/superpowers `writing-plans` + `executing-plans` (via VoltAgent/awesome-agent-skills).
