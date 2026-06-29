---
description: LeadGen AI ka full pre-ship verify loop chalao (prod_check + tests + import) aur PASS/FAIL report do.
---
# /verify — LeadGen AI verification loop

Project ka REAL verify loop. **Windows = source of truth** (sandbox mount file-edits ke baad STALE hota hai — Windows venv pe verify karo).

## Steps (exact order)
1. **prod_check**: `.venv\Scripts\python.exe scripts\prod_check.py` — parse/pycache/import/route/config. Route count note karo. FAIL → ruk jao + report.
2. **Tests**: `scripts\run_tests.bat` → phir **`pytest_run.log` Read karo** (console truncate hota hai, log = truth). ~80+ green expected. Targeted: `.venv\Scripts\python.exe -m pytest tests\test_X.py -q`.
3. **Import**: `.venv\Scripts\python.exe -c "import app.main; print('IMPORT_OK')"`.
4. **Secrets**: `.venv\Scripts\python.exe scripts\check_secrets.py` (changed files scan; patterns: api-keys/JWT/sk_/rzp_live/AKIA/private-key). FAIL → secret `.env` me move karo; false-positive = us line pe `nosecret` comment. Full audit: `--all`.

## Output
```
VERIFY: PASS/FAIL
prod_check: OK (N routes) | FAIL: <reason>
tests:     X passed / Y failed
import:    OK/FAIL
secrets:   OK/found
Ready to ship: YES/NO
```

`$ARGUMENTS`: `quick` = prod_check + import only · `full` = sab (default).

## Step 5 — RL marker (Loop B, INERT unless RL_ENGINE set)
Report print karne ke BAAD `data/.claude_last_verify.json` likho (Windows file-tools):
`{"ts": "<ISO-8601 UTC now>", "pass": <bool>, "tests_pass": <bool>, "review_findings": <int|null>, "deploy_health": <str|null>}`.
`ts` zaroori — Stop hook stale marker (>2h purana) ko ignore karta hai aur read ke baad consume (delete) karta hai, taaki ek verify-result kai sessions pe misattribute na ho.
Ye marker `Stop` hook (`.claude/hooks/reward_capture.py`) padhta hai session ka dev-reward score karne ke liye. Sirf metadata — secrets/code NAHI. RL_ENGINE unset = hook no-op, marker harmless.
