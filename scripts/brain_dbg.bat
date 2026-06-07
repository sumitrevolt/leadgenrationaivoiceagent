@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del brain_dbg.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && timeout 40 env PYTHONPATH=/opt/leadgen .venv/bin/python scripts/brain_test.py 2>&1 | grep -aiE 'PROVIDER|REPLY|free_ai|error|fail|cerebras|xai|exception' | tail -15" > brain_dbg.log 2>&1
echo BD_EXIT_%ERRORLEVEL% >> brain_dbg.log
echo BD_DONE
