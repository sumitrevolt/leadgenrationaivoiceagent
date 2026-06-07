@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del tcn.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && echo ---BALANCE---; timeout 25 .venv/bin/python -c \"import asyncio; from app.telephony.vobiz_handler import VobizClient; print(asyncio.run(VobizClient().get_balance()))\" 2>&1 | tail -2; echo ---PLACING-CONVERSATIONAL-CALL---; timeout 50 .venv/bin/python scripts/conv_test.py 2>&1 | grep -aE 'STREAM CALL'" > tcn.log 2>&1
echo TCN_EXIT_%ERRORLEVEL% >> tcn.log
echo TCN_DONE
