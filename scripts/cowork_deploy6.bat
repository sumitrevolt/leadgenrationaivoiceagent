@echo off
REM GODMODE deploy: extraction repos + structured content wiring. Log -> cowork_deploy6.log
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_deploy6.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === py_compile (Windows = source of truth) === > %LOG%
call python -m py_compile app\llm\structured.py app\marketing\post_generator.py app\lead_scraper\to_markdown.py app\lead_scraper\deep_extract.py >> %LOG% 2>&1
echo EXIT_PYCOMPILE=%errorlevel% >> %LOG%
echo === git add/commit/push === >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(godmode): MarkItDown + Crawl4AI web-extraction modules + structured content wiring (opt-in, defensive)" >> %LOG% 2>&1
echo EXIT_COMMIT=%errorlevel% >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >> %LOG% 2>&1
echo EXIT_PUSH=%errorlevel% >> %LOG%
echo === VPS pull + restart (safe code first) === >> %LOG%
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && systemctl restart leadgen" >> %LOG% 2>&1
echo EXIT_PULL=%errorlevel% >> %LOG%
ping -n 8 127.0.0.1 >nul
call %SSH% "cd /opt/leadgen && git log --oneline -1" >> %LOG% 2>&1
call %SSH% "systemctl is-active leadgen" >> %LOG% 2>&1
call %SSH% "curl -s http://127.0.0.1:8000/health" >> %LOG% 2>&1
echo. >> %LOG%
echo === INSTALL markitdown === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/pip install -q markitdown" >> %LOG% 2>&1
echo EXIT_PIP=%errorlevel% >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python -c 'import markitdown'" >> %LOG% 2>&1
echo EXIT_IMPORT=%errorlevel% >> %LOG%
echo === QA: prod_check (imports app incl. post_generator edit) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python scripts/prod_check.py > /tmp/pc.log 2>&1; echo PRODCHECK_EXIT=$?; tail -6 /tmp/pc.log" >> %LOG% 2>&1
echo === HEALTH AGAIN === >> %LOG%
call %SSH% "curl -s http://127.0.0.1:8000/health" >> %LOG% 2>&1
echo. >> %LOG%
echo === DONE === >> %LOG%
