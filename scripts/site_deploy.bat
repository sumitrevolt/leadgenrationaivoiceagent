@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del site.log 2>nul
.venv\Scripts\python.exe -c "from app.main import app; from app.api import public_site; print('IMPORTS OK')" > site.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> site.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> site.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> site.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main >> site.log 2>&1
call "%GIT%" reset --soft origin/main >> site.log 2>&1
call "%GIT%" add -A >> site.log 2>&1
call "%GIT%" commit -m "feat(growth): conversion landing page (hero/demo CTA/GBP hook/8 niches) + public inquiry API (honeypot, rate-limit, jsonl-first + DB lead, rohan event) + self-marketing kit (WhatsApp pitches, follow-ups, social posts, 7-day plan, demo script)" >> site.log 2>&1
echo COMMIT_EXIT_%ERRORLEVEL% >> site.log
call "%GIT%" push origin main >> site.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> site.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && git log -1 --oneline && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 14 && systemctl is-active leadgen && curl -s -m 8 -o /dev/null -w 'root: %%{http_code}\n' http://127.0.0.1:8000/ && curl -s -m 8 -X POST http://127.0.0.1:8000/api/public/inquiry -H 'Content-Type: application/json' -d '{\"name\":\"Smoke Test\",\"business_name\":\"Test Traders\",\"phone\":\"9876543210\",\"niche\":\"solar_residential\",\"city\":\"Pune\"}' | head -c 200; echo; tail -1 data/inquiries.jsonl | head -c 150" >> site.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> site.log
echo SITE_DONE
