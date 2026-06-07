@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del mkt2b.log 2>nul
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A > mkt2b.log 2>&1
call "%GIT%" commit -m "fix(marketing): audit fixes key compat (top_fixes) in UI + smoke" >> mkt2b.log 2>&1
call "%GIT%" push origin main >> mkt2b.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> mkt2b.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && git log -1 --oneline && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 14 && systemctl is-active leadgen && curl -s -m 8 -o /dev/null -w 'marketing page: %%{http_code}\n' http://127.0.0.1:8000/app/marketing && timeout 40 env PYTHONPATH=/opt/leadgen .venv/bin/python scripts/mkt2_smoke.py" >> mkt2b.log 2>&1
echo DEPLOY2_EXIT_%ERRORLEVEL% >> mkt2b.log
echo MKT2B_DONE
