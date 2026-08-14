@echo off
setlocal
echo === LeadGen AI Deploy ===

cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent

echo [1/3] Git add + commit + push...
C:\PROGRA~1\Git\cmd\git.exe add app/telephony/vobiz_stream.py
C:\PROGRA~1\Git\cmd\git.exe commit -m "fix: vobiz bidirectional recording - outbound TTS frames wired"
C:\PROGRA~1\Git\cmd\git.exe push origin main
if errorlevel 1 (
    echo Push failed - check git status
    pause
    exit /b 1
)
echo [1/3] DONE - pushed to GitHub

echo [2/3] VPS: docker build + deploy...
C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa -o StrictHostKeyChecking=no root@72.61.245.204 "cd /opt/leadgen && git pull origin main && docker compose -f docker-compose.vps.yml build app 2>&1 | tail -5 && docker compose -f docker-compose.vps.yml up -d --no-deps app && echo BUILD_DEPLOY_OK"
if errorlevel 1 (
    echo VPS deploy failed
    pause
    exit /b 1
)

echo [3/3] Health check (wait 18s)...
ping -n 19 127.0.0.1 > nul
C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa -o StrictHostKeyChecking=no root@72.61.245.204 "curl -s https://leadsgenai.in/health | python3 -c \"import sys,json; d=json.load(sys.stdin); print('HEALTH:', d.get('environment'), d.get('status'))\""

echo === Deploy complete ===
