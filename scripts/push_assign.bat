@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent
call C:\PROGRA~1\Git\cmd\git.exe add scripts/exotel_assign_flow.py scripts/push_assign.bat
call C:\PROGRA~1\Git\cmd\git.exe commit -m "exotel assign-flow ready-to-flip script"
call C:\PROGRA~1\Git\cmd\git.exe push origin main
echo PUSH_EXIT %ERRORLEVEL%
