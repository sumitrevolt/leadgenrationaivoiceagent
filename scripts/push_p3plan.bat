@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add docs/P3_Own_Telephony_Stack_Plan.md CLAUDE.md scripts/push_p3plan.bat > pp3.log 2>&1
call "%GIT%" commit -m "docs: P3 decision - own telephony stack (FreeSWITCH+Pipecat+Plivo) + white-label resell plan" >> pp3.log 2>&1
call "%GIT%" push origin main >> pp3.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> pp3.log
echo DONE
