@echo off
REM ===== VOICE HUMANIZATION + ADMIN-UX deploy (2026-06-12) =====
REM Gate: prod_check + targeted voice tests -> commit/push -> VPS pull+build+up -> health+smoke
cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set LOG=scripts\deploy_voicehuman.log
del /q %LOG% 2>nul

echo === 1. prod_check === > %LOG%
python scripts\prod_check.py >> %LOG% 2>&1
if errorlevel 1 goto :fail

echo === 2. targeted tests (voice paths) === >> %LOG%
python -m pytest tests\test_exotel_stream.py tests\test_phase3_voice.py -q >> %LOG% 2>&1
if errorlevel 1 goto :fail

echo === 3. git commit + push === >> %LOG%
call %GIT% add app/voice_agent/phone_stream.py app/voice_agent/exotel_stream.py app/platform/today_overview.py app/api/growth.py app/api/customer_auth.py frontend/automation.html frontend/customer_dashboard.html .claude/skills/voice-humanization/SKILL.md .claude/skills/admin-friendly-ux/SKILL.md scripts/deploy_voicehuman.bat CLAUDE.md docs/SESSION_LOG.md >> %LOG% 2>&1
call %GIT% commit -m "voice humanization - exotel groq stt, telecaller brain, fillers, prosody, admin aaj tab, customer content card" >> %LOG% 2>&1
call %GIT% push origin main >> %LOG% 2>&1
if errorlevel 1 goto :fail

echo === 4. VPS deploy === >> %LOG%
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "echo c2V0IC1lCnNldCAtbyBwaXBlZmFpbApjZCAvb3B0L2xlYWRnZW4KZ2l0IHN0YXNoIC1xIDI+L2Rldi9udWxsIHx8IHRydWUKZ2l0IGZldGNoIG9yaWdpbiAtcQpnaXQgbWVyZ2UgLS1mZi1vbmx5IG9yaWdpbi9tYWluCmVjaG8gIlBVTExFRDogJChnaXQgbG9nIC0xIC0tb25lbGluZSB8IGhlYWQgLWMgNzApIgpweXRob24zIHNjcmlwdHMvZW52X3NldC5weSBQSE9ORV9UVFNfUkFURT0rOCUgMj4mMSB8IHRhaWwgLTEgfHwgdHJ1ZQpkb2NrZXIgY29tcG9zZSAtZiBkb2NrZXItY29tcG9zZS52cHMueW1sIGJ1aWxkIGFwcCAyPiYxIHwgdGFpbCAtMgpkb2NrZXIgY29tcG9zZSAtZiBkb2NrZXItY29tcG9zZS52cHMueW1sIC0tcHJvZmlsZSBjZWxlcnkgdXAgLWQgLS1mb3JjZS1yZWNyZWF0ZSBhcHAgd29ya2VyIHNjaGVkdWxlciAyPiYxIHwgdGFpbCAtMwpzbGVlcCAxNgplY2hvIC1uICJIRUFMVEgxOiAiOyBjdXJsIC1zIC1vIC9kZXYvbnVsbCAtdyAnJXtodHRwX2NvZGV9JyBodHRwOi8vMTI3LjAuMC4xOjgwMDAvaGVhbHRoOyBlY2hvCnNsZWVwIDYKZWNobyAtbiAiSEVBTFRIMjogIjsgY3VybCAtcyAtbyAvZGV2L251bGwgLXcgJyV7aHR0cF9jb2RlfScgaHR0cDovLzEyNy4wLjAuMTo4MDAwL2hlYWx0aDsgZWNobwpkb2NrZXIgZXhlYyBsZWFkZ2VuX2FwcCBweXRob24gLWMgIgpmcm9tIGFwcC52b2ljZV9hZ2VudCBpbXBvcnQgcGhvbmVfc3RyZWFtIGFzIHBzCnByaW50KCdQU19TVFRfQ0hBSU4nLCBoYXNhdHRyKHBzLlBob25lQ2FsbFNlc3Npb24sICdfc3R0X2NoYWluJykpCnByaW50KCdQU19UVFNfUkFURScsIHBzLlRUU19SQVRFLCAnRklMTEVSUycsIHBzLkZJTExFUlNfRU5BQkxFRCkKZnJvbSBhcHAudm9pY2VfYWdlbnQuZXhvdGVsX3N0cmVhbSBpbXBvcnQgRXhvdGVsVm9pY2Vib3RTZXNzaW9uCnByaW50KCdFWE9fV0lSRV9PSycsICdfbXAzX3RvX3dpcmUnIGluIEV4b3RlbFZvaWNlYm90U2Vzc2lvbi5fX2RpY3RfXykKZnJvbSBhcHAucGxhdGZvcm0gaW1wb3J0IHRvZGF5X292ZXJ2aWV3CmQgPSB0b2RheV9vdmVydmlldy5idWlsZCgpCnByaW50KCdUT0RBWV9PSycsIHJlcHIoZFsnaGVhZGxpbmUnXVs6NzBdKSkKcHJpbnQoJ1RPREFZX1BST0JMRU1TJywgbGVuKGRbJ3Byb2JsZW1zJ10pLCAnU1RBRkYnLCBsZW4oZFsnc3RhZmYnXSkpCiIKZWNobyAtbiAiRVhUX0hFQUxUSDogIjsgY3VybCAtcyAtbyAvZGV2L251bGwgLXcgJyV7aHR0cF9jb2RlfScgaHR0cHM6Ly9sZWFkc2dlbmFpLmluL2hlYWx0aDsgZWNobwplY2hvIC1uICJFWFRfQVVUT01BVElPTjogIjsgY3VybCAtcyAtbyAvZGV2L251bGwgLXcgJyV7aHR0cF9jb2RlfScgaHR0cHM6Ly9sZWFkc2dlbmFpLmluL2FwcC9hdXRvbWF0aW9uOyBlY2hvCmRvY2tlciBwcyAtLWZvcm1hdCAne3suTmFtZXN9fSB7ey5TdGF0dXN9fScgfCBncmVwIC1FICdsZWFkZ2VuXyhhcHB8d29ya2VyfHNjaGVkdWxlciknCmVjaG8gVk9JQ0VIVU1BTl9ERVBMT1lfRE9ORQo= | base64 -d | bash" >> %LOG% 2>&1
echo BAT_EXIT_%ERRORLEVEL% >> %LOG%
echo BATDONE
goto :eof

:fail
echo DEPLOY_ABORTED_CHECK_LOG >> %LOG%
echo BATFAIL
