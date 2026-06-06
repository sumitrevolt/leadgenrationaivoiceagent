@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del fc.log 2>nul

echo === ENSURE DEPS === > fc.log
.venv\Scripts\python.exe -c "import langgraph, qdrant_client, fastembed, fastapi_mcp; print('deps OK')" >> fc.log 2>&1
if errorlevel 1 (
  echo installing... >> fc.log
  .venv\Scripts\python.exe -m pip install -q "qdrant-client>=1.12.0" "fastembed>=0.4.0" "langgraph>=1.0" "langgraph-checkpoint-sqlite>=2.0" "langchain-core>=0.3" "fastapi-mcp>=0.3" >> fc.log 2>&1
  echo PIP_EXIT_%ERRORLEVEL% >> fc.log
)

echo === PYTEST === >> fc.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> fc.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> fc.log

echo === COMMIT+PUSH === >> fc.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A >> fc.log 2>&1
call "%GIT%" commit -m "ops: leadgen-ops + niche-onboarding skills, README agentic-stack update, route_for_task pure fn + 17 stack tests" >> fc.log 2>&1
call "%GIT%" push origin main >> fc.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> fc.log

echo === VPS PULL+RESTART+VERIFY === >> fc.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && systemctl restart leadgen && sleep 12 && systemctl is-active leadgen && curl -s -m 8 http://127.0.0.1:8000/api/agents/status && echo && curl -s -m 8 http://127.0.0.1:8000/health" >> fc.log 2>&1
echo VPS_EXIT_%ERRORLEVEL% >> fc.log
echo FC_DONE >> fc.log
echo FC_DONE
