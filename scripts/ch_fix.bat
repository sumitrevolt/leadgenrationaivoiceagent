@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del chf.log 2>nul
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line > chf.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> chf.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A >> chf.log 2>&1
call "%GIT%" commit -m "fix(tests): self-brand auto-seed flag (AUTO_SEED_SELF) — content tests pure-loop pe monkeypatch off" >> chf.log 2>&1
call "%GIT%" push origin main >> chf.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> chf.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 12 && systemctl is-active leadgen" >> chf.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> chf.log
echo CHF_DONE
