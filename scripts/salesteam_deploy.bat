@echo off
REM Sales-team batch deploy + SALES_TEAM flag ON + live demo. Log -> salesteam_deploy.log
cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent
set LOG=salesteam_deploy.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes root@72.61.245.204
echo === pull + build + up === > %LOG%
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && git log --oneline -1 && docker compose -f docker-compose.vps.yml build app 2>&1 | tail -2 && python3 scripts/env_set.py SALES_TEAM=1 && docker compose -f docker-compose.vps.yml --profile celery up -d 2>&1 | tail -4" >> %LOG% 2>&1
echo EXIT_DEPLOY=%errorlevel% >> %LOG%
ping -n 17 127.0.0.1 >nul
call %SSH% "curl -s http://127.0.0.1:8000/health | head -c 110; echo; curl -s http://127.0.0.1:8000/health/ready | head -c 160" >> %LOG% 2>&1
echo. >> %LOG%
echo === live demo: ek real deep-dive === >> %LOG%
call %SSH% "docker exec leadgen_app python -c \"import asyncio, json; from app.agents import sales_team as st; r = asyncio.run(st.analyze({'name':'Sharma Solar','niche':'solar','city':'Pune','phone':'+919800000001','rating':4.4,'reviews':62,'website':'','email':'','status':'interested','source':'inquiry','tier':'S'})); print('OK', r.get('ok'), 'SCORE', r.get('score'), 'GRADE', r.get('grade')); print(open(r['md'],encoding='utf-8').read()[:900])\"" >> %LOG% 2>&1
echo === gate check === >> %LOG%
call %SSH% "docker exec leadgen_app printenv SALES_TEAM" >> %LOG% 2>&1
echo === DONE === >> %LOG%
