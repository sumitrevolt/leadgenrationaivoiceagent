@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
if not exist docs\page_kits mkdir docs\page_kits
%SSH% -i %KEY% -o BatchMode=yes root@72.61.245.204 "cat /opt/leadgen/data/page_kits/leadsgenai.md" > docs\page_kits\LeadsGenAI_social_pages_kit.md 2>nul
%SSH% -i %KEY% -o BatchMode=yes root@72.61.245.204 "cat /opt/leadgen/data/page_kits/sharma_solar.md" > docs\page_kits\SAMPLE_client_Sharma_Solar_kit.md 2>nul
echo FETCHED
