@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del brain.log 2>nul
%SCP% -i %KEY% -o BatchMode=yes scripts\brain_test.py root@72.61.245.204:/opt/leadgen/scripts/brain_test.py > brain.log 2>&1
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && grep -q '^XAI_API_KEY=' .env && echo XAI_KEY_SET || echo XAI_KEY_MISSING; find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 12 && timeout 40 env PYTHONPATH=/opt/leadgen .venv/bin/python scripts/brain_test.py 2>&1 | grep -aE 'PROVIDERS|PROVIDER_USED|REPLY'" >> brain.log 2>&1
echo BT_EXIT_%ERRORLEVEL% >> brain.log
echo BRAIN_DONE
