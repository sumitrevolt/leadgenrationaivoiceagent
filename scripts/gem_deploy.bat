@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del gem.log 2>nul
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A > gem.log 2>&1
call "%GIT%" commit -m "feat(stt): Gemini audio-in as PRIMARY hearing (multimodal, Hinglish-strong, free tier) with whisper fallback; per-call transcript persistence to data/call_transcripts (continuous-training fuel)" >> gem.log 2>&1
call "%GIT%" push origin main >> gem.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> gem.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=25 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && git log -1 --oneline && .venv/bin/pip install -U -q google-genai 2>&1 | tail -1; find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 14 && systemctl is-active leadgen && timeout 50 .venv/bin/python scripts/conv_test.py 2>&1 | grep -aE 'STREAM CALL'" >> gem.log 2>&1
echo GEM_EXIT_%ERRORLEVEL% >> gem.log
echo GEM_DONE
