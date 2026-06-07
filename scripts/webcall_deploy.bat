@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del wcd.log 2>nul
.venv\Scripts\python.exe -c "from app.main import app; from app.api import web_call; print('web_call import OK')" > wcd.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> wcd.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> wcd.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> wcd.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main >> wcd.log 2>&1
call "%GIT%" reset --soft origin/main >> wcd.log 2>&1
call "%GIT%" add -A >> wcd.log 2>&1
call "%GIT%" commit -m "feat(web-call): real phone-call UI (hands-free continuous listening, call screen, echo-guard) + professional TelecallerBrain + EdgeTTS Swara voice — FREE android test that matches real call quality" >> wcd.log 2>&1
echo COMMIT_EXIT_%ERRORLEVEL% >> wcd.log
call "%GIT%" push origin main >> wcd.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> wcd.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && git log -1 --oneline && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 12 && systemctl is-active leadgen && curl -s -m 8 -o /dev/null -w 'test-call page: %%{http_code}\n' http://127.0.0.1:8000/app/test-call" >> wcd.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> wcd.log
echo WCD_DONE
