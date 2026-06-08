@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_diag.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === setup_status === > %LOG%
call %SSH% "cd /opt/leadgen && PYTHONPATH=. .venv/bin/python scripts/setup_status.py 2>&1 | tail -30" >> %LOG% 2>&1
echo === ruff (errors only, top 30) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/ruff check app --select F,E9 --output-format concise 2>&1 | tail -30" >> %LOG% 2>&1
echo === full pytest (asyncio auto) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python -m pytest -q -o asyncio_mode=auto 2>&1 | tail -18" >> %LOG% 2>&1
echo === DONE === >> %LOG%
