@echo off
setlocal
cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent

echo === [1] Check secrets ===
python scripts\check_secrets.py
if %ERRORLEVEL% NEQ 0 (echo SECRETS CHECK FAILED & exit /b 1)

echo === [2] Git add + commit + push ===
"C:\PROGRA~1\Git\cmd\git.exe" add frontend/admin_dashboard.html app/api/admin_ops.py app/main.py
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat: God Mode + Campaign Launcher in admin dashboard (JS complete)"
"C:\PROGRA~1\Git\cmd\git.exe" push origin main
if %ERRORLEVEL% NEQ 0 (echo GIT PUSH FAILED & exit /b 1)

echo === [3] VPS pull + build + deploy ===
"C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o StrictHostKeyChecking=no root@72.61.245.204 "cd /opt/leadgen && git pull origin main && docker compose -f docker-compose.vps.yml build app 2>&1 | tail -20 && docker compose -f docker-compose.vps.yml up -d --no-deps app && sleep 18 && curl -sf http://localhost:8000/health | python3 -c \"import sys,json; d=json.load(sys.stdin); print('ENV:', d.get('environment','?')); print('OK' if d.get('environment')=='production' else 'WARN: not production')\""
if %ERRORLEVEL% NEQ 0 (echo VPS DEPLOY FAILED & exit /b 1)

echo === DONE ===
