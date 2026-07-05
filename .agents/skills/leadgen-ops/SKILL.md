---
name: leadgen-ops
description: LeadGen AI ka proven ops loop — verify, test, push, deploy + production triage. Use when the user says "deploy", "redeploy", "tests chalao", "VPS issue", "production error", "verify karo", "push karo", or anything about shipping code to leadsgenai.in / debugging the live Docker server.
---

# LeadGen Ops Loop (verify → test → push → deploy)

Yeh exact cycle har deploy pe follow karo — **gated**: har step ka ek PASS-bar hai; bar fail = **ABORT** (aage mat badho, partial deploy = prod-down). Live stack = Hostinger VPS Docker (`leadgen_app` container :8000, `docker-compose.vps.yml`), NOT systemd. **Windows = source of truth** (sandbox mount file-edits ke baad STALE — verify Windows venv pe).

## Step 0 — Pre-flight gate (deploy karna chahiye ya nahi)
- **Code change hai?** Sirf `./data`/`./logs` (bind-mount) badla → rebuild NAHI, sidha recreate/koi action nahi. Code/`app/`/`frontend/`/`.claude/skills/` badla → full rebuild zaroori (image me BAKED).
- **Branch**: `main` pe ho? VPS `origin/main` se reset karta hai — feature-branch ka kaam live nahi jaata.
- **Naya `@app.get` page-route** add kiya? → deploy ke baad **HARD RELOAD** lazmi (stale `.pyc` = 404). Container recreate isko handle karta; warna `scripts/check_route.py` se diagnose.
- **ABORT pehle hi agar**: uncommitted secret risk, prod abhi incident me hai (pehle `prod-incident-triage`), ya user ne sirf "test/verify" maanga (deploy step skip).

## The proven loop (4 gated steps)

1. **Pre-flight check** — `python scripts/prod_check.py` (parse/pycache/import/route/config). **Route count note karo** (deploy ke baad match karne ke liye). 
   → **GATE**: koi fail = fix karo, aage NAHI. Green = next.
2. **Tests** — `scripts\run_tests.bat`, phir **`pytest_run.log` Read karo** (console truncate hota — log = truth). ~80+ green expected. Full pytest `team_pulse` area pe hang ho sakta → targeted suite: `.venv\Scripts\python.exe -m pytest tests\test_X.py -q`. Billing/pricing/route touch hua → `test_billing_truth_2026.py` zaroor. Frontend office map touch hua → `tests\test_office_map_frontend.py` (JS syntax gate + no-removal guard, 2026-07-05) zaroor.
   → **GATE**: red test = root-cause (`systematic-debugging`), fix, re-run. Skip-with-reason sirf agar pre-existing-unrelated (log me note).
3. **Git push** — Windows git hi: `C:\PROGRA~1\Git\cmd\git.exe`, hamesha ek `.bat` ke andar (DC one-liner quoting mangle; sandbox git index unreadable). Reference: `scripts/fix_push_redeploy.bat`. Secrets kabhi committed file me nahi (`scripts/check_secrets.py`).
   → **GATE**: push success (remote SHA match) confirm karo. **+ (2026-07-05) Foreign-commit check**: push se pehle `git log origin/main..HEAD --format="%h %s"` — background automation checked-out branch pe apne commits banati hai; unhe pehchano (inspect, intentionally include/exclude) — anjaane me automation ka unreviewed kaam push mat karo.
