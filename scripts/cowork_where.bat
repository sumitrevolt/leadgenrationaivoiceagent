@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_where.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >nul 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "chore: uvicorn-import diagnostic + git tree check" >nul 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >nul 2>&1
echo === git tree state === > %LOG%
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && git rev-parse --short HEAD; echo CACHE:; ls -ld app/cache.py app/cache 2>&1; echo UNTRACKED:; git status --porcelain --untracked-files=normal" >> %LOG% 2>&1
echo === uvicorn-style import (no PYTHONPATH) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python scripts/where2.py 2>&1 | tail -8" >> %LOG% 2>&1
echo === DONE === >> %LOG%
