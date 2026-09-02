@echo off
setlocal
cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent

echo === [1] Git commit + push ===
"C:\PROGRA~1\Git\cmd\git.exe" add app/api/admin_ops.py
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "fix: activation import + Vobiz as primary telephony provider"
"C:\PROGRA~1\Git\cmd\git.exe" push origin main
if %ERRORLEVEL% NEQ 0 (echo GIT PUSH FAILED & exit /b 1)

echo === [2] VPS: set TELEPHONY_PROVIDER=vobiz in .env, pull, rebuild ===
"C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o StrictHostKeyChecking=no root@72.61.245.204 "cd /opt/leadgen && grep -q TELEPHONY_PROVIDER .env && sed -i 's/^TELEPHONY_PROVIDER=.*/TELEPHONY_PROVIDER=vobiz/' .env || echo 'TELEPHONY_PROVIDER=vobiz' >> .env && git pull origin main && docker compose -f docker-compose.vps.yml build app 2>&1 | tail -10 && docker compose -f docker-compose.vps.yml up -d --no-deps app && sleep 18 && curl -sf http://localhost:8000/api/admin/system/summary | python3 -c \"import sys,json; d=json.load(sys.stdin); rd=d.get('readiness',{}); print('ready:', rd.get('ready_for_first_paid_customer','?')); print('probes:', len(rd.get('probes',{}))); print('telephony:', d.get('telephony_provider','?')); print('TRAI:', d.get('trai',{}).get('calling_open','?'))\""
if %ERRORLEVEL% NEQ 0 (echo VPS DEPLOY FAILED & exit /b 1)

echo === DONE ===
