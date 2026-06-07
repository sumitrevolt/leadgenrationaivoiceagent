@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del cid.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && grep -q '^VOBIZ_CALLER_ID=' .env && sed -i 's/^VOBIZ_CALLER_ID=.*/VOBIZ_CALLER_ID=+911171366938/' .env || echo 'VOBIZ_CALLER_ID=+911171366938' >> .env; systemctl restart leadgen && sleep 8 && systemctl is-active leadgen && grep -c VOBIZ_CALLER_ID .env" > cid.log 2>&1
echo CID_EXIT_%ERRORLEVEL% >> cid.log
echo CID_DONE
