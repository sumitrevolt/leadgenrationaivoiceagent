@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_dns.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes root@72.61.245.204
echo === .env var NAMES (no values) matching hostinger/api/dns/domain === > %LOG%
call %SSH% "grep -oiE '^[A-Za-z0-9_]+' /opt/leadgen/.env | grep -iE 'hostinger|hpanel|dns|domain|api_token' | sort -u" >> %LOG% 2>&1
echo === MX === >> %LOG%
call %SSH% "dig +short MX leadsgenai.in" >> %LOG% 2>&1
echo === DKIM selectors (Hostinger uses CNAME) === >> %LOG%
call %SSH% "dig +short CNAME hostingermail-a._domainkey.leadsgenai.in" >> %LOG% 2>&1
call %SSH% "dig +short CNAME hostingermail-b._domainkey.leadsgenai.in" >> %LOG% 2>&1
call %SSH% "dig +short CNAME hostingermail-c._domainkey.leadsgenai.in" >> %LOG% 2>&1
call %SSH% "dig +short TXT hostingermail-a._domainkey.leadsgenai.in" >> %LOG% 2>&1
echo === DONE === >> %LOG%
