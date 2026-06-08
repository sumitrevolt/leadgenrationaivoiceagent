@echo off
REM VPS deploy for this Cowork session. Output -> cowork_vps.log
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_vps.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === PULL + RESTART === > %LOG%
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && systemctl restart leadgen" >> %LOG% 2>&1
echo EXIT_PULL=%errorlevel% >> %LOG%
ping -n 8 127.0.0.1 >nul
echo === HEAD ON VPS === >> %LOG%
call %SSH% "cd /opt/leadgen && git log --oneline -1" >> %LOG% 2>&1
echo === IS-ACTIVE === >> %LOG%
call %SSH% "systemctl is-active leadgen" >> %LOG% 2>&1
echo === HEALTH === >> %LOG%
call %SSH% "curl -s http://127.0.0.1:8000/health" >> %LOG% 2>&1
echo. >> %LOG%
echo === INSTALL AGENT DEPS (langgraph-supervisor + langchain-openai) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/pip install -q langgraph-supervisor langchain-openai" >> %LOG% 2>&1
echo EXIT_PIP=%errorlevel% >> %LOG%
echo === IMPORT CHECK (deps only; running app NOT restarted with them) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python -c 'import langgraph_supervisor, langchain_openai'" >> %LOG% 2>&1
echo EXIT_IMPORT=%errorlevel% >> %LOG%
echo === DONE === >> %LOG%
