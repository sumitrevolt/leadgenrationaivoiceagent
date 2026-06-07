@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del tune.log 2>nul
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line > tune.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> tune.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A >> tune.log 2>&1
call "%GIT%" commit -m "tune(voice): human-fast — VAD captures full sentences (silence 850ms), junk-STT guard (no LLM on fragments=save money), brutal-brevity prompt (1 sentence/<=15 words, no meta-talk, max_tokens 50)" >> tune.log 2>&1
call "%GIT%" push origin main >> tune.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> tune.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 10 && systemctl is-active leadgen" >> tune.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> tune.log
echo TUNE_DONE
