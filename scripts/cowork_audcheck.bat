@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_audcheck.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === recheck failing files WITH asyncio_mode=auto === > %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python -m pytest tests/test_voice_agent.py tests/test_seo_blog.py tests/test_production_ready.py tests/test_telephony_upgrades.py -q -o asyncio_mode=auto 2>&1 | tail -8" >> %LOG% 2>&1
echo === DONE === >> %LOG%
