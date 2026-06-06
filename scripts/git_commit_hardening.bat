@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
del git_commit.log 2>nul
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A > git_commit.log 2>&1
call "%GIT%" commit -m "production hardening: fix data.py corruption + stale pycache 500s, UTF-8 safe logging on Windows, JWT secret unification, CSP/mic headers for dashboards+web-call, Docker ships frontend, VPS deploy uses APP_ENV=production with stable secrets+CORS, test DB in temp dir, prod_check script" >> git_commit.log 2>&1
echo COMMIT_EXIT_%ERRORLEVEL% >> git_commit.log
call "%GIT%" log -1 --oneline >> git_commit.log 2>&1
echo GIT_COMMIT_DONE
