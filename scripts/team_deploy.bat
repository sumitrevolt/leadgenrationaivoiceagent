@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del team.log 2>nul
.venv\Scripts\python.exe -c "from app.main import app; from app.platform import team, team_scheduler; from app.agents import staff; from app.marketing import post_generator; from app.api import team as t, marketing as m; print('ALL IMPORTS OK')" > team.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> team.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> team.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> team.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main >> team.log 2>&1
call "%GIT%" reset --soft origin/main >> team.log 2>&1
call "%GIT%" add -A >> team.log 2>&1
call "%GIT%" commit -m "feat(team+marketing): AI Staff company roster (8 members, roles+duties) + agent_events activity log + automation scheduler (QA 02:30/trainer 03:00/ops hourly) + team admin dashboard (/app/team) + Dhanda-style AI marketing module (Isha: posts/calendar/GBP tips, /app/marketing) — all free stack" >> team.log 2>&1
echo COMMIT_EXIT_%ERRORLEVEL% >> team.log
call "%GIT%" push origin main >> team.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> team.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && git log -1 --oneline && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 14 && systemctl is-active leadgen && curl -s -m 8 -o /dev/null -w 'team page: %%{http_code}\n' http://127.0.0.1:8000/app/team && curl -s -m 8 -o /dev/null -w 'marketing page: %%{http_code}\n' http://127.0.0.1:8000/app/marketing && journalctl -u leadgen -n 80 --no-pager | grep -aE 'Team scheduler|Team router|Marketing router|automation' | tail -4" >> team.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> team.log
echo TEAM_DONE
