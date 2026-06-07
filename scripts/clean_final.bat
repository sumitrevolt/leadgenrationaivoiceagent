@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del clean.log 2>nul
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
REM remote ke saath sync (origin aage ho sakta), phir saari unpushed commits
REM (jinme secret thi) ko ek clean commit me collapse karo
call "%GIT%" fetch origin main > clean.log 2>&1
call "%GIT%" reset --soft origin/main >> clean.log 2>&1
call "%GIT%" add -A >> clean.log 2>&1
call "%GIT%" commit -m "tune(voice): human-fast VAD+brevity+junk-guard; Cerebras gpt-oss-120b + Groq STT live; scripts secret-free" >> clean.log 2>&1
echo COMMIT_EXIT_%ERRORLEVEL% >> clean.log
call "%GIT%" push origin main >> clean.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> clean.log
call "%GIT%" log -1 --oneline >> clean.log 2>&1
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && git log -1 --oneline && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 10 && systemctl is-active leadgen" >> clean.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> clean.log
echo CLEAN_DONE
