@echo off
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
"%SSH%" -i "%KEY%" -o BatchMode=yes root@72.61.245.204 "docker logs leadgen_app --since 20m 2>&1 | grep -iE '9175515858|placed|stream|answer|hangup|no.?answer|busy|failed|blocked' | tail -30"
