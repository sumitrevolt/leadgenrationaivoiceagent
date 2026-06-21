---
name: verify-ship
description: LeadGen pre-ship verify and deploy loop — prod_check, pytest, secrets scan, explorer_sync, git push, VPS Docker rebuild, health gate. Use before saying done, on /verify, /ship, or any deploy request.
---
# Verify + Ship (mandatory gate)

Combines `.claude/commands/verify.md` + `ship.md`. **"Ho gaya" tabhi jab green.**

## /verify (Windows = truth)

Order (exact):
1. `.venv\Scripts\python.exe scripts\prod_check.py` — FAIL → stop
2. `scripts\run_tests.bat` → **Read `pytest_run.log`** (not console)
   - OR targeted: `pytest tests\test_<area>.py -q` (faster)
3. `.venv\Scripts\python.exe -c "import app.main; print('IMPORT_OK')"`
4. `.venv\Scripts\python.exe scripts\check_secrets.py` (changed files)

**Full readiness** (launch audit):
5. `.venv\Scripts\python.exe scripts\explorer_sync.py --check`
6. `.venv\Scripts\python.exe scripts\cross_path_audit.py`

`quick` = steps 1+3 only.

Live probe (optional):
```powershell
curl.exe -fsS https://leadsgenai.in/health
curl.exe -fsS https://leadsgenai.in/api/activation/summary
```

Windows: use **`curl.exe`** not `curl` (PowerShell alias breaks).

Output template:
```
VERIFY: PASS/FAIL
prod_check: OK (N routes) | FAIL
tests: X passed
import: OK
secrets: OK
live: ready_for_first_paid_customer true/false
Ready to ship: YES/NO
```

## /ship (only if verify PASS)

1. Verify full PASS
2. Commit (user asked) — simple message, no secrets
3. Push: `C:\PROGRA~1\Git\cmd\git.exe`
4. VPS:
```bash
ssh -i ~/.ssh/id_rsa root@72.61.245.204
cd /opt/leadgen && git reset --hard origin/main -q
docker compose -f docker-compose.vps.yml build app
docker compose -f docker-compose.vps.yml up -d --no-deps app
sleep 16 && curl -s https://leadsgenai.in/health
```
5. Expect `environment:production` · naye pages = curl 200

Worker/scheduler code changed → also recreate celery profile.

Fail → rollback, don't leave prod red. Detail: `leadgen-ops`, `hostinger-deploy`, `ship-checklist`, `production-ready`.