4. **VPS pull + rebuild + recreate** — Git ka ssh.exe (Windows OpenSSH is PC pe broken). Image me code BAKED → **rebuild lazmi** (git-pull-restart kaafi NAHI). Build pipe `| tail` exit-code maskta → `set -o pipefail`. Compose service naam galat (`worker-heavy` hyphen) = poora `up` ABORT → pehle `docker compose ... config --services`.
   ```
   C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204 \
     "set -o pipefail; cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && \
      docker compose -f docker-compose.vps.yml build app && \
      docker compose -f docker-compose.vps.yml up -d --no-deps app"
   ```
   SSH command me `&`/`<` quoting todta (EXIT_9009) → complex logic `.py` me likho, `ssh ... python scripts/x.py` se chalao.
   - **(2026-07-05) DRIFT-CHECK pehle**: upar wala one-liner blind `reset --hard` karta hai — VPS tree chronically dirty rehta hai (live hotfixes); pehle `hostinger-deploy` skill ka Step-0 drift-check (`git status --porcelain` + `docker diff leadgen_app`) chalao, drift dikhe to PRESERVE karo.
   - **(2026-07-05) Deploy target = user-confirmed**: host/IP user ke message se confirm hona chahiye (docs se uthaya hua target user ko bata ke haan lo) — permission classifier bhi yahi enforce karta hai.
   - **Automation/worker code badla** (`team_scheduler.py` · `self_improve.py` · `worker.py` · `staff_jobs.py` · scheduled engines) → sirf `app` recreate KAAFI NAHI — `worker`/`scheduler` purana code chalate rehte. Build + recreate **app + worker + worker-heavy + scheduler** (`--profile celery up -d --no-deps app worker worker-heavy scheduler`). Pure frontend/page change = sirf `app`.
   - **Repeated worker recreate (ek session me 3-5×) = celery flood risk**: `self_improve_tick` self-requeue chain multiply ho sakti (`acks_late` redelivery + revive). Recreate ke baad `docker exec leadgen_redis redis-cli llen celery` check — >800 = `redis-cli del celery` (beat re-schedules, revive 1 chain re-seed). `saturday_hygiene` job auto-trims.

## Step 5 — Verify + done-gate (bina proof "done" mat bolo)
- `sleep 16` (boot-grace) **+ 2x** `https://leadsgenai.in/health` → **`environment:production`** + 200. Ek-baar pass pe bharosa mat karo.
- Route count Step-1 se match? Naya page-route 200 de raha (404 nahi)?
- **Health fail → ROLLBACK** (niche), phir root-cause — broken prod chhod ke mat jao.
- **Report (structured)**:
  ```
  SHIP: ok | rolled-back
  push:   <SHA>
  build:  ok | fail:<reason>
  health: 200 environment:production (2/2)
  routes: <N> (Δ vs pre)
  ```

## Rollback (deploy ke baad health red)
- **Fast**: pichla good image abhi chal raha tha → `git reset --hard <prev-SHA>` + rebuild + recreate (forward-fix-by-revert).
- **Scheduler/worker se aaya** → `.env`: `RUN_IN_PROCESS_SCHEDULER=1` + `WEB_CONCURRENCY=1`, worker/scheduler stop, app recreate.
- **systemd `leadgen`** = installed-but-DISABLED (last-resort rollback). Default path Docker hi.

## Production triage table

| Symptom | Root cause | Fix |
|---|---|---|
| App unhealthy + CPU ~0%, WS/endpoint hang | Sync ML/KB init event-loop par freeze (classic prod-down) | `docker logs leadgen_app`; HOST se `py-spy dump --pid $(pgrep -f uvicorn\|head -1)`; `docker restart leadgen_app`. Root: `asyncio.to_thread`+hard-timeout (`model-asset-bake` + `prod-incident-triage`) |
| First WS hit after rebuild hangs (~250MB HF download) | ML asset runtime-download, baked nahi | Model BAKE in `Dockerfile.lock` + disable-switch (`model-asset-bake`) |
| Naya page-route 404 after deploy | Stale `.pyc` (page-route hard-reload chahiye) | Container recreate; ya `find /opt/leadgen/app -name __pycache__ -prune -exec rm -rf {} +` + restart. Diagnose: `scripts/check_route.py` |
| Bot rule-based / "[echo / test-mode]" | Free LLM provider cooldown (Cerebras/Groq 429/TPD) | `docker logs leadgen_app \| grep -iE "429\|quota"`; circuit-breaker self-recovers (60s→30min). Mistral=primary, Gemini=late fallback (`llm-quota-ops`) |
| Random 500s (e.g. /api/data/niches) | Stale `__pycache__` (fresh image me nahi) | Rebuild app + recreate. `prod_check.py` locally yehi class pakadta |
| Naye deps import-fail in container | image lock out of date | `requirements.lock.txt` refresh (`scripts/vps_freeze.sh`) → commit → rebuild |
| celery queue blow-up after worker recreate (1000s of `self_improve_tick`) | self-improve self-requeue chain MULTIPLIED — repeated recreate × `acks_late` redelivery + revive (no dedup) → parallel chains | `redis-cli llen celery`; >800 = `del celery` (beat re-schedules, revive re-seeds 1 chain). Root-fixed: `self_improve_tick acks_late=False` + `ensure_alive` Redis NX lock (2026-06-19) |

