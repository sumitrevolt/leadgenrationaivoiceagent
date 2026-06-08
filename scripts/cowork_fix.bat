@echo off
REM Fix RAG embedder + AI-image token + graceful UI. Log -> cowork_fix.log
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_fix.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === py_compile === > %LOG%
call python -m py_compile app\voice_agent\knowledge_base.py app\marketing\ai_image.py scripts\check_rag.py >> %LOG% 2>&1
echo EXIT_PYCOMPILE=%errorlevel% >> %LOG%
echo === git add/commit/push === >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "fix: vector RAG multi-model embedder (fastembed) + AI-image Pollinations token + graceful broken-image UI" >> %LOG% 2>&1
echo EXIT_COMMIT=%errorlevel% >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >> %LOG% 2>&1
echo EXIT_PUSH=%errorlevel% >> %LOG%
echo === VPS pull + restart === >> %LOG%
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && systemctl restart leadgen" >> %LOG% 2>&1
ping -n 8 127.0.0.1 >nul
call %SSH% "cd /opt/leadgen && git log --oneline -1" >> %LOG% 2>&1
call %SSH% "systemctl is-active leadgen" >> %LOG% 2>&1
call %SSH% "curl -s http://127.0.0.1:8000/health" >> %LOG% 2>&1
echo. >> %LOG%
echo === QA: prod_check === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python scripts/prod_check.py > /tmp/pc.log 2>&1; echo PRODCHECK_EXIT=$?; tail -3 /tmp/pc.log" >> %LOG% 2>&1
echo === JS check (marketing.html) === >> %LOG%
call %SSH% "cd /opt/leadgen && python3 scripts/check_marketing_js.py" >> %LOG% 2>&1
echo === RAG verify (embedder + semantic retrieve; may download model) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python scripts/check_rag.py" >> %LOG% 2>&1
echo === DONE === >> %LOG%
