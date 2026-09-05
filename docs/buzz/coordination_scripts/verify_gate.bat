@echo off
set REPO=C:\Users\Ratanshila\Documents\leadgenrationaiagent
set PY=%REPO%\.venv\Scripts\python.exe
cd /d "%REPO%"

echo == check_secrets
"%PY%" scripts\check_secrets.py
echo    exit=%ERRORLEVEL%

echo == ruff on new scripts
"%PY%" -m ruff check scripts\buzzlock.py scripts\buzz_staff_pulse.py
echo    exit=%ERRORLEVEL%

echo == prod_check
"%PY%" scripts\prod_check.py
echo    exit=%ERRORLEVEL%
