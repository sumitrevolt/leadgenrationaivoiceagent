@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del vps_llm.log 2>nul
%SCP% -i %KEY% -o BatchMode=yes scripts\llm_probe.py root@72.61.245.204:/tmp/llm_probe.py > vps_llm.log 2>&1
echo SCP_EXIT_%ERRORLEVEL% >> vps_llm.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && timeout 90 env PYTHONPATH=/opt/leadgen .venv/bin/python /tmp/llm_probe.py 2>&1 | tail -60" >> vps_llm.log 2>&1
echo PROBE_EXIT_%ERRORLEVEL% >> vps_llm.log
echo PROBE_DONE
