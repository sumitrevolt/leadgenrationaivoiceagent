@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del fin.log 2>nul
.venv\Scripts\python.exe -c "from app.main import app; from app.marketing import referral_kit, evergreen; r=referral_kit.make_referral('Sharma Solar', reward='10%% off'); print('REF code:', bool(r.get('code')), 'svg:', '<svg' in str(r.get('card_svg') or r.get('svg') or '')); print('EVERGREEN:', hasattr(evergreen,'recycle_for_client'))" > fin.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> fin.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> fin.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> fin.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main >> fin.log 2>&1
call "%GIT%" reset --soft origin/main >> fin.log 2>&1
call "%GIT%" add -A >> fin.log 2>&1
call "%GIT%" commit -m "feat(referral+evergreen): referral kit (code + WhatsApp share + Refer&Earn SVG card + tracking) + evergreen content recycling (auto_content fallback so queue never dries) — last free-buildable marketing features, 19th marketing tab" >> fin.log 2>&1
call "%GIT%" push origin main >> fin.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> fin.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=25 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && git log -1 --oneline && systemctl stop leadgen; sleep 2; pkill -9 -f uvicorn 2>/dev/null; find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null; sleep 2; systemctl start leadgen && sleep 16 && systemctl is-active leadgen && curl -s -m 8 -o /dev/null -w 'marketing page: %%{http_code}\n' http://127.0.0.1:8000/app/marketing" >> fin.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> fin.log
echo FIN_DONE
