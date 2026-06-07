@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del first_call.log 2>nul
%SCP% -i %KEY% -o BatchMode=yes scripts\first_call.py root@72.61.245.204:/opt/leadgen/scripts/first_call.py > first_call.log 2>&1
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && timeout 60 .venv/bin/python scripts/first_call.py 2>&1 | grep -vE '\"timestamp\"' | tail -8" >> first_call.log 2>&1
echo FC_EXIT_%ERRORLEVEL% >> first_call.log
echo FC_DONE
