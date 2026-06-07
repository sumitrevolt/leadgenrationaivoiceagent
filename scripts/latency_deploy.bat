@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del latd.log 2>nul
.venv\Scripts\python.exe -c "from app.telephony import vobiz_stream as v; print('import OK; SILENCE_MS=', v.SILENCE_MS); print('split:', v._split_sentences('Namaste sir. Aap kaise hain? Theek.'))" > latd.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> latd.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> latd.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> latd.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main >> latd.log 2>&1
call "%GIT%" reset --soft origin/main >> latd.log 2>&1
call "%GIT%" add -A >> latd.log 2>&1
call "%GIT%" commit -m "perf(voice-free): sentence-chunked streaming TTS (first-audio ~0.5s vs 2-4s), Groq whisper-large-v3-turbo STT, VAD silence 650ms — all free, no paid services" >> latd.log 2>&1
echo COMMIT_EXIT_%ERRORLEVEL% >> latd.log
call "%GIT%" push origin main >> latd.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> latd.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && git log -1 --oneline && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 12 && systemctl is-active leadgen" >> latd.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> latd.log
echo LATD_DONE
