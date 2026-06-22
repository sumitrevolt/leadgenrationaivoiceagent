@echo off
REM Build the React frontend (vite) and log the result
cd /d "%~dp0..\frontend"
del ..\frontend_build.log 2>nul
echo === node/npm versions === > ..\frontend_build.log
node --version >> ..\frontend_build.log 2>&1
call npm --version >> ..\frontend_build.log 2>&1
echo === npm install === >> ..\frontend_build.log
call npm install --include=dev --no-audit --no-fund >> ..\frontend_build.log 2>&1
echo NPM_INSTALL_EXIT_%ERRORLEVEL% >> ..\frontend_build.log
echo === npm run build === >> ..\frontend_build.log
call npm run build >> ..\frontend_build.log 2>&1
echo BUILD_EXIT_%ERRORLEVEL% >> ..\frontend_build.log
echo BUILD_DONE
