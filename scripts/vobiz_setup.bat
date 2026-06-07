@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del vobiz_setup.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && grep -q '^VOBIZ_AUTH_ID=' .env || printf '\nVOBIZ_AUTH_ID=MA_RVP4WSNO\nVOBIZ_AUTH_TOKEN=1InaWpSsS2tR4pdaSwirZRh0sq2YNiyhlsgrNTjISXC5Qty3zKuUMPHqDFdwZowm\nTELEPHONY_TRUNK=vobiz\n' >> .env; grep -c '^VOBIZ' .env; echo ---REGION---; curl -s -m 8 https://ipinfo.io/72.61.245.204/json | head -c 300; echo; echo ---DOCKER---; command -v docker >/dev/null && docker --version" > vobiz_setup.log 2>&1
echo VS_EXIT_%ERRORLEVEL% >> vobiz_setup.log
echo VS_DONE
