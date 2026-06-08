@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_workercheck.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === clean restart === > %LOG%
call %SSH% "systemctl restart leadgen" >> %LOG% 2>&1
ping -n 11 127.0.0.1 >nul
call %SSH% "systemctl is-active leadgen" >> %LOG% 2>&1
echo === /app/login x6 (worker consistency) === >> %LOG%
call %SSH% "curl -s -o /dev/null -w '%%{http_code} ' http://127.0.0.1:8000/app/login" >> %LOG% 2>&1
call %SSH% "curl -s -o /dev/null -w '%%{http_code} ' http://127.0.0.1:8000/app/login" >> %LOG% 2>&1
call %SSH% "curl -s -o /dev/null -w '%%{http_code} ' http://127.0.0.1:8000/app/login" >> %LOG% 2>&1
call %SSH% "curl -s -o /dev/null -w '%%{http_code} ' http://127.0.0.1:8000/app/login" >> %LOG% 2>&1
call %SSH% "curl -s -o /dev/null -w '%%{http_code} ' http://127.0.0.1:8000/app/login" >> %LOG% 2>&1
call %SSH% "curl -s -o /dev/null -w '%%{http_code} ' http://127.0.0.1:8000/app/analytics" >> %LOG% 2>&1
echo. >> %LOG%
echo === DONE === >> %LOG%
