@echo off
REM Phase-3 voice (Silero VAD + Smart Turn, OFF-default) + phone_verified footgun fix. Pull (no restart) + test.
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_phase3.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === py_compile === > %LOG%
call python -m py_compile app\telephony\vobiz_stream.py app\voice_agent\phone_stream.py app\voice_agent\turn_detector.py app\voice_agent\pipeline.py app\tasks\scraping.py tests\test_phase3_voice.py >> %LOG% 2>&1
echo EXIT_PYCOMPILE=%errorlevel% >> %LOG%
echo === git add/commit/push === >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(phase3-voice): wire Silero VAD gate into vobiz/phone streams + Smart Turn v3 combine in pipeline (OFF-default, graceful) + fix phone_verified filter footgun + tests" >> %LOG% 2>&1
echo EXIT_COMMIT=%errorlevel% >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >> %LOG% 2>&1
echo EXIT_PUSH=%errorlevel% >> %LOG%
echo === VPS pull (NO restart) === >> %LOG%
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && git log --oneline -1" >> %LOG% 2>&1
echo === IMPORT CHECK === >> %LOG%
call %SSH% "cd /opt/leadgen && PYTHONPATH=. .venv/bin/python scripts/check_import.py 2>&1 | tail -2" >> %LOG% 2>&1
echo === PYTEST (phase3 voice + phase2 + telephony) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python -m pytest tests/test_phase3_voice.py tests/test_phase2_upgrades.py tests/test_telephony_upgrades.py -q -o asyncio_mode=auto 2>&1 | tail -16" >> %LOG% 2>&1
echo === DONE (not restarted) === >> %LOG%
