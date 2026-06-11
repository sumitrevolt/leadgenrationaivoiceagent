@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
%SSH% -i C:\Users\Ratanshila\.ssh\id_rsa -o StrictHostKeyChecking=no root@72.61.245.204 "cd /opt/leadgen; git pull --ff-only; docker compose -f docker-compose.vps.yml build app; echo BUILD_DONE; docker compose -f docker-compose.vps.yml --profile celery up -d; sleep 16; echo HEALTH1:; curl -s http://127.0.0.1:8000/health; echo; sleep 6; echo HEALTH2:; curl -s http://127.0.0.1:8000/health; echo; echo CONSENT_ROUTES:; curl -s http://127.0.0.1:8000/openapi.json | grep -c voiceai/consent" > deploy_consent.log 2>&1
echo SSH_EXIT_%ERRORLEVEL% >> deploy_consent.log
echo DONE
