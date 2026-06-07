@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del fad.log 2>nul

echo === IMPORT + PYTEST === > fad.log
.venv\Scripts\python.exe -c "from app.main import app; import app.voice_agent.free_ai as f; print('free_ai OK; providers:', f.describe())" >> fad.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> fad.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> fad.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> fad.log

echo === COMMIT+PUSH === >> fad.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A >> fad.log 2>&1
call "%GIT%" commit -m "feat(free-ai): multi-provider STT (Groq Whisper-large-v3) + LLM (Cerebras llama-3.3-70b / Groq / OpenRouter) fallback chains; KB-grounded TelecallerBrain; repeated-answer guard — kills Gemini quota choke" >> fad.log 2>&1
call "%GIT%" push origin main >> fad.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> fad.log

echo === VPS DEPLOY === >> fad.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=25 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && git log -1 --oneline && .venv/bin/pip install -U -q openai 2>&1 | tail -1; find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 14 && systemctl is-active leadgen && .venv/bin/python -c 'import app.voice_agent.free_ai as f; print(f.describe())'" >> fad.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> fad.log
echo FAD_DONE
