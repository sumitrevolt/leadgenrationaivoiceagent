---
name: verify-ship
description: LeadGen pre-ship verify and deploy loop — prod_check, pytest, secrets scan, git push, VPS Docker rebuild, health gate. Use before saying done, on /verify, /ship, or any deploy request.
---
# Verify + Ship (mandatory gate)

Combines `.claude/commands/verify.md` + `ship.md`. **"Ho gaya" tabhi jab green.**

## /verify (Windows = truth)

Order (exact):
1. `.venv\Scripts\python.exe scripts\prod_check.py` — FAIL → stop
2. `scripts\run_tests.bat` → **Read `pytest_run.log`** (not console)
3. `.venv\Scripts\python.exe -c "import app.main; print('IMPORT_OK')"`
4. `.venv\Scripts\python.exe scripts\check_secrets.py` (changed files)

`quick` = steps 1+3 only.

Output template:
```
VERIFY: PASS/FAIL
prod_check: OK (N routes) | FAIL
tests: X passed
import: OK
secrets: OK
Ready to ship: YES/NO
```

Targeted tests after feature: `pytest tests\test_<area>.py -q`

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

Fail → rollback, don't leave prod red. Detail: `leadgen-ops`, `hostinger-deploy`, `ship-checklist`.
