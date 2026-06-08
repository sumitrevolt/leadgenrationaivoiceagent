@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
del eapi2.log 2>nul
.venv\Scripts\python.exe -m pytest tests/test_auto_outreach.py -q --no-header -p no:cacheprovider --tb=line > eapi2.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> eapi2.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A >> eapi2.log 2>&1
call "%GIT%" commit -m "test(auto_outreach): skip reason smtp_unset -> email_unconfigured (API-or-SMTP gate)" >> eapi2.log 2>&1
call "%GIT%" push origin main >> eapi2.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> eapi2.log
echo EAPI2_DONE
