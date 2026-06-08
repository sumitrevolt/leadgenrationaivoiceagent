@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_logfinal.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === append log entry === > %LOG%
type scripts\_logentry.md >> docs\SESSION_LOG.md
del scripts\_logentry.md
echo === git commit docs === >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" add CLAUDE.md docs\SESSION_LOG.md >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "docs: log advanced batch (content scheduler + LLM circuit-breaker)" >> %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >> %LOG% 2>&1
echo EXIT_PUSH=%errorlevel% >> %LOG%
echo === VPS sync docs === >> %LOG%
call %SSH% "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && git log --oneline -1" >> %LOG% 2>&1
echo === DONE === >> %LOG%
