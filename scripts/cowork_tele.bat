@echo off
REM Telephony hardening — compile, push, pull (NO restart), import-check + pytest. Log -> cowork_tele.log
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_tele.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === py_compile === > %LOG%
call python -m py_compile app\utils\dnd_checker.py app\telephony\compliance.py app\telephony\exotel_handler.py app\telephony\call_state.py app\telephony\call_manager.py app\telephony\webhooks.py app\api\health.py app\tasks\scraping.py app\main.py scripts\check_import.py tests\test_telephony_upgrades.py >> %LOG% 2>&1
echo EXIT_PYCOMPILE=%errorlevel% >> %LOG%
echo === git add/commit/push === >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(telephony): production hardening - mount+sign telephony webhooks, AMD, fail-closed DND, Exotel payload, Redis call state, async enrichment, cached metrics + tests" >> %LOG% 2>&1
echo EXIT_COMMIT=%errorlevel% >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >> %LOG% 2>&1
echo EXIT_PUSH=%errorlevel% >> %LOG%
echo === VPS pull (NO restart; old code keeps serving) === >> %LOG%
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && git log --oneline -1" >> %LOG% 2>&1
echo === IMPORT CHECK (circular refs / app builds) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python scripts/check_import.py 2>&1 | tail -8" >> %LOG% 2>&1
echo === PYTEST (telephony upgrades) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python -m pytest tests/test_telephony_upgrades.py -q 2>&1 | tail -30" >> %LOG% 2>&1
echo === DONE (service NOT restarted yet) === >> %LOG%
