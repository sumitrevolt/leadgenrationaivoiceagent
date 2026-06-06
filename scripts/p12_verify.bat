@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del p12v.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "systemctl is-active leadgen; echo ---AGENTS---; curl -s -m 8 http://127.0.0.1:8000/api/agents/status; echo; echo ---QDRANT---; curl -s -m 5 http://127.0.0.1:6333/collections; echo; echo ---LOGS---; journalctl -u leadgen --since '6 minutes ago' --no-pager | grep -iE 'MCP server|qdrant|backend|agents' | tail -5" > p12v.log 2>&1
echo V_EXIT_%ERRORLEVEL% >> p12v.log
echo V_DONE
