@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del pro_test.log 2>nul
%SCP% -i %KEY% -o BatchMode=yes scripts\pro_test.py root@72.61.245.204:/opt/leadgen/scripts/pro_test.py > pro_test.log 2>&1
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && timeout 60 env PYTHONPATH=/opt/leadgen .venv/bin/python scripts/pro_test.py 2>&1 | grep -aE 'USER:|BOT :'" >> pro_test.log 2>&1
echo PT_EXIT_%ERRORLEVEL% >> pro_test.log
echo PT_DONE
