@echo off
REM Boot the app, hit critical endpoints, report, shut down.
cd /d "%~dp0.."
REM kill anything already on the port (stale previous run)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8923 ^| findstr LISTENING') do taskkill /f /pid %%a > nul 2>&1
ping -n 2 127.0.0.1 > nul
del smoke_test.log 2>nul
del uvicorn_smoke.log 2>nul
start "leadgen-smoke" /b cmd /c ".venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8923 > uvicorn_smoke.log 2>&1"
ping -n 13 127.0.0.1 > nul
echo === /health === > smoke_test.log
curl.exe -s -m 8 http://127.0.0.1:8923/health >> smoke_test.log 2>&1
echo. >> smoke_test.log
echo === /api/data/niches === >> smoke_test.log
curl.exe -s -m 8 -o nul -w "HTTP %%{http_code}" http://127.0.0.1:8923/api/data/niches >> smoke_test.log 2>&1
echo. >> smoke_test.log
echo === / === >> smoke_test.log
curl.exe -s -m 8 -o nul -w "HTTP %%{http_code}" http://127.0.0.1:8923/ >> smoke_test.log 2>&1
echo. >> smoke_test.log
echo === /app/test-call === >> smoke_test.log
curl.exe -s -m 8 -o nul -w "HTTP %%{http_code}" http://127.0.0.1:8923/app/test-call >> smoke_test.log 2>&1
echo. >> smoke_test.log
echo === /api/ml/status === >> smoke_test.log
curl.exe -s -m 8 -o nul -w "HTTP %%{http_code}" http://127.0.0.1:8923/api/ml/status >> smoke_test.log 2>&1
echo. >> smoke_test.log
echo === /docs === >> smoke_test.log
curl.exe -s -m 8 -o nul -w "HTTP %%{http_code}" http://127.0.0.1:8923/docs >> smoke_test.log 2>&1
echo. >> smoke_test.log
echo SMOKE_DONE >> smoke_test.log
REM kill the uvicorn we started (by port)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8923 ^| findstr LISTENING') do taskkill /f /pid %%a > nul 2>&1
echo SMOKE_DONE
