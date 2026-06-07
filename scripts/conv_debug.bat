@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del conv_dbg.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "echo ---HITS---; journalctl -u leadgen --since '12 minutes ago' --no-pager | grep -iE 'answer-stream|/stream/|websocket|vobiz_stream' | tail -10; echo ---ERRORS---; journalctl -u leadgen --since '12 minutes ago' --no-pager | grep -iE 'error|exception|traceback' | tail -6; echo ---XML-CHECK---; curl -s -m 8 'https://leadsgenai.in/api/telephony/vobiz/answer-stream/dbgtok?niche=solar_residential' | head -c 300; echo" > conv_dbg.log 2>&1
echo CDBG_EXIT_%ERRORLEVEL% >> conv_dbg.log
echo CDBG_DONE
