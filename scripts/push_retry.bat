@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del pr.log 2>nul
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" pull --rebase origin main > pr.log 2>&1
call "%GIT%" push origin main >> pr.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> pr.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 12 && systemctl is-active leadgen && env PYTHONPATH=/opt/leadgen .venv/bin/python -c 'import app.voice_agent.free_ai as f; print(f.describe())'" >> pr.log 2>&1
echo PR_EXIT_%ERRORLEVEL% >> pr.log
echo PR_DONE
