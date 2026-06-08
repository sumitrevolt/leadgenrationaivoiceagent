@echo off
REM Embeddable lead-capture widget deploy + verify. Log -> cowork_widget.log
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_widget.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === py_compile === > %LOG%
call python -m py_compile app\main.py app\api\marketing.py app\marketing\embed_widget.py scripts\check_widget.py >> %LOG% 2>&1
echo EXIT_PYCOMPILE=%errorlevel% >> %LOG%
echo === git add/commit/push === >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(leadgen): embeddable website lead-capture widget (Growth-tier) — /b/{slug}/embed + widget.js + admin snippet + console tab" >> %LOG% 2>&1
echo EXIT_COMMIT=%errorlevel% >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >> %LOG% 2>&1
echo EXIT_PUSH=%errorlevel% >> %LOG%
echo === VPS pull + restart === >> %LOG%
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && systemctl restart leadgen" >> %LOG% 2>&1
ping -n 9 127.0.0.1 >nul
call %SSH% "cd /opt/leadgen && git log --oneline -1" >> %LOG% 2>&1
call %SSH% "systemctl is-active leadgen" >> %LOG% 2>&1
call %SSH% "curl -s http://127.0.0.1:8000/health" >> %LOG% 2>&1
echo. >> %LOG%
echo === JS node --check (marketing.html) === >> %LOG%
call %SSH% "cd /opt/leadgen && python3 scripts/check_marketing_js.py" >> %LOG% 2>&1
echo === QA prod_check === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python scripts/prod_check.py > /tmp/pc.log 2>&1; echo PRODCHECK_EXIT=$?; tail -2 /tmp/pc.log" >> %LOG% 2>&1
echo === VERIFY widget (funcs + live routes) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python scripts/check_widget.py" >> %LOG% 2>&1
echo === VERIFY console tab present === >> %LOG%
call %SSH% "echo -n 'tab='; grep -c 'data-tab=.widget.' /opt/leadgen/frontend/marketing.html; echo -n 'pane='; grep -c 'id=.pane-widget.' /opt/leadgen/frontend/marketing.html" >> %LOG% 2>&1
echo === DONE === >> %LOG%
