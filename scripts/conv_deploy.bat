@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del conv_deploy.log 2>nul

echo === LOCAL IMPORT CHECK === > conv_deploy.log
.venv\Scripts\python.exe -c "from app.main import app; import app.telephony.vobiz_stream as v; print('import OK; STT=',v.STT_AVAILABLE,'TTS=',v.TTS_AVAILABLE)" >> conv_deploy.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> conv_deploy.log

echo === PYTEST === >> conv_deploy.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> conv_deploy.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> conv_deploy.log

echo === COMMIT+PUSH === >> conv_deploy.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A >> conv_deploy.log 2>&1
call "%GIT%" commit -m "feat(P3): conversational phone AI via Vobiz WebSocket streaming (mu-law audioop chain, VAD turn-taking, barge-in, EdgeTTS hi-IN -> STT -> LLMBrain); stream-call + answer-stream routes" >> conv_deploy.log 2>&1
call "%GIT%" push origin main >> conv_deploy.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> conv_deploy.log

echo === VPS DEPLOY + STT INSTALL === >> conv_deploy.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && .venv/bin/pip install -q faster-whisper 2>&1 | tail -2 ; echo PIP_RC=$? ; systemctl restart leadgen && sleep 14 && systemctl is-active leadgen && echo ---STREAM-STATUS--- && curl -s -m 8 http://127.0.0.1:8000/api/telephony/vobiz/status" >> conv_deploy.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> conv_deploy.log
echo CONV_DONE >> conv_deploy.log
echo CONV_DONE
