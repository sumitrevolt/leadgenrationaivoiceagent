@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del verify_deploy.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && echo ---HEAD---; git log -1 --oneline; echo ---GREP-NEWCODE---; grep -c 'start streamId=' app/telephony/vobiz_stream.py; grep -c 'def _maybe_greet' app/telephony/vobiz_stream.py; echo ---CLEAR-PYC---; find app -name '*.pyc' -delete; find app -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null; systemctl restart leadgen; sleep 12; systemctl is-active leadgen" > verify_deploy.log 2>&1
echo VD_EXIT_%ERRORLEVEL% >> verify_deploy.log
echo VD_DONE
