@echo off
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
%GIT% add app/telephony/consent_ledger.py app/telephony/compliance.py app/telephony/call_manager.py app/voice_agent/agent.py app/api/webhooks.py app/api/voiceai.py app/api/growth.py app/platform/team_scheduler.py tests/test_consent_ledger.py scripts/run_consent_tests.bat > git_consent.log 2>&1
%GIT% commit -m "feat(compliance): TCCCPR/DPDP consent + opt-out ledger - suppression enforced in ComplianceGate, 90d recording retention (gated RECORDING_RETENTION), /api/voiceai/consent/* routes, cross-channel opt-out propagation; tests 9/9" >> git_consent.log 2>&1
%GIT% push origin main >> git_consent.log 2>&1
echo GIT_EXIT_%ERRORLEVEL% >> git_consent.log
echo DONE
