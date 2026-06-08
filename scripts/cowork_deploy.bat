@echo off
REM One-shot deploy helper for this Cowork session (push side). Output -> cowork_deploy.log
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_deploy.log
echo === py_compile new modules === > %LOG%
call python -m py_compile app\voice_agent\turn_detector.py app\agents\staff_supervisor.py >> %LOG% 2>&1
echo EXIT_PYCOMPILE=%errorlevel% >> %LOG%
echo === git add -A === >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" add -A >> %LOG% 2>&1
echo === git status --short === >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" status --short >> %LOG% 2>&1
echo === git commit === >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat: website SEO/JSON-LD/lucide icons + turn_detector VAD + staff_supervisor multi-agent + lean memory/docs" >> %LOG% 2>&1
echo EXIT_COMMIT=%errorlevel% >> %LOG%
echo === git push origin main === >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" push origin main >> %LOG% 2>&1
echo EXIT_PUSH=%errorlevel% >> %LOG%
echo === git log -1 === >> %LOG%
call "C:\PROGRA~1\Git\cmd\git.exe" log --oneline -1 >> %LOG% 2>&1
echo === DONE === >> %LOG%
