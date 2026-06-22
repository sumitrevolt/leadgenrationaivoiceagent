@echo off
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set ROOT=c:\Users\Ratanshila\Documents\leadgenrationaiagent

"%SCP%" -i "%KEY%" -o BatchMode=yes "%ROOT%\app\middleware\__init__.py" root@72.61.245.204:/tmp/middleware_init.py
"%SSH%" -i "%KEY%" -o BatchMode=yes root@72.61.245.204 "docker cp /tmp/middleware_init.py leadgen_app:/app/app/middleware/__init__.py && docker compose -f /opt/leadgen/docker-compose.vps.yml restart app && sleep 18 && curl -sf -o /dev/null -w 'admin-login:%{http_code}\n' http://127.0.0.1:8000/app/admin-login"
