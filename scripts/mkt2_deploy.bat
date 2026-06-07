@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del mkt2.log 2>nul
.venv\Scripts\python.exe -c "from app.main import app; from app.marketing import gbp_audit, review_replies, festivals, posters, whatsapp_pack, competitor; print('IMPORTS OK'); print('audit Qs:', len(gbp_audit.AUDIT_QUESTIONS)); print('festivals:', len(festivals.FESTIVALS_2026_27)); print('templates:', len(posters.TEMPLATES))" > mkt2.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> mkt2.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> mkt2.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> mkt2.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main >> mkt2.log 2>&1
call "%GIT%" reset --soft origin/main >> mkt2.log 2>&1
call "%GIT%" add -A >> mkt2.log 2>&1
call "%GIT%" commit -m "feat(marketing-v2): research-backed Dhanda+ feature suite — GBP audit scorer (16Q, no API), AI review replies, festival calendar 2026-27 (29) + post ideas, SVG poster generator (6 templates, AdBanao-lite), WhatsApp content pack, competitor analysis — 7-tab marketing suite, all free stack" >> mkt2.log 2>&1
echo COMMIT_EXIT_%ERRORLEVEL% >> mkt2.log
call "%GIT%" push origin main >> mkt2.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> mkt2.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && git log -1 --oneline && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 14 && systemctl is-active leadgen && curl -s -m 8 -o /dev/null -w 'marketing page: %%{http_code}\n' http://127.0.0.1:8000/app/marketing && timeout 40 env PYTHONPATH=/opt/leadgen .venv/bin/python -c \"from app.marketing import gbp_audit, posters, festivals; a=gbp_audit.score_audit({q['id']:0 for q in gbp_audit.AUDIT_QUESTIONS}); print('AUDIT best-case score:', a.get('score'), a.get('grade')); p=posters.generate_poster('offer-burst','R&D <Solar>',offer='20%% OFF',phone='98xxx'); print('POSTER svg ok:', 'R&amp;D' in p['svg'] and len(p['svg'])>500); print('UPCOMING fests:', len(festivals.upcoming(60)))\"" >> mkt2.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> mkt2.log
echo MKT2_DONE
