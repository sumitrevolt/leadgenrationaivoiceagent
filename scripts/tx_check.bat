@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del tx.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "echo ---STT-PATH---; journalctl -u leadgen --since '30 minutes ago' --no-pager | grep -aoE 'gemini[^\x22]{0,80}|whisper[^\x22]{0,60}|user: [^\x22]*|bot: [^\x22]*' | tail -16; echo ---TRANSCRIPT-FILES---; ls -la /opt/leadgen/data/call_transcripts/ 2>/dev/null | tail -3; tail -c 600 /opt/leadgen/data/call_transcripts/*.jsonl 2>/dev/null" > tx.log 2>&1
echo TX_DONE
