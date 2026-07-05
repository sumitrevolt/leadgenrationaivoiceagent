---
name: verify-ship
description: LeadGen pre-ship verify and deploy loop — prod_check, pytest, secrets scan, explorer_sync, git push, VPS Docker rebuild, health gate. Use before saying done, on /verify, /ship, or any deploy request.
---
# Verify + Ship (mandatory gate)

Combines `.claude/commands/verify.md` + `ship.md`. **"Ho gaya" tabhi jab green.**

## /verify (Windows = truth)

Order (exact):
1. `.venv\Scripts\python.exe scripts\prod_check.py` — FAIL → stop
2. TARGETED pytest DEFAULT: `pytest tests\test_<area>.py -q` (output log file me, console truncate hota)
   - Full `scripts\run_tests.bat` = online/CI-only (offline HANG — LLM/network tests; 2026-07-05)
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
2b. (2026-07-05) `git log origin/main..HEAD` — foreign/automation commits inspect karo (background automation branch pe commit karti hai)
3. Push: `C:\PROGRA~1\Git\cmd\git.exe`
4. VPS:
```bash
# DRIFT-CHECK pehle (hostinger-deploy Step-0) — VPS tree dirty ho sakta hai
ssh -i ~/.ssh/id_rsa root@72.61.245.204
cd /opt/leadgen && git reset --hard origin/main -q
docker compose -f docker-compose.vps.yml build app
docker compose -f docker-compose.vps.yml up -d --no-deps app
sleep 16 && curl -s https://leadsgenai.in/health
```
5. Expect `environment:production` · naye pages = curl 200

Worker/scheduler code changed → also recreate celery profile.

Fail → rollback, don't leave prod red. Detail: `leadgen-ops`, `hostinger-deploy`, `ship-checklist`, `production-ready`.

## Enterprise gate (this IS the evidence gate)
Operating loop: Discover → Contract → Execute → Self-review → **Evidence** (`fable-operating-manual`). This skill OWNS the Evidence phase — "done" = artifact, never assertion. **Bina artifact "ho gaya" KABHI mat bolo.**

**Risk-tier the check depth (don't run a launch audit for a typo, don't `quick` a billing change):**
- **Trivial** (doc/copy/1 fn) → `quick` = steps 1+3 (prod_check + import).
- **Standard** (endpoint/UI/logic) → full /verify steps 1–4 (prod_check + targeted pytest via `pytest_run.log` + import + `check_secrets`).
- **High-risk** (billing/public/telephony/auth/scheduler) → steps 1–6 INCLUDING `cross_path_audit.py` + `explorer_sync.py --check` (0 orphans), and:
  - billing/pricing → `pytest tests\test_billing_truth_2026.py -q` MUST be green (`packages.py` single source).
  - telephony/outbound → `cross_path_audit` covers the vobiz parity path (meter + auto-qualify).
  - any change → self-review the diff (`self-code-review`); High-risk also `security-review`.

**Done-bar (the artifact that gates "ship"):** `prod_check` ALL PASSED (route count noted) · targeted pytest green in `pytest_run.log` (read the file, not console) · `IMPORT_OK` · `check_secrets` clean · optional live `ready_for_first_paid_customer: true`. Any RED → stop, root-cause (`systematic-debugging`), do not push. Post-deploy evidence (handed to /ship): 2× `/health`=`environment:production` + new route curl 200. Live-VPS deploy = explicit user-auth.
