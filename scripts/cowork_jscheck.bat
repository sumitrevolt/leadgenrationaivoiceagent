@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_jscheck.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes root@72.61.245.204
echo === ensure node === > %LOG%
call %SSH% "which node >/dev/null 2>&1 || (apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y nodejs >/dev/null 2>&1); node --version" >> %LOG% 2>&1
echo === JS syntax check on REAL deployed marketing.html === >> %LOG%
call %SSH% "cd /opt/leadgen && python3 scripts/check_marketing_js.py" >> %LOG% 2>&1
echo === DONE === >> %LOG%
