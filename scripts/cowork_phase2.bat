@echo off
REM Phase-2 (free-stack): semantic router + greeting cache + prospector->DB. Pull (NO restart) + test.
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_phase2.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === py_compile === > %LOG%
call python -m py_compile app\agents\supervisor.py app\voice_agent\latency.py app\platform\prospector.py tests\test_phase2_upgrades.py >> %LOG% 2>&1
echo EXIT_PYCOMPILE=%errorlevel% >> %LOG%
echo === git add/commit/push === >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(phase2): semantic FREE-LLM supervisor router + pre-synth greeting audio cache (Hinglish) + prospector->DB persist (no paid services) + tests" >> %LOG% 2>&1
echo EXIT_COMMIT=%errorlevel% >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >> %LOG% 2>&1
echo EXIT_PUSH=%errorlevel% >> %LOG%
echo === VPS pull (NO restart; old code keeps serving) === >> %LOG%
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && git log --oneline -1" >> %LOG% 2>&1
echo === IMPORT CHECK (no circular refs) === >> %LOG%
call %SSH% "cd /opt/leadgen && PYTHONPATH=. .venv/bin/python scripts/check_import.py 2>&1 | tail -3" >> %LOG% 2>&1
echo === PYTEST (phase2 + telephony) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python -m pytest tests/test_phase2_upgrades.py tests/test_telephony_upgrades.py -q -o asyncio_mode=auto 2>&1 | tail -20" >> %LOG% 2>&1
echo === DONE (service NOT restarted yet) === >> %LOG%
