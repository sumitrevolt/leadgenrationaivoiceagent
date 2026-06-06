@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add CLAUDE.md scripts/commit_memory.bat > commit_mem.log 2>&1
call "%GIT%" commit -m "docs: CLAUDE.md production deploy status + VPS ops notes" >> commit_mem.log 2>&1
call "%GIT%" push origin main >> commit_mem.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> commit_mem.log
echo MEM_DONE
