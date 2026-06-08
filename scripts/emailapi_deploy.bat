@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del eapi.log 2>nul
.venv\Scripts\python.exe -c "from app.main import app; from app.integrations.email_api import api_available, send_email_api; print('IMPORTS OK; api_available=', api_available())" > eapi.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> eapi.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> eapi.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> eapi.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main >> eapi.log 2>&1
call "%GIT%" reset --soft origin/main >> eapi.log 2>&1
call "%GIT%" add -A >> eapi.log 2>&1
call "%GIT%" commit -m "feat(email-api): API-based email sending (Resend + Brevo, RESEND_API_KEY/BREVO_API_KEY env) — EmailSender API-first then SMTP fallback; auto_outreach gate ab API-key ya SMTP koi bhi pe chalta hai. SMTP-password jhanjhat khatam" >> eapi.log 2>&1
call "%GIT%" push origin main >> eapi.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> eapi.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 12 && systemctl is-active leadgen && timeout 20 env PYTHONPATH=/opt/leadgen .venv/bin/python -c \"from app.integrations.email_api import api_available; print('API_AVAILABLE:', api_available())\"" >> eapi.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> eapi.log
echo EAPI_DONE
