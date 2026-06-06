@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del p12s.log 2>nul
%SCP% -i %KEY% -o BatchMode=yes scripts\vps_agents_test.py root@72.61.245.204:/opt/leadgen/scripts/vps_agents_test.py > p12s.log 2>&1
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && .venv/bin/pip uninstall -y -q langchain langchain-openai 2>/dev/null; timeout 120 env PYTHONPATH=/opt/leadgen QDRANT_URL=http://127.0.0.1:6333 .venv/bin/python scripts/vps_agents_test.py 2>&1 | grep -vE '\"timestamp\"' | tail -10" >> p12s.log 2>&1
echo S_EXIT_%ERRORLEVEL% >> p12s.log
echo S_DONE
