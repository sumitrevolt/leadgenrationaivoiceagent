@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del conv_retry.log 2>nul
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A > conv_retry.log 2>&1
call "%GIT%" commit -m "fix(vobiz-stream): protocol visibility (raw event logging), top-level streamSid capture, greet-once on first sid (start event optional), event errors at warning" >> conv_retry.log 2>&1
call "%GIT%" push origin main >> conv_retry.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> conv_retry.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && systemctl restart leadgen && sleep 12 && timeout 60 .venv/bin/python scripts/conv_test.py 2>&1 | grep -E 'STREAM CALL' ; sleep 30 ; echo ---CALL-LOGS--- ; journalctl -u leadgen --since '90 seconds ago' --no-pager | grep -iE 'vobiz-stream' | tail -14" >> conv_retry.log 2>&1
echo RETRY_EXIT_%ERRORLEVEL% >> conv_retry.log
echo CR2_DONE
