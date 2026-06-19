@echo off
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=-i C:\Users\Ratanshila\.ssh\id_rsa
set HOST=root@72.61.245.204
"%SSH%" %KEY% %HOST% "docker cp /opt/leadgen/scripts/morning_ops_audit.py leadgen_app:/tmp/morning_ops_audit.py 2>/dev/null || true"
"%SSH%" %KEY% %HOST% "cd /opt/leadgen && docker cp scripts/morning_ops_audit.py leadgen_app:/tmp/morning_ops_audit.py && docker exec leadgen_app python /tmp/morning_ops_audit.py" > morning_audit.log 2>&1
type morning_audit.log
