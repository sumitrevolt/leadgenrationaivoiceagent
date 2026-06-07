@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del cbf.log 2>nul
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add app/voice_agent/free_ai.py scripts/cb_final.bat scripts/cb_models.py > cbf.log 2>&1
call "%GIT%" commit -m "fix(free-ai): Cerebras model gpt-oss-120b (account-available; llama not provisioned)" >> cbf.log 2>&1
call "%GIT%" push origin main >> cbf.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> cbf.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 12 && timeout 40 env PYTHONPATH=/opt/leadgen .venv/bin/python scripts/brain_test.py 2>&1 | grep -aE 'PROVIDER_USED|REPLY'" >> cbf.log 2>&1
echo CBF_EXIT_%ERRORLEVEL% >> cbf.log
echo CBF_DONE
