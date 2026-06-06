@echo off
cd /d "%~dp0.."
del git_check.log 2>nul
echo === git version === > git_check.log
call git --version >> git_check.log 2>&1
echo === git status === >> git_check.log
call git status --short >> git_check.log 2>&1
echo GIT_STATUS_EXIT_%ERRORLEVEL% >> git_check.log
echo === git log -3 === >> git_check.log
call git log --oneline -3 >> git_check.log 2>&1
echo === git remote === >> git_check.log
call git remote -v >> git_check.log 2>&1
echo GIT_CHECK_DONE
