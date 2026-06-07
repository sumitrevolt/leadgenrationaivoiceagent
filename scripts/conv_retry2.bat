@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del conv_retry2.log 2>nul
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A > conv_retry2.log 2>&1
call "%GIT%" commit -m "fix(vobiz-stream): capture streamId field (not streamSid); greet+process media without sid gate (playAudio needs no id) — fixes silent call" >> conv_retry2.log 2>&1
call "%GIT%" push origin main >> conv_retry2.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> conv_retry2.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && systemctl restart leadgen && sleep 12 && timeout 60 .venv/bin/python scripts/conv_test.py 2>&1 | grep -E 'STREAM CALL' ; sleep 32 ; echo ---LOGS--- ; journalctl -u leadgen --since '70 seconds ago' --no-pager | grep -aoE 'vobiz-stream[^\"]*' | head -22" >> conv_retry2.log 2>&1
echo RETRY_EXIT_%ERRORLEVEL% >> conv_retry2.log
echo CR3_DONE
