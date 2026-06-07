@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del gap.log 2>nul
.venv\Scripts\python.exe -c "from app.main import app; from app.agents.staff import run_digest; print('IMPORTS OK')" > gap.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> gap.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> gap.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> gap.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main >> gap.log 2>&1
call "%GIT%" reset --soft origin/main >> gap.log 2>&1
call "%GIT%" add -A >> gap.log 2>&1
call "%GIT%" commit -m "fix(prod-gaps): VPS daily backup script+cron, inquiry email notify (NOTIFY_EMAIL/SMTP gated), daily 08:30 digest job (manager), UPI pay modal on landing (UPI_VPA gated, public /pay-info), package field in inquiry, customer dashboard real KPI binding" >> gap.log 2>&1
call "%GIT%" push origin main >> gap.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> gap.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && find app -name '*.pyc' -delete 2>/dev/null; cp scripts/vps_backup.sh /root/vps_backup.sh && chmod +x /root/vps_backup.sh && (crontab -l 2>/dev/null | grep -v vps_backup; echo '30 22 * * * /root/vps_backup.sh >> /root/backup.log 2>&1') | crontab - && /root/vps_backup.sh && systemctl restart leadgen && sleep 14 && systemctl is-active leadgen && curl -s -m 8 http://127.0.0.1:8000/api/public/pay-info | head -c 80; echo; curl -s -m 8 -o /dev/null -w 'root: %%{http_code}\n' http://127.0.0.1:8000/ && timeout 40 env PYTHONPATH=/opt/leadgen .venv/bin/python -c \"import asyncio; from app.agents.staff import run_digest; r=asyncio.run(run_digest()); print('DIGEST:', str(r)[:160])\"" >> gap.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> gap.log
echo GAP_DONE
