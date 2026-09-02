@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent
del /q pytest_full2.log 2>nul
.venv\Scripts\python.exe -m pytest -q --tb=line -p no:cacheprovider > pytest_full2.log 2>&1
echo FULLSUITE_EXIT_%ERRORLEVEL% >> pytest_full2.log
