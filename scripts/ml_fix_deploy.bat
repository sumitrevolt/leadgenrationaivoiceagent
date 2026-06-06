@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del ml_fix.log 2>nul

echo === PYTEST === > ml_fix.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=no >> ml_fix.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> ml_fix.log

echo === COMMIT+PUSH === >> ml_fix.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add app/voice_agent/llm_brain.py scripts/ml_fix_deploy.bat scripts/warn_check.bat >> ml_fix.log 2>&1
call "%GIT%" commit -m "fix(ml): align llm_brain with real BrainOptimizer/FeedbackLoop APIs (agent_type/industry args, sync get_best_response)" >> ml_fix.log 2>&1
call "%GIT%" push origin main >> ml_fix.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> ml_fix.log

echo === VPS PULL+RESTART+TEST === >> ml_fix.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && systemctl restart leadgen && sleep 12 && systemctl is-active leadgen && echo ---WS-TEST--- && timeout 60 .venv/bin/python scripts/ws_test.py ; echo ---ML-WARN--- ; journalctl -u leadgen --since '45 seconds ago' --no-pager | grep -iE 'ML optimization failed|llm responder failed' | tail -3 ; echo ---ML-OK--- ; journalctl -u leadgen --since '45 seconds ago' --no-pager | grep -c 'ML-optimized prompt'" >> ml_fix.log 2>&1
echo ML_DEPLOY_EXIT_%ERRORLEVEL% >> ml_fix.log
echo ML_DONE
