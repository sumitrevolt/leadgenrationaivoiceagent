@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_seo.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes root@72.61.245.204
echo === SEO markers count (og:title / ld+json / lucide) === > %LOG%
call %SSH% "curl -s http://127.0.0.1:8000/ | grep -c -E 'og:title|application/ld|jsdelivr.net/npm/lucide'" >> %LOG% 2>&1
echo === FAQPage schema present? === >> %LOG%
call %SSH% "curl -s http://127.0.0.1:8000/ | grep -c FAQPage" >> %LOG% 2>&1
echo === DONE === >> %LOG%
