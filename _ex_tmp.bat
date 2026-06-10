@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent
C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204 "cd /opt/leadgen && git pull --ff-only -q && docker cp scripts/exotel_setup_audit.py leadgen_app:/app/scripts/exotel_setup_audit.py && docker exec leadgen_app python scripts/exotel_setup_audit.py" > _ex_out.log 2>&1
echo SSH_EXIT %ERRORLEVEL% >> _ex_out.log
