@echo off
REM Scheduler UI tab deploy + verify (JS node --check). Log -> cowork_ui.log
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_ui.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === git add/commit/push === > %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(ui): Scheduler tab — content schedule (add/list/run) + 1-click festival auto-schedule (27th tab, additive)" >> %LOG% 2>&1
echo EXIT_COMMIT=%errorlevel% >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >> %LOG% 2>&1
echo EXIT_PUSH=%errorlevel% >> %LOG%
echo === VPS pull + restart === >> %LOG%
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && systemctl restart leadgen" >> %LOG% 2>&1
ping -n 8 127.0.0.1 >nul
call %SSH% "cd /opt/leadgen && git log --oneline -1" >> %LOG% 2>&1
call %SSH% "systemctl is-active leadgen" >> %LOG% 2>&1
call %SSH% "curl -s http://127.0.0.1:8000/health" >> %LOG% 2>&1
echo. >> %LOG%
echo === JS node --check (inline marketing.html JS — MUST pass) === >> %LOG%
call %SSH% "cd /opt/leadgen && python3 scripts/check_marketing_js.py" >> %LOG% 2>&1
echo === QA prod_check === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python scripts/prod_check.py > /tmp/pc.log 2>&1; echo PRODCHECK_EXIT=$?; tail -2 /tmp/pc.log" >> %LOG% 2>&1
echo === VERIFY page serves Scheduler tab === >> %LOG%
call %SSH% "echo -n 'tab_button='; grep -c 'data-tab=.scheduler.' /opt/leadgen/frontend/marketing.html; echo -n 'pane='; grep -c 'id=.pane-scheduler.' /opt/leadgen/frontend/marketing.html; echo -n 'js_loadScheduler='; grep -c 'function loadScheduler' /opt/leadgen/frontend/marketing.html; echo -n 'paneIds_has='; grep -c 'logo.,.scheduler' /opt/leadgen/frontend/marketing.html" >> %LOG% 2>&1
echo === DONE === >> %LOG%
