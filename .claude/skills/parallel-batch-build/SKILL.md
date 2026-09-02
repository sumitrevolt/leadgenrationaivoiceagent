---
name: parallel-batch-build
description: 10-20 features ek session me parallel sub-agents se banane ka PROVEN pattern (batch-3 me 16 features aise hi bane). Use when user says "sab karo", "in parallel", "bulk features", "competitor parity batch", or any multi-feature build. Captures disjoint-file ownership, wiring rules, and the 2 prod-down lessons.
---

# Parallel Batch Build (multi-agent, disjoint files)

16-feature batch isi pattern se LIVE hua (commits e765911+a1da957). Re-derive mat karo.

## Pattern
1. **Features ko 3-4 agents me group karo by DOMAIN** (conversion/creative/client-facing/ops) — har agent ka apna NAYA router file `app/api/<domain>.py` + apne naye modules + apna test file `tests/test_parity_<domain>.py`.
2. **File ownership matrix LIKHO prompt me** — ek file = ek hi owner. Shared files (`app/main.py`, `app/api/growth.py`, `app/api/marketing.py`, `app/api/public_site.py`, `app/platform/team_scheduler.py`, `app/worker.py`, `docker-compose.vps.yml`, `requirements*.txt`) **KOI agent touch nahi karta** — wiring main session sequentially karta hai (mounts, page routes, AUTOMATION_FLAGS, scheduler hooks best-effort try/except).
3. Har agent prompt me ye HARD RULES paste karo: grep-before-build (duplicate route = prod shadow), never-raise, lazy imports, gated flags default OFF, rate_limit public pe, require_admin pattern copy from creative.py, Hinglish strings, pure-python tests (no network/DB).
4. **Launch all agents in ONE block** (parallel). Reports me mangwao: files, mount lines, flags, scheduler hooks, skipped+why.
5. Wiring → `python scripts/prod_check.py` → `scripts\run_tests.bat` + targeted pytest suites (full pytest team_pulse area pe HANG ho sakta — targeted use karo, `pytest_run.log` Read) → commit → deploy → **smoke me naye PUBLIC endpoints zaroor hit karo** → health re-check.

## 2 PROD-DOWN LESSONS (batch-3 me dono hue)
- **Public endpoint me KB/ML/sync-SDK = thread + hard timeout.** `kb.retrieve`/fastembed first-load/google-generativeai sync SDK event loop pe = dono workers starve = site down. Fix pattern: `await asyncio.wait_for(asyncio.to_thread(fn), timeout=10-25s)`. Smoke me chat/LLM endpoint ke DAURAN health poll karo (6x).
- **Compose healthcheck me sirf wo binary use karo jo image me HAI** — `pgrep` nahi tha → unhealthy → selfheal cron 10-min restart-loop. `/proc/[0-9]*/cmdline` grep use karo.

## Smoke gotchas
- DC one-liner ssh quoting todta → script `outputs/x.sh` likho → `ssh "bash -s" < x.sh`, output log me, log Read.
- MCP call ~60s pe timeout — lambi remote jobs `start /b` + log poll (ping -n 50 chunks).

## Enterprise gate (N parallel features = N× blast radius)

Run the operating loop — Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). A parallel batch = **High-risk by aggregation** (one bad public handler downs the whole site): per-agent disjoint ownership + flag-gate default OFF + the 2 prod-down lessons are non-negotiable.

- **Disjoint-file ownership (hard gate):** ek file = ek owner. Shared files (`app/main.py`, `app/api/{growth,marketing,public_site}.py`, `team_scheduler.py`, `worker.py`, `docker-compose.vps.yml`, `requirements*.txt`) = **NO agent touches** — main session wires sequentially (mounts, page routes, `AUTOMATION_FLAGS`, scheduler hooks best-effort try/except). Bade multi-edit same-file parallel = truncation hazard.
- **Per-agent HARD RULES (paste in every prompt):** `duplicate-route-guard` grep-before-build (duplicate route = prod shadow) · never-raise + lazy imports · new flags default OFF + registered in `AUTOMATION_FLAGS` (`/api/growth/infra/flags`) · `rate_limit` on public routes · `require_admin` copy from creative.py · pure-python tests (no network/DB) · Hinglish strings.
- **Compliance + side-effects:** koi batch agent auto-send/auto-post/auto-dial wire na kare — send/call sirf existing gated engines (DLT/DND/warmup) se. Secrets sirf `.env`.
- **The 2 PROD-DOWN lessons (re-confirm each batch):** (1) public endpoint me KB/ML/sync-SDK = `await asyncio.wait_for(asyncio.to_thread(fn), timeout=10-25s)` — warna both workers starve = site down; smoke me chat/LLM endpoint ke DAURAN health 6× poll. (2) compose healthcheck me sirf in-image binary (`/proc/[0-9]*/cmdline` grep, `pgrep` nahi) — warna selfheal 10-min restart-loop.
- **Rollback (NAMED):** har feature flag OFF = instant inert (no behaviour change) · revert per-domain router file + its mount line · container recreate `docker compose -f docker-compose.vps.yml up -d --no-deps app`. Disjoint ownership = one feature revert never touches others.
- **Evidence (done):** wiring → `.venv\Scripts\python.exe scripts\prod_check.py` → `scripts\run_tests.bat` + targeted `pytest tests\test_parity_<domain>.py -q` (full pytest hangs in team_pulse — targeted only; Read `pytest_run.log`) → `scripts\check_secrets.py` → commit → deploy → **smoke har naye PUBLIC endpoint hit** + 6× health poll → `/health` = `environment:production`. Live deploy = explicit user-auth.
