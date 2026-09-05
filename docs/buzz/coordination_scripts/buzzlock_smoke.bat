@echo off
set REPO=C:\Users\Ratanshila\Documents\leadgenrationaiagent
set PY=%REPO%\.venv\Scripts\python.exe
cd /d "%REPO%"

echo == 1. CURSOR claims a file CLAUDE holds (expect refuse, exit 2)
"%PY%" scripts\buzzlock.py claim app/api/growth_revenue.py --tool CURSOR --reason "exit code check" >nul 2>&1
echo    exit=%ERRORLEVEL%

echo == 2. CURSOR tries STALE-BREAK on a fresh claim (expect refuse, exit 2)
"%PY%" scripts\buzzlock.py break app/api/growth_revenue.py --tool CURSOR >nul 2>&1
echo    exit=%ERRORLEVEL%

echo == 3. CLAUDE releases its own claims (expect ok, exit 0)
"%PY%" scripts\buzzlock.py release app/api/growth_revenue.py tests/test_billing_truth_2026.py --tool CLAUDE --evidence "smoke test complete, no code changed"
echo    exit=%ERRORLEVEL%

echo == 4. CURSOR claims the now-free file (expect ok, exit 0)
"%PY%" scripts\buzzlock.py claim app/api/growth_revenue.py --tool CURSOR --reason "post-release availability check"
echo    exit=%ERRORLEVEL%

echo == 5. CURSOR releases, tree should end clean
"%PY%" scripts\buzzlock.py release app/api/growth_revenue.py --tool CURSOR --evidence "smoke test complete"
echo    exit=%ERRORLEVEL%

echo == 6. final status
"%PY%" scripts\buzzlock.py status
echo    exit=%ERRORLEVEL%
