@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del em.log 2>nul
.venv\Scripts\python.exe -c "from app.main import app; from app.platform import auto_outreach; s,t,h=auto_outreach._email_subject_body({'business_name':'Test Cafe','niche':'restaurant_cafe','city':'Pune','rating':3.9,'reviews_count':12}); print('SUBJ_OK', bool(s) and 'Test Cafe' in s); print('UNSUB_OK', 'REMOVE' in t.upper())" > em.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> em.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> em.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> em.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main >> em.log 2>&1
call "%GIT%" reset --soft origin/main >> em.log 2>&1
call "%GIT%" add -A >> em.log 2>&1
call "%GIT%" commit -m "feat(auto-outreach): system khud emails prospects — auto_outreach.py (personalized cold email + unsubscribe, daily cap 25, 2-4s throttle, emailed_at no-repeat), prospector email capture (website scrape), daily 10:30 IST job, API run/stats. AUTO_EMAIL_OUTREACH + SMTP gated" >> em.log 2>&1
call "%GIT%" push origin main >> em.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> em.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 12 && systemctl is-active leadgen && timeout 30 env PYTHONPATH=/opt/leadgen .venv/bin/python -c \"import asyncio; from app.platform import auto_outreach; print('RUN(off):', asyncio.run(auto_outreach.run_email_outreach())); print('STATS:', auto_outreach.outreach_stats())\" 2>&1 | grep -aE 'RUN|STATS'" >> em.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> em.log
echo EM_DONE
