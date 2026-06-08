@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_final.log
echo.>> .gitignore
echo cowork_*.log>> .gitignore
call "C:\PROGRA~1\Git\cmd\git.exe" add -A > %LOG% 2>&1
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "docs: session log + lean memory (multi-agent + deploy); gitignore cowork logs" >> %LOG% 2>&1
echo EXIT_COMMIT=%errorlevel% >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >> %LOG% 2>&1
echo EXIT_PUSH=%errorlevel% >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" log --oneline -1 >> %LOG% 2>&1
echo DONE >> %LOG%
