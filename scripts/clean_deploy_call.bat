@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del cdc.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main && git reset --hard origin/main && git log -1 --oneline && grep -c 'start streamId=' app/telephony/vobiz_stream.py && find app -name '*.pyc' -delete 2>/dev/null; find app -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null; systemctl restart leadgen && sleep 12 && systemctl is-active leadgen" > cdc.log 2>&1
echo PULL_EXIT_%ERRORLEVEL% >> cdc.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && timeout 50 .venv/bin/python scripts/conv_test.py 2>&1 | grep -aE 'STREAM CALL' && sleep 33 && journalctl -u leadgen --since '50 seconds ago' --no-pager | grep -aoE 'vobiz-stream] [^\x22]*|bot:[^\x22]*|user:[^\x22]*' | tail -22" >> cdc.log 2>&1
echo CALL_EXIT_%ERRORLEVEL% >> cdc.log
echo CDC_DONE
