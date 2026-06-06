@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del p12d.log 2>nul

echo === COMMIT+PUSH === > p12d.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A >> p12d.log 2>&1
call "%GIT%" commit -m "feat(stack): Qdrant payload-partitioned RAG backend (fastembed e5-small, graceful fallback) + LangGraph supervisor (data/leads agent nodes, /api/agents/run) + fastapi_mcp mount (/mcp) + Qdrant docker in deploy" >> p12d.log 2>&1
echo COMMIT_EXIT_%ERRORLEVEL% >> p12d.log
call "%GIT%" push origin main >> p12d.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> p12d.log

echo === VPS FULL DEPLOY (pip + qdrant + restart) === >> p12d.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && bash deploy_vps.sh 2>&1 | tail -12" >> p12d.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> p12d.log

echo === VERIFY === >> p12d.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "sleep 5; systemctl is-active leadgen; echo ---AGENTS-STATUS---; curl -s -m 8 http://127.0.0.1:8000/api/agents/status; echo; echo ---QDRANT---; curl -s -m 5 http://127.0.0.1:6333/collections | head -c 200; echo; echo ---LOGS---; journalctl -u leadgen --since '3 minutes ago' --no-pager | grep -iE 'MCP|qdrant|agents|backend|error' | tail -6" >> p12d.log 2>&1
echo VERIFY_EXIT_%ERRORLEVEL% >> p12d.log
echo P12D_DONE
