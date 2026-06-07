@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del qa.log 2>nul
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main > qa.log 2>&1
call "%GIT%" reset --soft origin/main >> qa.log 2>&1
call "%GIT%" add -A >> qa.log 2>&1
call "%GIT%" commit -m "fix(web-call): double-voice guard (stop prev audio+speechSynthesis on new turn, dup user-turn guard) + automated agent_tester QA harness" >> qa.log 2>&1
call "%GIT%" push origin main >> qa.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> qa.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 12 && systemctl is-active leadgen && echo ===QA-RUN=== && timeout 180 env PYTHONPATH=/opt/leadgen .venv/bin/python scripts/agent_tester.py 2>&1 | grep -aE 'TEST:|U:|B\(|ISSUE|NO ISSUES|- \[' | tail -60" >> qa.log 2>&1
echo QA_EXIT_%ERRORLEVEL% >> qa.log
echo QA_DONE
