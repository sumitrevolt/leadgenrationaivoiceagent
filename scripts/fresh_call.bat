@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del fresh_call.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && systemctl is-active leadgen && echo ---PLACING--- && timeout 50 .venv/bin/python scripts/conv_test.py 2>&1 | grep -aE 'STT_AVAILABLE|STREAM CALL' && sleep 33 && echo ---STREAM-LOGS--- && journalctl -u leadgen --since '50 seconds ago' --no-pager | grep -aoE 'vobiz-stream] [^\x22]*|bot:[^\x22]*|user:[^\x22]*' | tail -24" > fresh_call.log 2>&1
echo FC_EXIT_%ERRORLEVEL% >> fresh_call.log
echo FRESH_DONE
