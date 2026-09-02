@echo off
setlocal
set LOG=%~dp0_canary_run.log
echo CANARY START %DATE% %TIME% > "%LOG%"

:WAIT_LOOP
for /f "tokens=*" %%t in ('wsl bash -lc "ssh -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no root@72.61.245.204 TZ=Asia/Kolkata date +%%H"') do set H=%%t
echo IST hour=%H% >> "%LOG%"
if %H% LSS 9 (
  echo waiting for 9am IST >> "%LOG%"
  ping -n 61 127.0.0.1 >nul
  goto WAIT_LOOP
)

echo PLACING CALL >> "%LOG%"
wsl bash -lc "scp -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no /mnt/c/Users/Ratanshila/Documents/leadgenrationaiagent/scripts/_canary_place_call.py root@72.61.245.204:/tmp/_canary_place_call.py && ssh -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no root@72.61.245.204 '/usr/bin/docker cp /tmp/_canary_place_call.py leadgen_app:/tmp/_canary_place_call.py && /usr/bin/docker exec leadgen_app python /tmp/_canary_place_call.py'" >> "%LOG%" 2>&1

echo WAIT 300s >> "%LOG%"
ping -n 301 127.0.0.1 >nul

echo ANALYZE >> "%LOG%"
wsl bash -lc "scp -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no /mnt/c/Users/Ratanshila/Documents/leadgenrationaiagent/scripts/_canary_analyze.py root@72.61.245.204:/tmp/_canary_analyze.py && ssh -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no root@72.61.245.204 'python3 /tmp/_canary_analyze.py'" >> "%LOG%" 2>&1

echo LOGS >> "%LOG%"
wsl bash -lc "ssh -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no root@72.61.245.204 '/usr/bin/docker logs leadgen_app --since 15m 2>&1 | grep -iE omniroute | tail -30'" >> "%LOG%" 2>&1

echo RECORDINGS >> "%LOG%"
wsl bash -lc "ssh -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no root@72.61.245.204 'ls -lt /opt/leadgen/data/call_recordings 2>/dev/null | head -5; ls -lt /opt/leadgen/data/recordings 2>/dev/null | head -5'" >> "%LOG%" 2>&1

echo TURN_METRICS_TAIL >> "%LOG%"
wsl bash -lc "ssh -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no root@72.61.245.204 'tail -5 /opt/leadgen/data/turn_metrics/2026-07-18.jsonl 2>/dev/null'" >> "%LOG%" 2>&1

echo DONE >> "%LOG%"
type "%LOG%"
