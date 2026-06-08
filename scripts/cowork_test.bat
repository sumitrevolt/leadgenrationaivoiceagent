@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_test.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes root@72.61.245.204
echo === push self-test === > %LOG%
call python -m py_compile scripts\test_features.py >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "test: live feature self-test script" >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >> %LOG% 2>&1
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q" >> %LOG% 2>&1
echo === RUN SELF-TEST (real LLM env) === >> %LOG%
call %SSH% "cd /opt/leadgen && .venv/bin/python scripts/test_features.py" >> %LOG% 2>&1
echo === RECENT PROD ERRORS (excl Cerebras-429 noise) === >> %LOG%
call %SSH% "journalctl -u leadgen --since '25 min ago' --no-pager 2>/dev/null | grep -iE 'error|exception|traceback' | grep -viE 'cerebras chat failed|too_many_requests|queue_exceeded' | tail -20" >> %LOG% 2>&1
echo === DONE === >> %LOG%
