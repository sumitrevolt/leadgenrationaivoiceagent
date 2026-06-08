@echo off
REM P7 analytics dashboard (frontend over existing endpoints). Push, node-check JS, restart, smoke.
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_p7.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === py_compile === > %LOG%
call python -m py_compile app\main.py scripts\check_html_js.py >> %LOG% 2>&1
echo EXIT_PYCOMPILE=%errorlevel% >> %LOG%
echo === git add/commit/push === >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(P7): analytics dashboard /app/analytics (Chart.js funnel/call/lead/revenue over existing /api/admin/live-stats + /api/analytics/*) + html-js checker" >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >> %LOG% 2>&1
echo EXIT_PUSH=%errorlevel% >> %LOG%
echo === VPS pull === >> %LOG%
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && git log --oneline -1" >> %LOG% 2>&1
echo === node --check inline JS (analytics + login) === >> %LOG%
call %SSH% "cd /opt/leadgen && python3 scripts/check_html_js.py frontend/analytics.html; python3 scripts/check_html_js.py frontend/login.html" >> %LOG% 2>&1
echo === restart + smoke === >> %LOG%
call %SSH% "systemctl restart leadgen" >> %LOG% 2>&1
ping -n 9 127.0.0.1 >nul
call %SSH% "systemctl is-active leadgen" >> %LOG% 2>&1
call %SSH% "echo -n 'health='; curl -s -o /dev/null -w '%%{http_code}' http://127.0.0.1:8000/health; echo -n ' analytics='; curl -s -o /dev/null -w '%%{http_code}' http://127.0.0.1:8000/app/analytics; echo -n ' login='; curl -s -o /dev/null -w '%%{http_code}' http://127.0.0.1:8000/app/login; echo" >> %LOG% 2>&1
echo === DONE === >> %LOG%
