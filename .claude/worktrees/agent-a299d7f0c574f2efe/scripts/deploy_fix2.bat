@echo off
setlocal
cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent

echo === Git commit + push ===
"C:\PROGRA~1\Git\cmd\git.exe" add app/api/admin_ops.py
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "fix: activation_summary_public + vobiz JS compat + UPI pending queue"
"C:\PROGRA~1\Git\cmd\git.exe" push origin main
if %ERRORLEVEL% NEQ 0 (echo GIT PUSH FAILED & exit /b 1)

echo === VPS pull + rebuild + verify ===
"C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o StrictHostKeyChecking=no root@72.61.245.204 "cd /opt/leadgen && git pull origin main && docker compose -f docker-compose.vps.yml build app 2>&1 | tail -8 && docker compose -f docker-compose.vps.yml up -d --no-deps app && sleep 20 && python3 scripts/verify_godmode.py"
if %ERRORLEVEL% NEQ 0 (echo VPS FAILED & exit /b 1)

echo === DONE ===
