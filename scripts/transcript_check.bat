@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del transcript.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "journalctl -u leadgen --since '12 minutes ago' --no-pager | grep -aoE 'user: [^\x22]*|bot: [^\x22]*|utterance[^\x22]*|STT [^\x22]*' | tail -24" > transcript.log 2>&1
echo TC_EXIT_%ERRORLEVEL% >> transcript.log
echo TC_DONE
