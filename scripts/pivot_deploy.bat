@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del pivot.log 2>nul
.venv\Scripts\python.exe -c "from app.main import app; from app.marketing.packages import get_packages; from app.niches import NICHES; from app.voice_agent.niche_scripts import get_script; p=get_packages(); print('PKGS:', len(p), [x['key'] for x in p]); print('NICHE ai_marketing:', 'ai_marketing' in NICHES); print('SCRIPT:', bool(get_script('ai_marketing').get('opening')))" > pivot.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> pivot.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> pivot.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> pivot.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main >> pivot.log 2>&1
call "%GIT%" reset --soft origin/main >> pivot.log 2>&1
call "%GIT%" add -A >> pivot.log 2>&1
call "%GIT%" commit -m "feat(pivot): marketing-first positioning — 3 packages (Starter 2999/Growth 5999/Advanced AI Agent 11999 with voice = India-unique tier), public /api/marketing/packages, ai_marketing builtin niche + Swara sales script, landing hero+pricing cards, web-call default ai_marketing" >> pivot.log 2>&1
call "%GIT%" push origin main >> pivot.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> pivot.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 14 && systemctl is-active leadgen && curl -s -m 8 http://127.0.0.1:8000/api/marketing/packages | head -c 120; echo; curl -s -m 8 -o /dev/null -w 'root: %%{http_code}\n' http://127.0.0.1:8000/" >> pivot.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> pivot.log
echo PIVOT_DONE
