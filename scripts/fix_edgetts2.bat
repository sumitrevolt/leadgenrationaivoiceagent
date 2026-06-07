@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del fix_edgetts.log 2>nul
%SCP% -i %KEY% -o BatchMode=yes scripts\tts_selftest.py root@72.61.245.204:/opt/leadgen/scripts/tts_selftest.py > fix_edgetts.log 2>&1
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=25 root@72.61.245.204 "cd /opt/leadgen && .venv/bin/pip install -U -q edge-tts 2>&1 | tail -2; echo ---SELFTEST---; timeout 40 .venv/bin/python scripts/tts_selftest.py 2>&1 | tail -4; systemctl restart leadgen && sleep 12 && systemctl is-active leadgen" >> fix_edgetts.log 2>&1
echo FE_EXIT_%ERRORLEVEL% >> fix_edgetts.log
echo FE2_DONE
