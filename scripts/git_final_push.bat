@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
del git_commit.log 2>nul
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add scripts/prod_check.py scripts/final_verify.bat scripts/git_final_push.bat .gitignore > git_commit.log 2>&1
call "%GIT%" commit -m "prod_check: pyc-header based stale bytecode detection (mtime+size), auto-clean; verify scripts" >> git_commit.log 2>&1
echo COMMIT_EXIT_%ERRORLEVEL% >> git_commit.log
call "%GIT%" push origin main >> git_commit.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> git_commit.log
call "%GIT%" log -2 --oneline >> git_commit.log 2>&1
echo DONE
