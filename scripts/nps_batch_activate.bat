@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent
set LOG=nps_batch_activate.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes root@72.61.245.204
echo === flags ON === > %LOG%
call %SSH% "cd /opt/leadgen && python3 scripts/env_set.py NPS_ALERTS=1 PAYMENT_RECON=1 INDEXNOW=1" >> %LOG% 2>&1
echo === recreate for env pickup === >> %LOG%
call %SSH% "cd /opt/leadgen && docker compose -f docker-compose.vps.yml --profile celery up -d 2>&1 | tail -4" >> %LOG% 2>&1
ping -n 13 127.0.0.1 >nul
call %SSH% "curl -s http://127.0.0.1:8000/health | head -c 120" >> %LOG% 2>&1
echo. >> %LOG%
echo === alembic adopt (stamp head, zero DDL) === >> %LOG%
call %SSH% "cd /opt/leadgen && bash scripts/alembic_baseline.sh --apply" >> %LOG% 2>&1
echo EXIT_ALEMBIC=%errorlevel% >> %LOG%
echo === live gates verify === >> %LOG%
call %SSH% "docker exec leadgen_app python -c \"import asyncio; from app.billing import payment_recon as pr; print('RECON', asyncio.run(pr.run_if_enabled(3)))\"" >> %LOG% 2>&1
call %SSH% "docker exec leadgen_app python -c \"import asyncio; from app.marketing import indexnow as ix; print('INDEXNOW', asyncio.run(ix.submit_sitemap_if_enabled()))\"" >> %LOG% 2>&1
echo === DONE === >> %LOG%
