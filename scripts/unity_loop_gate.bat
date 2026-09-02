@echo off
REM Unity Blueprint Virtual Office loop — Phase A/B/C evidence collector (2026-07-12).
REM Output: uat_evidence\phaseA_git.log, phaseB_python.log, phaseC_unity.log + SENTINEL_DONE.txt
setlocal
cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent
if not exist uat_evidence mkdir uat_evidence
del /q uat_evidence\SENTINEL_DONE.txt 2>nul

set GIT=C:\PROGRA~1\Git\cmd\git.exe
set LOG=uat_evidence\phaseA_git.log

echo ===GIT_STATUS_SHORT_BRANCH=== > %LOG%
%GIT% status --short --branch >> %LOG% 2>&1
echo ===GIT_BRANCH_CURRENT=== >> %LOG%
%GIT% branch --show-current >> %LOG% 2>&1
echo ===GIT_REVPARSE_HEAD=== >> %LOG%
%GIT% rev-parse HEAD >> %LOG% 2>&1
echo ===GIT_REVPARSE_MAIN=== >> %LOG%
%GIT% rev-parse main >> %LOG% 2>&1
echo ===GIT_REVPARSE_ORIGIN_MAIN=== >> %LOG%
%GIT% rev-parse origin/main >> %LOG% 2>&1
echo ===GIT_LOG_20=== >> %LOG%
%GIT% log --oneline --decorate -20 >> %LOG% 2>&1
echo ===GIT_REFLOG_20=== >> %LOG%
%GIT% reflog -20 >> %LOG% 2>&1
echo ===GIT_BRANCH_VV=== >> %LOG%
%GIT% branch -vv >> %LOG% 2>&1
echo ===GIT_DIFF_STAT=== >> %LOG%
%GIT% diff --stat >> %LOG% 2>&1
echo ===GIT_UNTRACKED=== >> %LOG%
%GIT% ls-files --others --exclude-standard >> %LOG% 2>&1
echo ===PHASE_A_DONE=== >> %LOG%

set PY=.venv\Scripts\python.exe
if not exist %PY% set PY=python
set PLOG=uat_evidence\phaseB_python.log

echo ===PY_VERSION=== > %PLOG%
%PY% --version >> %PLOG% 2>&1
echo ===PYTEST_OFFICE_SHELL=== >> %PLOG%
%PY% -m pytest tests\test_office_blueprint_shell.py -q --no-header >> %PLOG% 2>&1
echo EXIT_PYTEST_SHELL=%ERRORLEVEL% >> %PLOG%
echo ===PYTEST_TENANT_ISOLATION=== >> %PLOG%
%PY% -m pytest tests\test_customer_tenant_isolation_authenticated.py -q --no-header >> %PLOG% 2>&1
echo EXIT_PYTEST_ISOLATION=%ERRORLEVEL% >> %PLOG%
echo ===PROD_CHECK=== >> %PLOG%
%PY% scripts\prod_check.py >> %PLOG% 2>&1
echo EXIT_PROD_CHECK=%ERRORLEVEL% >> %PLOG%
echo ===CHECK_SECRETS=== >> %PLOG%
%PY% scripts\check_secrets.py >> %PLOG% 2>&1
echo EXIT_CHECK_SECRETS=%ERRORLEVEL% >> %PLOG%
echo ===COMPILEALL_APP=== >> %PLOG%
%PY% -m compileall app -q >> %PLOG% 2>&1
echo EXIT_COMPILEALL=%ERRORLEVEL% >> %PLOG%
echo ===PHASE_B_DONE=== >> %PLOG%

set ULOG=uat_evidence\phaseC_unity.log
echo ===UNITY_HUB_PROGRAMFILES=== > %ULOG%
if exist "C:\Program Files\Unity Hub\Unity Hub.exe" (echo HUB_FOUND_PROGRAMFILES >> %ULOG%) else (echo HUB_NOT_FOUND_PROGRAMFILES >> %ULOG%)
echo ===UNITY_HUB_LOCALAPPDATA=== >> %ULOG%
if exist "%LOCALAPPDATA%\Programs\Unity Hub\Unity Hub.exe" (echo HUB_FOUND_LOCALAPPDATA >> %ULOG%) else (echo HUB_NOT_FOUND_LOCALAPPDATA >> %ULOG%)
echo ===UNITY_EDITORS_DIR=== >> %ULOG%
dir /b "C:\Program Files\Unity\Hub\Editor" >> %ULOG% 2>&1
echo ===UNITY_EDITORS_DIR_ALT=== >> %ULOG%
dir /b "C:\Program Files\Unity" >> %ULOG% 2>&1
echo ===WHERE_UNITY=== >> %ULOG%
where Unity.exe >> %ULOG% 2>&1
echo WHERE_EXIT=%ERRORLEVEL% >> %ULOG%
echo ===REG_HKLM_UNITY=== >> %ULOG%
reg query "HKLM\SOFTWARE\Unity Technologies" >> %ULOG% 2>&1
echo ===REG_HKCU_UNITY=== >> %ULOG%
reg query "HKCU\SOFTWARE\Unity Technologies" >> %ULOG% 2>&1
echo ===REG_UNINSTALL_UNITYHUB=== >> %ULOG%
reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall" /f "Unity" /s >> %ULOG% 2>&1
echo ===PHASE_C_DONE=== >> %ULOG%

echo ALL_PHASES_DONE > uat_evidence\SENTINEL_DONE.txt
endlocal
exit
