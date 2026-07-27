@echo off
REM Owned EXTERNAL_AGENT_RUNNER test wrapper — capture argv; NEVER execute them.
setlocal
set "CAPTURE_OUT=%~dp0_captured_argv_cmd.json"
set "CANARY=%CD%\SECONDARY_CMD_RAN.txt"
if exist "%CANARY%" del /f /q "%CANARY%" >nul 2>&1
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0argv_capture.ps1" -CaptureOut "%CAPTURE_OUT%" -Wrapper cmd %*
exit /b %ERRORLEVEL%
