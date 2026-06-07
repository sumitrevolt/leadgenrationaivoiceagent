@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del fs_try.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "docker exec leadgen-freeswitch fs_cli -x 'originate {origination_caller_id_number=+918459012607,origination_caller_id_name=LeadGenAI}sofia/gateway/vobiz/+918459012607 &playback(local_stream://moh)' ; sleep 3 ; docker exec leadgen-freeswitch fs_cli -x 'show calls' | head -5" > fs_try.log 2>&1
echo FT_EXIT_%ERRORLEVEL% >> fs_try.log
echo FT_DONE
