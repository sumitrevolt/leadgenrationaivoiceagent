@echo off
REM Targeted: consent ledger + regression (compliance/telephony) + prod_check
cd /d "%~dp0.."
.venv\Scripts\python.exe -m pytest tests/test_consent_ledger.py tests/test_telephony_upgrades.py -q --no-header -p no:cacheprovider > consent_test.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> consent_test.log
.venv\Scripts\python.exe scripts\prod_check.py >> consent_test.log 2>&1
echo PRODCHECK_EXIT_%ERRORLEVEL% >> consent_test.log
echo DONE
