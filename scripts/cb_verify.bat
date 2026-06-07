@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del cbv.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && echo ---DEPLOYED-MODEL---; grep -n '_CEREBRAS_LLM_MODEL =' app/voice_agent/free_ai.py; echo ---HEAD---; git log -1 --oneline; echo ---CEREBRAS-MODELS-API---; curl -s -m 10 https://api.cerebras.ai/v1/models -H \"Authorization: Bearer $(grep '^CEREBRAS_API_KEY=' .env | cut -d= -f2)\" | head -c 600" > cbv.log 2>&1
echo CBV_EXIT_%ERRORLEVEL% >> cbv.log
echo CBV_DONE
