@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del pro.log 2>nul
.venv\Scripts\python.exe -c "from app.voice_agent.niche_scripts import get_script,kb_documents; print('scripts OK; solar opening:', get_script('solar_residential')['opening'][:60]); from app.voice_agent.telecaller_brain import TelecallerBrain; print('brain import OK')" > pro.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> pro.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> pro.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> pro.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main >> pro.log 2>&1
call "%GIT%" reset --soft origin/main >> pro.log 2>&1
call "%GIT%" add -A >> pro.log 2>&1
call "%GIT%" commit -m "feat(training): professional per-niche script dataset (openings/discovery/objections/closings) seeded into KB + grounded into TelecallerBrain persona (top-telecaller, not noob); pro opener on calls" >> pro.log 2>&1
echo COMMIT_EXIT_%ERRORLEVEL% >> pro.log
call "%GIT%" push origin main >> pro.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> pro.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && git log -1 --oneline && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 12 && systemctl is-active leadgen" >> pro.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> pro.log
echo PRO_DONE
