@echo off
REM Wire 7 new marketing tabs into marketing.html. Log -> cowork_wire.log
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_wire.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === py_compile checker === > %LOG%
call python -m py_compile scripts\check_marketing_js.py >> %LOG% 2>&1
echo === git add/commit/push === >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(marketing-ui): wire 7 new tabs (ai-image, complete-post, variations, chatbot, sentiment, hashtags, logo)" >> %LOG% 2>&1
echo EXIT_COMMIT=%errorlevel% >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >> %LOG% 2>&1
echo EXIT_PUSH=%errorlevel% >> %LOG%
echo === VPS pull + restart === >> %LOG%
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && systemctl restart leadgen" >> %LOG% 2>&1
ping -n 8 127.0.0.1 >nul
call %SSH% "systemctl is-active leadgen" >> %LOG% 2>&1
call %SSH% "curl -s http://127.0.0.1:8000/health" >> %LOG% 2>&1
echo. >> %LOG%
echo === JS SYNTAX CHECK (node) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python scripts/check_marketing_js.py" >> %LOG% 2>&1
echo === page serves new tabs? (count) === >> %LOG%
call %SSH% "curl -s http://127.0.0.1:8000/app/marketing | grep -c -e pane-chatbot -e pane-aiimage -e pane-complete -e pane-sentiment -e pane-hashtags -e pane-logo -e pane-variations" >> %LOG% 2>&1
echo === DONE === >> %LOG%
