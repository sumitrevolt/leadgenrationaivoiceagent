@echo off
REM Deploy: outreach bounce-detection fix + staged OUTREACH_AB rollout (2026-07-04, llm-council verdict)
REM Fully unattended: prod_check -> tests -> git push -> VPS build+recreate -> health verify.
REM All gates are automatic (errorlevel / findstr) - no keypress needed. Everything is
REM logged to scripts\deploy_run.log so progress/result can be reviewed after the fact.
REM Follows CLAUDE.md deploy loop exactly. Double-click to run (cd's to repo root itself).

cd /d "%~dp0.."
set LOG=scripts\deploy_run.log
echo ===== DEPLOY RUN %date% %time% ===== > "%LOG%"

echo STEP 1/6: prod_check.py >> "%LOG%"
python scripts\prod_check.py >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ABORT] prod_check FAILED - see log. >> "%LOG%"
  exit /b 1
)
echo [OK] prod_check passed. >> "%LOG%"

echo STEP 2/6: test suite >> "%LOG%"
call scripts\run_tests.bat
findstr /C:"PYTEST_EXIT_0" pytest_run.log >nul
if errorlevel 1 (
  echo [ABORT] tests FAILED - see pytest_run.log. Deploy stopped. >> "%LOG%"
  exit /b 1
)
echo [OK] all tests passed (PYTEST_EXIT_0). >> "%LOG%"

echo STEP 3/6: git commit + push >> "%LOG%"
"C:\PROGRA~1\Git\cmd\git.exe" add -A >> "%LOG%" 2>&1
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "fix(outreach): bounce/NDR auto-detection + staged OUTREACH_AB rollout (llm-council verdict 2026-07-04)" >> "%LOG%" 2>&1
"C:\PROGRA~1\Git\cmd\git.exe" push >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ABORT] git push FAILED - see log. >> "%LOG%"
  exit /b 1
)
echo [OK] pushed to remote. >> "%LOG%"

echo STEP 4/6: VPS - git pull >> "%LOG%"
"C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204 "cd /opt/leadgen && git pull" >> "%LOG%" 2>&1

echo STEP 5/6: VPS - docker build + recreate app container >> "%LOG%"
"C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204 "cd /opt/leadgen && docker compose -f docker-compose.vps.yml build app" >> "%LOG%" 2>&1
"C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204 "cd /opt/leadgen && docker compose -f docker-compose.vps.yml up -d --no-deps app" >> "%LOG%" 2>&1

echo STEP 6/6: wait 16s + verify health >> "%LOG%"
ping -n 17 127.0.0.1 >nul
"C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204 "curl -s localhost:8000/health" >> "%LOG%" 2>&1
echo. >> "%LOG%"
echo ===== DEPLOY DONE %date% %time% ===== >> "%LOG%"
echo Check scripts\deploy_run.log - health output above should show environment:production. >> "%LOG%"
echo NEXT (manual - production email decision, deliberately not automated): >> "%LOG%"
echo   OUTREACH_AB=1 + OUTREACH_AB_PCT=5 add karo VPS .env me jab ready ho, phir app restart. >> "%LOG%"
