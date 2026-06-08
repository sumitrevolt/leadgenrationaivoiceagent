@echo off
REM Automation+marketing repos deploy. Log -> cowork_deploy3.log
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_deploy3.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === py_compile new modules === > %LOG%
call python -m py_compile app\llm\structured.py app\marketing\seo_tools.py app\lead_scraper\web_extract.py >> %LOG% 2>&1
echo EXIT_PYCOMPILE=%errorlevel% >> %LOG%
echo === git add/commit/push === >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat: structured LLM (instructor) + marketing SEO/ads (advertools) + web extract (trafilatura) - opt-in defensive" >> %LOG% 2>&1
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
echo === INSTALL instructor advertools trafilatura === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/pip install -q instructor advertools trafilatura" >> %LOG% 2>&1
echo EXIT_PIP=%errorlevel% >> %LOG%
echo === IMPORT CHECK === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python -c 'import instructor, advertools, trafilatura'" >> %LOG% 2>&1
echo EXIT_IMPORT=%errorlevel% >> %LOG%
echo === HEALTH AGAIN === >> %LOG%
call %SSH% "curl -s http://127.0.0.1:8000/health" >> %LOG% 2>&1
echo. >> %LOG%
echo === DONE === >> %LOG%
