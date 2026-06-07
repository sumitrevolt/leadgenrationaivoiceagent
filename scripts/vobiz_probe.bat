@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del vobiz_acct.log 2>nul
%SCP% -i %KEY% -o BatchMode=yes scripts\vobiz_account_probe.py root@72.61.245.204:/opt/leadgen/scripts/vobiz_account_probe.py > vobiz_acct.log 2>&1
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && timeout 60 .venv/bin/python scripts/vobiz_account_probe.py 2>&1 | tail -10" >> vobiz_acct.log 2>&1
echo VA_EXIT_%ERRORLEVEL% >> vobiz_acct.log
echo VA_DONE
