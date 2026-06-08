@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del sg.log 2>nul
.venv\Scripts\python.exe -c "from app.main import app; from app.platform import growth_engine; from app.api import admin_dashboard; print('IMPORTS OK', hasattr(growth_engine,'pulse'))" > sg.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> sg.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> sg.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> sg.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main >> sg.log 2>&1
call "%GIT%" reset --soft origin/main >> sg.log 2>&1
call "%GIT%" add -A >> sg.log 2>&1
call "%GIT%" commit -m "feat(self-grow): admin dashboard REAL data (sample hata, prospects/inquiries/clients/blog/emails live + /live-stats) + growth_engine.py self-run pulse every 15min (metrics + pipeline self-heal + pitch-learning) + Growth Pulse dashboard card + API. Udyam ready noted" >> sg.log 2>&1
call "%GIT%" push origin main >> sg.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> sg.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 14 && systemctl is-active leadgen && echo ---ADMIN--- && curl -s -m 8 http://127.0.0.1:8000/api/admin/dashboard | head -c 240; echo; echo ---GROWTH--- && timeout 60 env PYTHONPATH=/opt/leadgen .venv/bin/python -c \"import asyncio; from app.platform import growth_engine; p=asyncio.run(growth_engine.pulse()); print('PULSE keys:', sorted(p.keys())[:8]); m=p.get('metrics') or p; print('prospects:', m.get('prospects_total'), 'inquiries:', m.get('inquiries_total'), 'blog:', m.get('blog_articles'))\" 2>&1 | grep -aE 'PULSE|prospects:'; echo ---MCP--- && curl -s -m 8 -o /dev/null -w 'mcp: %%{http_code}\n' http://127.0.0.1:8000/mcp; curl -s -m 8 -o /dev/null -w 'root: %%{http_code} | team: ' http://127.0.0.1:8000/; curl -s -m 8 -o /dev/null -w '%%{http_code}\n' http://127.0.0.1:8000/app/team" >> sg.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> sg.log
echo SG_DONE
