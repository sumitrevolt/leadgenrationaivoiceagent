@echo off
setlocal
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set HOST=root@72.61.245.204
set LOG=%~dp0vps_vobiz_balance.log

echo balance check > "%LOG%"

"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "docker exec leadgen_app python3 scripts/setup_status.py" >> "%LOG%" 2>&1

"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "docker exec leadgen_app python3 -c \"import asyncio; from app.telephony.telephony_readiness import run_checks; from app.telephony.vobiz_handler import VobizClient; r=run_checks(); print('READINESS',r['score'],r.get('missing')); c=VobizClient(); print('VOBIZ_OK',c.available()); print(asyncio.run(c.get_balance()) if c.available() else '')\"" >> "%LOG%" 2>&1

type "%LOG%"
