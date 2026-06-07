@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del cbm.log 2>nul
%SCP% -i %KEY% -o BatchMode=yes scripts\cb_models.py root@72.61.245.204:/opt/leadgen/scripts/cb_models.py > cbm.log 2>&1
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && env PYTHONPATH=/opt/leadgen .venv/bin/python scripts/cb_models.py 2>&1 | grep -aE 'STATUS|MODEL:|DEPLOYED'" >> cbm.log 2>&1
echo CBM_EXIT_%ERRORLEVEL% >> cbm.log
echo CBM_DONE
