@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_hardreload.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === HARD RELOAD (stop + pkill uvicorn + clear pycache + start) === > %LOG%
call %SSH% "systemctl stop leadgen; pkill -9 -f uvicorn; find /opt/leadgen/app -name __pycache__ -type d -prune -exec rm -rf {} +; systemctl start leadgen" >> %LOG% 2>&1
ping -n 12 127.0.0.1 >nul
echo === is-active === >> %LOG%
call %SSH% "systemctl is-active leadgen" >> %LOG% 2>&1
echo === health === >> %LOG%
call %SSH% "curl -s -o /dev/null -w '%%{http_code}' http://127.0.0.1:8000/health" >> %LOG% 2>&1
echo. >> %LOG%
echo === /app/login === >> %LOG%
call %SSH% "curl -s -o /dev/null -w '%%{http_code}' http://127.0.0.1:8000/app/login" >> %LOG% 2>&1
echo. >> %LOG%
echo === /app/analytics === >> %LOG%
call %SSH% "curl -s -o /dev/null -w '%%{http_code}' http://127.0.0.1:8000/app/analytics" >> %LOG% 2>&1
echo. >> %LOG%
echo === /app/customer (control) === >> %LOG%
call %SSH% "curl -s -o /dev/null -w '%%{http_code}' http://127.0.0.1:8000/app/customer" >> %LOG% 2>&1
echo. >> %LOG%
echo === DONE === >> %LOG%
