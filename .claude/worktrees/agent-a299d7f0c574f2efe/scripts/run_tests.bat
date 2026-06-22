@echo off
REM Run the test suite and write results to pytest_run.log
cd /d "%~dp0.."
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider > pytest_run.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> pytest_run.log
echo PYTEST_EXIT_%ERRORLEVEL%
