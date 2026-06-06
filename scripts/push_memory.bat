@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add CLAUDE.md scripts/push_memory.bat > push_mem.log 2>&1
call "%GIT%" commit -m "docs: web-call LLM fix notes (quota per model, probe/test commands)" >> push_mem.log 2>&1
call "%GIT%" push origin main >> push_mem.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> push_mem.log
echo PM_DONE
