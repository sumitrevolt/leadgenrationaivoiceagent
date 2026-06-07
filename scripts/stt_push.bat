@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A > stt_push.log 2>&1
call "%GIT%" commit -m "fix(stt): force Hindi language + vad_filter in whisper (tiny was transcribing Hindi as English garbage); default model base" >> stt_push.log 2>&1
call "%GIT%" push origin main >> stt_push.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> stt_push.log
echo SP_DONE
