@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del p3f.log 2>nul
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A > p3f.log 2>&1
call "%GIT%" commit -m "fix(freeswitch): vobiz gateway register=false (per-call digest auth, no REGISTER support on outbound trunks)" >> p3f.log 2>&1
call "%GIT%" push origin main >> p3f.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> p3f.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && cd app/telephony/freeswitch && docker compose restart && sleep 10 && docker exec leadgen-freeswitch fs_cli -x 'sofia status gateway vobiz' | grep -iE 'name|state|status' | head -5" >> p3f.log 2>&1
echo FIX_EXIT_%ERRORLEVEL% >> p3f.log
echo P3F_DONE
