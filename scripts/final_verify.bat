@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
del final_verify.log 2>nul

echo === GIT PUSH === > final_verify.log
call "%GIT%" push origin main >> final_verify.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> final_verify.log

echo === PROD CHECK === >> final_verify.log
.venv\Scripts\python.exe scripts\prod_check.py >> final_verify.log 2>&1
echo PRODCHECK_EXIT_%ERRORLEVEL% >> final_verify.log

echo === PYTEST === >> final_verify.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=no >> final_verify.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> final_verify.log

echo FINAL_VERIFY_DONE
