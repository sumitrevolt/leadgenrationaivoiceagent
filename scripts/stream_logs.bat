@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del stream_logs.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "journalctl -u leadgen --since '6 minutes ago' --no-pager | grep -aoE 'vobiz-stream[^\x22]*|bot:[^\x22]*|user:[^\x22]*|TTS synth failed[^\x22]*|playback error[^\x22]*' | tail -30" > stream_logs.log 2>&1
echo SL_EXIT_%ERRORLEVEL% >> stream_logs.log
echo SL_DONE
