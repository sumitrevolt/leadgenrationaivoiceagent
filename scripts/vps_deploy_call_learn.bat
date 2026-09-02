@echo off
setlocal
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set HOST=root@72.61.245.204
set LOG=%~dp0vps_deploy_call_learn.log
set ROOT=c:\Users\Ratanshila\Documents\leadgenrationaiagent

echo [%date% %time%] deploy+call+learn > "%LOG%"

cd /d "%ROOT%"
python scripts\prod_check.py >> "%LOG%" 2>&1
if errorlevel 1 (
  echo prod_check FAIL >> "%LOG%"
  type "%LOG%"
  exit /b 1
)

"%GIT%" add app/utils/dnd_checker.py app/platform/setup_status.py scripts/voice_learn_from_calls.py scripts/vobiz_go_live.py scripts/vps_deploy_call_learn.py >> "%LOG%" 2>&1
"%GIT%" commit -m "feat(voice): DND carrier scrub + live call learn loop" >> "%LOG%" 2>&1
"%GIT%" push origin main >> "%LOG%" 2>&1
if errorlevel 1 (
  echo push FAIL >> "%LOG%"
  type "%LOG%"
  exit /b 1
)

"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "set -o pipefail; cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && docker compose -f docker-compose.vps.yml build app && docker compose -f docker-compose.vps.yml up -d --no-deps app worker && sleep 22 && curl -sf http://127.0.0.1:8000/health" >> "%LOG%" 2>&1
if errorlevel 1 goto fail

REM NOTE: DND_FAIL_OPEN=1 removed (TC-002) — it turns the TRAI DND gate fail-OPEN; never set in prod.
"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "cd /opt/leadgen && python3 scripts/env_set.py VOBIZ_CALL_RECORD=1 AUTO_QUALIFY_CALLS=1 DND_CARRIER_SCRUB=1 && docker compose -f docker-compose.vps.yml up -d --no-deps --force-recreate app worker && sleep 20" >> "%LOG%" 2>&1

"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "docker exec leadgen_app python3 scripts/voice_learn_from_calls.py --call-limit 1 --platform --wait 180 --limit 2" >> "%LOG%" 2>&1

echo DONE >> "%LOG%"
type "%LOG%"
exit /b 0

:fail
echo FAIL >> "%LOG%"
type "%LOG%"
exit /b 1
