@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del webcall_dbg.log 2>nul

if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add app/api/web_call.py scripts/webcall_debug_deploy.bat scripts/ws_test.py > webcall_dbg.log 2>&1
call "%GIT%" commit -m "web-call: surface llm responder failures as warnings; ws smoke script" >> webcall_dbg.log 2>&1
call "%GIT%" push origin main >> webcall_dbg.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> webcall_dbg.log

%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && systemctl restart leadgen && sleep 10 && timeout 60 .venv/bin/python scripts/ws_test.py ; echo ---RECENT-WARN-ERR--- ; journalctl -u leadgen --since '90 seconds ago' --no-pager | grep -iE 'warn|error|fail' | tail -10" >> webcall_dbg.log 2>&1
echo DBG_EXIT_%ERRORLEVEL% >> webcall_dbg.log
echo DBG_DONE
