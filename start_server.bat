@echo off
title LeadGenAI - Local Server
cd /d "%~dp0"
echo ===============================================
echo    LeadGenAI - Local backend server
echo ===============================================
echo.
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
echo Python: %PY%
echo.
echo Jab niche "Application startup complete" dikhe, browser me kholo:
echo    Admin dashboard : http://127.0.0.1:8000/app/admin
echo    Onboard wizard  : http://127.0.0.1:8000/app/onboard
echo    Admin login     : http://127.0.0.1:8000/app/admin-login
echo.
echo (Server band karne ke liye is window me Ctrl+C dabao)
echo -----------------------------------------------
echo.
"%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
echo.
echo Server ruk gaya. Agar upar laal (red) error/traceback hai to uska screenshot bhejo.
pause
