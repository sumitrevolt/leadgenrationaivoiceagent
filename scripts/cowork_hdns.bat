@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_hdns.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes root@72.61.245.204
echo === py_compile + push === > %LOG%
call python -m py_compile scripts\hostinger_dns.py >> %LOG% 2>&1
echo EXIT_PYCOMPILE=%errorlevel% >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "tool: hostinger_dns.py DNS API helper + DMARC reporting (rua)" >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >> %LOG% 2>&1
echo EXIT_PUSH=%errorlevel% >> %LOG%
echo === VPS pull === >> %LOG%
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q" >> %LOG% 2>&1
echo === API GET (read-only) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python scripts/hostinger_dns.py get" >> %LOG% 2>&1
echo === API VALIDATE (no change) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python scripts/hostinger_dns.py validate" >> %LOG% 2>&1
echo === DONE === >> %LOG%
