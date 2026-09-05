@echo off
setlocal
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set SCP=C:\PROGRA~1\Git\usr\bin\scp.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set HOST=root@72.61.245.204
set LOG=%~dp0sip_trace.log

"%SCP%" -i "%KEY%" -o BatchMode=yes %~dp0trace_vobiz_sip.py %HOST%:/tmp/trace_vobiz_sip.py
"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "python3 /tmp/trace_vobiz_sip.py" > "%LOG%" 2>&1
type "%LOG%"