## Long-running commands (DC ~60s pe process kill kar deta)
Launcher-bat: `.bat` me `start /min cmd /c "<long cmd> > C:\path\log.txt 2>&1"` — turant return — phir log file poll-Read karo done-marker tak. pip/npm/full-pytest sab isi se. (`.bat` me npm/git ko `call` se; `timeout /t` → `ping -n N 127.0.0.1`.)

## Smoke tests
- **Local**: `scripts\smoke_test.bat` (app boot + key endpoints).
- **VPS agents** (LangGraph/Qdrant/MCP): `docker exec leadgen_app python scripts/vps_agents_test.py`
- **VPS live websocket** (web-call bot): `docker exec leadgen_app python scripts/ws_test.py`
- **LLM probe**: `docker exec leadgen_app python scripts/llm_probe.py`

Sibling skills (VPS-level: Caddy vs Traefik, .env inline comments, firewalled ports, rollback detail): `hostinger-deploy`, `ship-checklist`, `prod-incident-triage`.

## Enterprise gate (deploy = High-risk always)
- **Operating loop:** Discover → Contract → Execute → Self-review → Evidence (`fable-operating-manual`). Yahan **Execute = the 4 gated steps above; Evidence = the done-gate**.
- **Change-risk tier:** live-VPS deploy is **High-risk by default** — it locks: ABORT-on-any-step-fail, **hard-reload** (container recreate, warna stale `.pyc` page-route 404), 2× `/health`=`environment:production`, and a **named rollback ready before pushing**. Touching billing/pricing → `test_billing_truth_2026` green SAATH; public route → SSRF/auth re-check.
- **Safety:** secrets sirf `/opt/leadgen/.env` (gitignored) — `scripts/check_secrets.py` step-3 me; never in committed file/`.bat`/CLAUDE.md. Code/skill change = rebuild (BAKED); data-only (`./data`/`./logs`) = no rebuild.
- **Reliability:** every deploy = health-gate + **named rollback** (fast `git reset --hard <prev-SHA>` + rebuild · scheduler-class → `RUN_IN_PROCESS_SCHEDULER=1`+`WEB_CONCURRENCY=1` · last-resort systemd `leadgen`). Worker/scheduler code → recreate `--profile celery` too; after recreate `redis-cli llen celery` >800 → `del celery` (celery-flood guard).
- **Observability:** `docker logs leadgen_app -n 60` · `docker stats --no-stream` (CPU 0% + hang = event-loop freeze → `prod-incident-triage`) · `/api/growth/infra/automation-health` (admin) for job liveness · `dlq:failed_tasks` for failed jobs · flower :5555.
- **Evidence (done):** `scripts\prod_check.py` green + `pytest_run.log` read + 2× `/health`=`environment:production` + route-count Δ vs pre-deploy + new page-route curl 200. Live-VPS deploy = **explicit user-auth** (infer mat karo).
