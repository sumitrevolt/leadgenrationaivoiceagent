@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del call_debug.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "echo ---ANSWER-HITS---; journalctl -u leadgen --since '20 minutes ago' --no-pager | grep -iE 'vobiz|answer' | tail -8; echo ---EXT-GET---; curl -s -m 8 -o /dev/null -w '%%{http_code} %%{content_type}' https://leadsgenai.in/api/telephony/vobiz/answer/firstcall; echo; echo ---EXT-POST---; curl -s -m 8 -X POST -d 'CallUUID=test' -o /dev/null -w '%%{http_code} %%{content_type}' https://leadsgenai.in/api/telephony/vobiz/answer/firstcall; echo" > call_debug.log 2>&1
echo CD_EXIT_%ERRORLEVEL% >> call_debug.log
echo CD2_DONE
