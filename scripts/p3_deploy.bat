@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del p3d.log 2>nul

echo === PYTEST === > p3d.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> p3d.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> p3d.log

echo === COMMIT+PUSH === >> p3d.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A >> p3d.log 2>&1
call "%GIT%" commit -m "feat(P3): Vobiz Call API integration (test-call + answer XML webhook) + FreeSWITCH docker stack (Vobiz gateway, ESL, dialplan) + pipecat pipeline skeleton + fs_deploy in VPS script" >> p3d.log 2>&1
call "%GIT%" push origin main >> p3d.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> p3d.log

echo === VPS DEPLOY === >> p3d.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && bash scripts/fs_deploy.sh 2>&1 | tail -8 ; systemctl restart leadgen && sleep 12 && systemctl is-active leadgen" >> p3d.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> p3d.log

echo === VERIFY === >> p3d.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "curl -s -m 8 -o /dev/null -w 'answer-xml: %%{http_code} %%{content_type}\n' http://127.0.0.1:8000/api/telephony/vobiz/answer/testtoken ; curl -s -m 8 http://127.0.0.1:8000/api/telephony/vobiz/answer/testtoken | head -c 200 ; echo ; docker ps --format '{{.Names}} {{.Status}}' | grep -iE 'freeswitch|qdrant' ; docker exec leadgen-freeswitch fs_cli -x 'sofia status gateway vobiz' 2>/dev/null | grep -iE 'state|status' | head -4 || echo FS_CLI_PENDING" >> p3d.log 2>&1
echo VERIFY_EXIT_%ERRORLEVEL% >> p3d.log
echo P3D_DONE >> p3d.log
echo P3D_DONE
