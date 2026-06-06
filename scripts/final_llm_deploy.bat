@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del final_llm.log 2>nul

echo === PYTEST === > final_llm.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=no >> final_llm.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> final_llm.log

echo === COMMIT+PUSH === >> final_llm.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add -A >> final_llm.log 2>&1
call "%GIT%" commit -m "fix(llm): ConversationContext built with correct fields; default model gemini-2.5-flash-lite (free-tier quota headroom); ops notes" >> final_llm.log 2>&1
call "%GIT%" push origin main >> final_llm.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> final_llm.log

echo === VPS DEPLOY + MODEL SWITCH === >> final_llm.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && sed -i 's/^DEFAULT_LLM=.*/DEFAULT_LLM=gemini-2.5-flash-lite/' .env && grep '^DEFAULT_LLM=' .env && systemctl restart leadgen && sleep 12 && systemctl is-active leadgen && echo ---WS-TEST--- && timeout 60 .venv/bin/python scripts/ws_test.py ; echo ---WARN-CHECK--- ; journalctl -u leadgen --since '60 seconds ago' --no-pager | grep -icE 'warning.*(llm|ml optimization)' " >> final_llm.log 2>&1
echo FINAL_EXIT_%ERRORLEVEL% >> final_llm.log
echo FINAL_DONE
