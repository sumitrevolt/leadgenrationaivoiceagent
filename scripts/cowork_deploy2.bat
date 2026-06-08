@echo off
REM RAG deploy (LightRAG + agentic). Push + VPS pull/restart/install/verify. Log -> cowork_deploy2.log
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_deploy2.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === py_compile new RAG modules === > %LOG%
call python -m py_compile app\voice_agent\graph_rag.py app\agents\agentic_rag.py >> %LOG% 2>&1
echo EXIT_PYCOMPILE=%errorlevel% >> %LOG%
echo === git add/commit/push === >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(rag): LightRAG knowledge-graph + agentic CRAG retrieval (opt-in, defensive) + doc" >> %LOG% 2>&1
echo EXIT_COMMIT=%errorlevel% >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >> %LOG% 2>&1
echo EXIT_PUSH=%errorlevel% >> %LOG%
echo === VPS pull + restart (safe code first) === >> %LOG%
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && systemctl restart leadgen" >> %LOG% 2>&1
echo EXIT_PULL=%errorlevel% >> %LOG%
ping -n 8 127.0.0.1 >nul
echo === HEAD / IS-ACTIVE / HEALTH === >> %LOG%
call %SSH% "cd /opt/leadgen && git log --oneline -1" >> %LOG% 2>&1
call %SSH% "systemctl is-active leadgen" >> %LOG% 2>&1
call %SSH% "curl -s http://127.0.0.1:8000/health" >> %LOG% 2>&1
echo. >> %LOG%
echo === INSTALL lightrag-hku (after restart; opt-in so cannot affect running app) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/pip install -q lightrag-hku" >> %LOG% 2>&1
echo EXIT_PIP=%errorlevel% >> %LOG%
echo === IMPORT CHECK lightrag === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python -c 'import lightrag'" >> %LOG% 2>&1
echo EXIT_IMPORT=%errorlevel% >> %LOG%
echo === HEALTH AGAIN (box still fine) === >> %LOG%
call %SSH% "curl -s http://127.0.0.1:8000/health" >> %LOG% 2>&1
echo. >> %LOG%
echo === DONE === >> %LOG%
