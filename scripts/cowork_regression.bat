@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_regression.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === full pytest (regression) === > %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python -m pytest -q 2>&1 | tail -25" >> %LOG% 2>&1
echo === DONE === >> %LOG%
