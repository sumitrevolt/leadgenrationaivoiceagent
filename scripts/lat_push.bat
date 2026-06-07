@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A > lat_push.log 2>&1
call "%GIT%" commit -m "perf(voice): instant cached greeting (pregen at WS accept, no LLM on greet path), module-level STT warmup thread, ack fillers, snappier VAD (550ms), whisper domain prompt, 6s LLM timeout" >> lat_push.log 2>&1
call "%GIT%" push origin main >> lat_push.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> lat_push.log
echo LP_DONE
