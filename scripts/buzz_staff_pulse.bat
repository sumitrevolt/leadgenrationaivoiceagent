@echo off
REM Hourly Buzz #staff-pulse post. Registered as scheduled task "LeadGen Buzz Staff Pulse".
REM Read-only: pulls team_status() from the VPS, posts a digest, changes nothing.
setlocal
set REPO=C:\Users\Ratanshila\Documents\leadgenrationaiagent
set LOG=%USERPROFILE%\.buzz\WORK_LOGS\staff_pulse.log

cd /d "%REPO%" || exit /b 1
echo [%date% %time%] pulse start >> "%LOG%"
"%REPO%\.venv\Scripts\python.exe" "%REPO%\scripts\buzz_staff_pulse.py" >> "%LOG%" 2>&1
set "PULSE_RC=%ERRORLEVEL%"
echo [%date% %time%] pulse exit=%PULSE_RC% >> "%LOG%"
endlocal & exit /b %PULSE_RC%
