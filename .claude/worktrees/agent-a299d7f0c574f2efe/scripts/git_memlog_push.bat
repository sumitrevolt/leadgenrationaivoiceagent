@echo off
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
%GIT% add CLAUDE.md docs/SESSION_LOG.md scripts/deploy_consent.bat scripts/git_consent_push.bat scripts/git_memlog_push.bat > git_memlog.log 2>&1
%GIT% commit -m "docs: consent-ledger milestone (CLAUDE.md lean + SESSION_LOG detail) + deploy scripts" >> git_memlog.log 2>&1
%GIT% push origin main >> git_memlog.log 2>&1
echo GIT_EXIT_%ERRORLEVEL% >> git_memlog.log
echo DONE
