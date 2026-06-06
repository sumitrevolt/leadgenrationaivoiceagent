@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del vps_check.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "systemctl is-active leadgen; echo ---LOCAL-HEALTH---; curl -s -m 8 http://127.0.0.1:8000/health; echo; echo ---LOGS---; journalctl -u leadgen -n 30 --no-pager | tail -30" > vps_check.log 2>&1
echo CHECK_EXIT_%ERRORLEVEL% >> vps_check.log
echo CHECK_DONE
