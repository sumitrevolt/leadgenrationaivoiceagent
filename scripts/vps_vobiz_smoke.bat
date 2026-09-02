@echo off
setlocal
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set HOST=root@72.61.245.204
set LOG=%~dp0vps_vobiz_smoke.log

echo smoke start > "%LOG%"

"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "docker exec leadgen_app python3 scripts/vobiz_account_probe.py" >> "%LOG%" 2>&1

"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "docker exec leadgen_app python3 scripts/fire_calls.py --limit 3 --dry-run --platform" >> "%LOG%" 2>&1

"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "curl -s http://127.0.0.1:8000/api/webhooks/health" >> "%LOG%" 2>&1

echo done >> "%LOG%"
type "%LOG%"
