@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del g2.log 2>nul
.venv\Scripts\python.exe -c "from app.main import app; from app.marketing.content_pack import build_client_pack; print('IMPORTS OK')" > g2.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> g2.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> g2.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> g2.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main >> g2.log 2>&1
call "%GIT%" reset --soft origin/main >> g2.log 2>&1
call "%GIT%" add -A >> g2.log 2>&1
call "%GIT%" commit -m "feat(godmode-2): PUBLIC free GBP audit funnel (/audit — lead magnet, teaser+inquiry CTA), legal pages (privacy/terms/refund), robots+sitemap SEO, 1-click client content-pack (monthly deliverable HTML, 18th tab), data retention (events>60d, transcripts>90d in Kavya ops)" >> g2.log 2>&1
call "%GIT%" push origin main >> g2.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> g2.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 14 && systemctl is-active leadgen && for p in /audit /privacy /robots.txt /sitemap.xml; do curl -s -m 8 -o /dev/null -w \"$p: %%{http_code}\n\" http://127.0.0.1:8000$p; done && curl -s -m 8 http://127.0.0.1:8000/api/public/audit/questions | head -c 60; echo; timeout 90 env PYTHONPATH=/opt/leadgen .venv/bin/python scripts/g2_smoke.py 2>&1 | grep -aE 'AUDIT-LOGIC|PACK:|OPS:'" >> g2.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> g2.log
echo G2_DONE
