@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A > p12p.log 2>&1
call "%GIT%" commit -m "ops: P1+P2 live on VPS - agents smoke script, deps fix scripts, CLAUDE.md stack status" >> p12p.log 2>&1
call "%GIT%" push origin main >> p12p.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> p12p.log
echo DONE
