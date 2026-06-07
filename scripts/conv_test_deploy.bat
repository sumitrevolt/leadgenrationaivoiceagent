@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del conv_test.log 2>nul

echo === PYTEST (fixed) === > conv_test.log
.venv\Scripts\python.exe -m pytest tests/test_vobiz.py -q --no-header -p no:cacheprovider --tb=line >> conv_test.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> conv_test.log

echo === COMMIT+PUSH === >> conv_test.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A >> conv_test.log 2>&1
call "%GIT%" commit -m "test(vobiz): update Speak XML test for attribute-free format; conv test script" >> conv_test.log 2>&1
call "%GIT%" push origin main >> conv_test.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> conv_test.log

echo === VPS: STT VERIFY + CONVERSATIONAL CALL === >> conv_test.log
%SCP% -i %KEY% -o BatchMode=yes scripts\conv_test.py root@72.61.245.204:/opt/leadgen/scripts/conv_test.py >> conv_test.log 2>&1
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && systemctl restart leadgen && sleep 12 && timeout 90 .venv/bin/python scripts/conv_test.py 2>&1 | grep -vE '\"timestamp\"' | tail -8" >> conv_test.log 2>&1
echo VPS_EXIT_%ERRORLEVEL% >> conv_test.log
echo CT_DONE
