@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del call_debug.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "echo ---ANSWER-HITS---; journalctl -u leadgen --since '15 minutes ago' --no-pager | grep -iE 'vobiz|answer' | tail -6; echo ---EXTERNAL-TEST---; curl -s -m 8 -o /dev/null -w 'GET: %%{http_code} %%{content_type}\n' https://leadsgenai.in/api/telephony/vobiz/answer/firstcall; curl -s -m 8 -X POST -o /dev/null -w 'POST: %%{http_code} %%{content_type}\n' https://leadsgenai.in/api/telephony/vobiz/answer/firstcall; echo ---CDR---; cd /opt/leadgen && .venv/bin/python -c \"
import requests
from pathlib import Path
env={l.split('=',1)[0]:l.split('=',1)[1].strip() for l in Path('.env').read_text(errors='ignore').splitlines() if '=' in l and not l.startswith('#')}
H={'X-Auth-ID':env['VOBIZ_AUTH_ID'],'X-Auth-Token':env['VOBIZ_AUTH_TOKEN']}
B='https://api.vobiz.ai/api/v1/Account/'+env['VOBIZ_AUTH_ID']
r=requests.get(B+'/Call/',headers=H,timeout=20)
print('CDR list:',r.status_code,str(r.text)[:500])
\" 2>&1 | tail -4" > call_debug.log 2>&1
echo CD_EXIT_%ERRORLEVEL% >> call_debug.log
echo CD_DONE
