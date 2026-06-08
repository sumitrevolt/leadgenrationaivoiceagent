@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del ch.log 2>nul
.venv\Scripts\python.exe -c "from app.main import app; from app.marketing import seo_blog; from app.platform import auto_outreach, team_scheduler; from app.marketing import auto_content; print('IMPORTS OK'); print('followups:', hasattr(auto_outreach,'run_email_followups')); print('blog:', hasattr(seo_blog,'run_daily_blog'))" > ch.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> ch.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> ch.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> ch.log
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" fetch origin main >> ch.log 2>&1
call "%GIT%" reset --soft origin/main >> ch.log 2>&1
call "%GIT%" add -A >> ch.log 2>&1
call "%GIT%" commit -m "feat(growth-channels): programmatic SEO blog engine (/blog auto-articles, dynamic sitemap, daily 06:30) + auto email follow-up sequences (Day-3/Day-7 non-responders, 10:30 job) + LeadGen AI self-brand auto-content. More inbound + multi-touch, all free" >> ch.log 2>&1
call "%GIT%" push origin main >> ch.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> ch.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && git fetch origin main -q && git reset --hard origin/main -q && find app -name '*.pyc' -delete 2>/dev/null; systemctl restart leadgen && sleep 14 && systemctl is-active leadgen && timeout 60 env PYTHONPATH=/opt/leadgen .venv/bin/python -c \"import asyncio; from app.marketing import seo_blog; print('BLOG_RUN:', asyncio.run(seo_blog.run_daily_blog(2)))\" 2>&1 | grep -aE 'BLOG_RUN'; curl -s -m 8 -o /dev/null -w 'blog page: %%{http_code}\n' http://127.0.0.1:8000/blog; curl -s -m 8 http://127.0.0.1:8000/sitemap.xml | grep -c '/blog/'" >> ch.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> ch.log
echo CH_DONE
