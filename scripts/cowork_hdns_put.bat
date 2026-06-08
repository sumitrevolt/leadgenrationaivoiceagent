@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_hdns_put.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes root@72.61.245.204
echo === API PUT (apply DMARC rua; overwrite=false -> only _dmarc) === > %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python scripts/hostinger_dns.py put" >> %LOG% 2>&1
echo === API GET (confirm _dmarc updated, SPF/DKIM/MX intact) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python scripts/hostinger_dns.py get" >> %LOG% 2>&1
echo === DONE === >> %LOG%
