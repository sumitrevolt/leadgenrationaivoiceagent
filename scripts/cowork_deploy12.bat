@echo off
REM AI image generation (Pollinations) + marketing endpoint. Log -> cowork_deploy12.log
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_deploy12.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === py_compile === > %LOG%
call python -m py_compile app\marketing\ai_image.py app\api\marketing.py >> %LOG% 2>&1
echo EXIT_PYCOMPILE=%errorlevel% >> %LOG%
echo === git add/commit/push === >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(marketing): AI image generation (Pollinations free Flux) + /api/marketing/ai-image (Predis-style)" >> %LOG% 2>&1
echo EXIT_COMMIT=%errorlevel% >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >> %LOG% 2>&1
echo EXIT_PUSH=%errorlevel% >> %LOG%
echo === VPS pull + restart === >> %LOG%
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && systemctl restart leadgen" >> %LOG% 2>&1
echo EXIT_PULL=%errorlevel% >> %LOG%
ping -n 8 127.0.0.1 >nul
call %SSH% "cd /opt/leadgen && git log --oneline -1" >> %LOG% 2>&1
call %SSH% "systemctl is-active leadgen" >> %LOG% 2>&1
call %SSH% "curl -s http://127.0.0.1:8000/health" >> %LOG% 2>&1
echo. >> %LOG%
echo === QA: prod_check (validates marketing router + new endpoint) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python scripts/prod_check.py > /tmp/pc.log 2>&1; echo PRODCHECK_EXIT=$?; tail -6 /tmp/pc.log" >> %LOG% 2>&1
echo === Pollinations reachable? (HEAD) === >> %LOG%
call %SSH% "curl -s -o /dev/null -w 'HTTP_%%{http_code} type=%%{content_type}' 'https://image.pollinations.ai/prompt/test?width=256&height=256&model=flux'" >> %LOG% 2>&1
echo. >> %LOG%
echo === DONE === >> %LOG%
