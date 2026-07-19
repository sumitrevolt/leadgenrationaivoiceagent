@echo off
wsl bash -lc "ssh -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no root@72.61.245.204 '/usr/bin/docker ps --format \"{{.Names}} {{.Image}}\" | grep leadgen | sort'"
wsl bash -lc "ssh -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no root@72.61.245.204 '/usr/bin/docker ps --format \"{{.Names}}\" | grep voice_agent || echo no_voice_agent_stray'"
wsl bash -lc "ssh -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no root@72.61.245.204 '/usr/bin/docker exec leadgen_app printenv OMNIROUTE_ENABLED OMNIROUTE_VOICE OMNIROUTE_BASE_URL'"
wsl bash -lc "ssh -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no root@72.61.245.204 '/usr/bin/docker exec leadgen_app python -c \"import os; print(os.getenv(chr(79)+chr(77)+chr(78)+chr(73)+chr(82)+chr(79)+chr(85)+chr(84)+chr(69)+chr(95)+chr(69)+chr(78)+chr(65)+chr(66)+chr(76)+chr(69)+chr(68)))\"'"
