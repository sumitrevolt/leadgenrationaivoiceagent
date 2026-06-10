@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent
set LOG=nps_batch_smoke.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes root@72.61.245.204
call %SSH% "curl -s http://127.0.0.1:8000/health/ready | head -c 280" > %LOG% 2>&1
echo. >> %LOG%
call %SSH% "echo -n KEYFILE=; curl -s http://127.0.0.1:8000/indexnow-key.txt | head -c 36" >> %LOG% 2>&1
echo. >> %LOG%
call %SSH% "curl -s https://leadsgenai.in/health | head -c 140" >> %LOG% 2>&1
echo. >> %LOG%
call %SSH% "docker ps | grep -c Up; docker exec leadgen_app python -c \"import asyncio; from app.platform import nps; from app.billing import payment_recon as pr; from app.marketing import indexnow as ix; print('NPS', nps.compute_nps([10,9,3])); print('RECON_GATE', asyncio.run(pr.run_if_enabled())); print('IXGATE', asyncio.run(ix.submit_sitemap_if_enabled())); print('PAYLOAD_HOST', ix.build_payload(['/blog/x'])['host'])\"" >> %LOG% 2>&1
echo === DONE === >> %LOG%
