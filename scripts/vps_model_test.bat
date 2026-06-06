@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del model_test.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && for M in gemini-2.5-flash-lite gemini-2.0-flash gemini-flash-latest; do echo ===MODEL $M===; timeout 45 env PYTHONPATH=/opt/leadgen DEFAULT_LLM=$M .venv/bin/python /tmp/llm_probe.py 2>&1 | grep -E 'RAW GEMINI|ResourceExhausted|NotFound|InvalidArgument' | head -3; done" > model_test.log 2>&1
echo MODEL_TEST_EXIT_%ERRORLEVEL% >> model_test.log
echo MT_DONE
