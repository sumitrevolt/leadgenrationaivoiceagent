@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del call_retry.log 2>nul
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A > call_retry.log 2>&1
call "%GIT%" commit -m "fix(vobiz): Speak XML without voice/language attributes (unsupported attrs made Vobiz skip Speak and hang up immediately)" >> call_retry.log 2>&1
call "%GIT%" push origin main >> call_retry.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> call_retry.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && systemctl restart leadgen && sleep 10 && curl -s -m 8 https://leadsgenai.in/api/telephony/vobiz/answer/firstcall | head -c 200 && echo && timeout 60 .venv/bin/python scripts/first_call.py 2>&1 | grep -E 'PLACE_CALL' | tail -2" >> call_retry.log 2>&1
echo RETRY_EXIT_%ERRORLEVEL% >> call_retry.log
echo CR_DONE
