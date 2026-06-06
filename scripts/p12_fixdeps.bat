@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del p12f.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && .venv/bin/pip install -q 'langgraph>=1.0' 'langgraph-checkpoint-sqlite>=2.0' 'langchain-core>=0.3' 'fastapi-mcp>=0.3' 'qdrant-client>=1.12.0' 'fastembed>=0.4.0' 2>&1 | tail -3; echo PIP_RC=$?; systemctl restart leadgen && sleep 14 && systemctl is-active leadgen && echo ---AGENTS--- && curl -s -m 8 http://127.0.0.1:8000/api/agents/status && echo && echo ---LOGS--- && journalctl -u leadgen --since '1 minute ago' --no-pager | grep -iE 'MCP server|qdrant|agents engine|backend' | tail -5" > p12f.log 2>&1
echo F_EXIT_%ERRORLEVEL% >> p12f.log
echo F_DONE
