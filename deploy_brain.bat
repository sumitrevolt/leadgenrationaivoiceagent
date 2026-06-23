@echo off
REM Deploy Obsidian second brain + KB cold-start fix to VPS
REM Run: deploy_brain.bat

echo [deploy_brain] Pushing to GitHub...
"C:\Program Files\Git\cmd\git.exe" push origin main
if errorlevel 1 (echo [FAIL] git push failed & pause & exit /b 1)
echo [deploy_brain] Push OK.

echo [deploy_brain] Connecting to VPS...
set SSH="C:\Program Files\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204

REM Pull + build + restart app
%SSH% "cd /opt/leadgen && git pull origin main && docker compose -f docker-compose.vps.yml build app 2>&1 | tail -5 && docker compose -f docker-compose.vps.yml up -d --no-deps app"
if errorlevel 1 (echo [FAIL] VPS deploy failed & pause & exit /b 1)

echo [deploy_brain] Waiting 20s for app to start...
ping -n 21 127.0.0.1 > nul

REM Health check
%SSH% "curl -sf https://leadsgenai.in/health | python3 -c \"import sys,json; d=json.load(sys.stdin); print('[OK] env=' + d.get('environment','?'))\" 2>/dev/null || echo '[WARN] health endpoint not JSON'"

echo.
echo [deploy_brain] === OBSIDIAN SETUP (one-time, if not done yet) ===
echo.
echo 1. Create GitHub repo: https://github.com/new  (name: leadsgenai-brain, private)
echo 2. On VPS run:
echo    bash scripts/setup_obsidian_vault.sh git@github.com:sumitrevolt/leadsgenai-brain.git
echo 3. Add to VPS .env:
echo    OBSIDIAN_SYNC=1
echo    OBSIDIAN_GIT_REMOTE=git@github.com:sumitrevolt/leadsgenai-brain.git
echo    VOBIZ_AUDIO_TRACK=both
echo 4. Restart app:  docker compose -f docker-compose.vps.yml up -d --no-deps app
echo 5. Backfill:     OBSIDIAN_SYNC=1 python scripts/backfill_obsidian.py
echo 6. On Windows:   git clone git@github.com:sumitrevolt/leadsgenai-brain.git [obsidian-vault-path]
echo 7. Install Obsidian Git plugin, auto-pull 30min.
echo.
echo [deploy_brain] Done.
pause
