@echo off
setlocal
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set HOST=root@72.61.245.204

"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "sleep 15 && docker exec leadgen_app python3 -c \"import asyncio,os; from datetime import datetime,timedelta,timezone; IST=timezone(timedelta(hours=5,minutes=30)); print('IST',datetime.now(IST).strftime('%H:%M')); from app.telephony.compliance import CallType,get_compliance_gate; g=get_compliance_gate(); r=asyncio.run(g.check('+919876543210',CallType.PROMOTIONAL)); print('promo',r.allowed,r.reasons)\""
