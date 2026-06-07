@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
del scrub.log 2>nul
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
REM unpushed commits (jinme secret tha) ki history wipe — working tree intact
call "%GIT%" reset --soft origin/main > scrub.log 2>&1
call "%GIT%" add -A >> scrub.log 2>&1
call "%GIT%" commit -m "feat(free-ai): xAI Grok in LLM chain + xai_api_key config; scripts secret-free (keys only in gitignored .env)" >> scrub.log 2>&1
echo COMMIT_EXIT_%ERRORLEVEL% >> scrub.log
call "%GIT%" push origin main >> scrub.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> scrub.log
call "%GIT%" log -1 --oneline >> scrub.log 2>&1
echo SCRUB_DONE
