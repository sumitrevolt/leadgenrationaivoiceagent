@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A > tc_push.log 2>&1
call "%GIT%" commit -m "feat(telecaller): research-backed TelecallerBrain (permission opener, ACP pattern, 1-question/turn, LARA objections, <=25 words, Hinglish few-shots) + STT warmup at WS open" >> tc_push.log 2>&1
call "%GIT%" push origin main >> tc_push.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> tc_push.log
echo TP_DONE
