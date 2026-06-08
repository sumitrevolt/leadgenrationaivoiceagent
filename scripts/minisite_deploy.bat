@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del ms.log 2>nul
.venv\Scripts\python.exe -c "from app.main import app; from app.marketing import mini_site, clients_store; print('IMPORTS OK', hasattr(mini_site,'render_site'), hasattr(clients_store,'get_by_slug'))" > ms.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> ms.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> ms.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> ms.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main >> ms.log 2>&1
call "%GIT%" reset --soft origin/main >> ms.log 2>&1
call "%GIT%" add -A >> ms.log 2>&1
call "%GIT%" commit -m "feat(mini-site): per-client free website + booking page /b/{slug} (brand-colored, call/WhatsApp/enquiry form->inquiry, review QR, sitemap) + client portal Site-dekho link + customer_dashboard real-data (SunVolt sample removed)" >> ms.log 2>&1
call "%GIT%" push origin main >> ms.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> ms.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=25 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && git log -1 --oneline && systemctl stop leadgen; sleep 2; pkill -9 -f uvicorn 2>/dev/null; find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null; sleep 2; systemctl start leadgen && sleep 16 && systemctl is-active leadgen && SLUG=$(env PYTHONPATH=/opt/leadgen .venv/bin/python -c \"from app.marketing import clients_store as c; L=c.list_clients(); print((L[0].get('slug') if L else ''))\" 2>/dev/null) && echo SLUG=$SLUG && curl -s -m 8 -o /dev/null -w 'mini-site /b/%SLUG%: %%{http_code}\n' http://127.0.0.1:8000/b/$SLUG && curl -s -m 8 http://127.0.0.1:8000/b/$SLUG | grep -oiE 'Sharma Solar|wa.me|/api/public/inquiry' | head -3" >> ms.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> ms.log
echo MS_DONE
