@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del vobiz_prov.log 2>nul
%SCP% -i %KEY% -o BatchMode=yes scripts\vobiz_provision.py root@72.61.245.204:/opt/leadgen/scripts/vobiz_provision.py > vobiz_prov.log 2>&1
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && timeout 90 .venv/bin/python scripts/vobiz_provision.py" >> vobiz_prov.log 2>&1
echo VP_EXIT_%ERRORLEVEL% >> vobiz_prov.log
echo VP_DONE
