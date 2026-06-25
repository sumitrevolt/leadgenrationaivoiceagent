# Runbook — Production Deploy Failure

## Scenario
A deploy breaks production: `/health` fails, a new page-route 404s, the app 502s, or the
container won't start after `docker compose build app + up -d`.

> Three real prod-downs informed this runbook (ML-asset blocking the event loop, stale
> `.pyc` 404, WS handler crash). The patterns below are the distilled fixes.

## Detection
- Deploy verify step: `GET /health` not returning `environment:production` (use sleep 16 + 2× check).
- New `@app.get` page returns 404 despite being in code (stale `.pyc`).
- `docker logs leadgen_app` shows import error / traceback at startup.

## Immediate Response
1. **Health-gate caught it:** the deploy loop has a health-gate + auto-rollback — if the
   new container is unhealthy, roll back to the previous image first, debug second.
2. If you must recover fast, recreate from the last-good image:
   ```bash
   cd /opt/leadgen && docker compose -f docker-compose.vps.yml up -d --no-deps app   # last good
   ```

## Diagnosis (by symptom)
- **New page 404 but code is correct → stale `.pyc`.** Container recreate clears it;
  if running on host instead, hard-reload:
  ```bash
  systemctl stop leadgen; pkill -9 -f uvicorn; find /opt/leadgen/app -name __pycache__ -type d -prune -exec rm -rf {} +; systemctl start leadgen
  ```
  Diagnostic: `python scripts/check_route.py`.
- **App won't start / import error:** `docker logs --tail 120 leadgen_app`. Common: a heavy
  ML asset loaded **on the event loop** (must be `asyncio.to_thread` + deadline + disable-switch).
- **WS closes 1006, no app log:** handler exception **before** its try-block — drive
  `app(scope,receive,send)` directly to surface the real traceback (`debug-ws-handler-crash` lesson).
- **`worker-heavy` / wrong service name aborts `up`:** run `docker compose config --services` first.
- **Build masked failure:** pipe with `set -o pipefail` (a `| tail` can mask a non-zero exit).

## Recovery
1. Roll back to last-good image (above); confirm `/health` green.
2. Fix the root cause locally on **Windows = source of truth** (sandbox mount is stale).
3. Re-run the deploy loop: `python scripts/prod_check.py` → changed-file tests →
   git push → VPS pull + `docker compose build app` + `up -d --no-deps app` (hard reload) →
   verify `/health` = `environment:production` (sleep 16 + 2× check).

## Post-Incident
- RCA: build vs import vs event-loop-block vs stale-pyc. Add the specific guard.
- Any new public ML/KB path must be: image-baked + off-loop load + hard timeout + disable-switch.
- Regression: relevant `tests/test_*`; if a route-wiring gap, `scripts/cross_path_audit.py`.
- Note: CI `deploy-vps.yml` is **gate-only** (`DEPLOY_ENABLED` unset) — push does not
  auto-deploy; actual deploy is the manual SSH step above.
