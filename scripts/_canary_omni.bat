@echo off
echo === OMNIROUTE AVAILABLE ===
wsl bash -lc "ssh -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no root@72.61.245.204 '/usr/bin/docker exec leadgen_app python -c \"from app.platform.omniroute_client import omniroute_available; print(omniroute_available())\"'"
echo === GATEWAY HEALTH ===
wsl bash -lc "ssh -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no root@72.61.245.204 '/usr/bin/docker exec leadgen_app python -c \"import urllib.request; r=urllib.request.urlopen(chr(104)+chr(116)+chr(116)+chr(112)+chr(58)+chr(47)+chr(47)+chr(49)+chr(55)+chr(50)+chr(46)+chr(49)+chr(54)+chr(46)+chr(49)+chr(46)+chr(49)+chr(58)+chr(50)+chr(48)+chr(49)+chr(50)+chr(56)+chr(47)+chr(104)+chr(101)+chr(97)+chr(108)+chr(116)+chr(104), timeout=5); print(r.read().decode()[:250])\"' 2>&1"
echo === ALLOWLIST ===
wsl bash -lc "ssh -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no root@72.61.245.204 '/usr/bin/docker exec leadgen_app python -c \"from app.telephony.dial_gate import allowlist, test_mode; print(test_mode(), list(allowlist()))\"'"
echo === IST TIME ===
wsl bash -lc "ssh -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no root@72.61.245.204 'TZ=Asia/Kolkata date'"
