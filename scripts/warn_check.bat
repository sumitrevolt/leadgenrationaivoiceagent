@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del warn_check.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "journalctl -u leadgen --since '5 minutes ago' --no-pager | grep -iE 'warning' | grep -ivE 'sentry' | tail -5" > warn_check.log 2>&1
echo WC_DONE
