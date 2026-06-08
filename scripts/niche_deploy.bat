@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del nd.log 2>nul
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> nd.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> nd.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main >> nd.log 2>&1
call "%GIT%" reset --soft origin/main >> nd.log 2>&1
call "%GIT%" add -A >> nd.log 2>&1
call "%GIT%" commit -m "feat(niches): marketing-first reframe — +16 local-business marketing niches (restaurant/jewellery/salon/boutique/gym/bakery/mobile/hotel/auto/photography/pharmacy/furniture/kirana/travel/gift/hardware), category tags (marketing/leadgen/both) + content_focus on all 42, niche_knowledge packs, tests 26->42" >> nd.log 2>&1
call "%GIT%" push origin main >> nd.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> nd.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 14 && systemctl is-active leadgen && curl -s -m 8 'http://127.0.0.1:8000/api/data/niches' | python3 -c 'import sys,json; d=json.load(sys.stdin); print(\"NICHES API count:\", d.get(\"count\"))' && curl -s -m 8 'http://127.0.0.1:8000/api/data/niches?tier=S' | python3 -c 'import sys,json; print(\"S-tier:\", json.load(sys.stdin).get(\"count\"))'" >> nd.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> nd.log
echo ND_DONE
