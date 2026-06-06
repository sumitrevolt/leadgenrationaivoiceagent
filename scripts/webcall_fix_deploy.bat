@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del webcall_fix.log 2>nul

echo === PYTEST === > webcall_fix.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=short >> webcall_fix.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> webcall_fix.log

echo === COMMIT+PUSH === >> webcall_fix.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add app/api/web_call.py app/voice_agent/llm_brain.py scripts/llm_probe.py scripts/vps_llm_probe.bat scripts/webcall_fix_deploy.bat >> webcall_fix.log 2>&1
call "%GIT%" commit -m "fix(web-call): use LLM brain when VoicePipeline has no text method; runtime fallback pipeline->brain; ML init used wrong kwargs (tenant-scoped data dirs)" >> webcall_fix.log 2>&1
echo COMMIT_EXIT_%ERRORLEVEL% >> webcall_fix.log
call "%GIT%" push origin main >> webcall_fix.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> webcall_fix.log

echo === VPS PULL+RESTART === >> webcall_fix.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main && systemctl restart leadgen && sleep 12 && systemctl is-active leadgen && curl -s -m 8 http://127.0.0.1:8000/health && echo && echo ---CONFIG--- && curl -s -m 8 http://127.0.0.1:8000/api/web-call/config" >> webcall_fix.log 2>&1
echo REDEPLOY_EXIT_%ERRORLEVEL% >> webcall_fix.log
echo ALL_DONE
