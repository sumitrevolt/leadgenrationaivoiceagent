@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_route.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >nul 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "chore: route diagnostic" >nul 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >nul 2>&1
echo === route diagnostic (fresh import + TestClient) === > %LOG%
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && PYTHONPATH=. .venv/bin/python scripts/check_route.py 2>&1 | tail -15" >> %LOG% 2>&1
echo === DONE === >> %LOG%
