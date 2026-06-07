@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del last_call.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "echo ---LAST-TRANSCRIPT---; tail -c 900 /opt/leadgen/data/call_transcripts/*.jsonl 2>/dev/null; echo; echo ---GROQ-ERRORS---; journalctl -u leadgen --since '25 minutes ago' --no-pager | grep -aoE 'groq[^\x22]{0,100}|free_ai[^\x22]{0,100}' | tail -6" > last_call.log 2>&1
echo LC_DONE
