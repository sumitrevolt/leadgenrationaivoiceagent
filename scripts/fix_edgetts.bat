@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del fix_edgetts.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=25 root@72.61.245.204 "cd /opt/leadgen && .venv/bin/pip install -U -q edge-tts 2>&1 | tail -2; .venv/bin/python -c 'import edge_tts; print(\"edge-tts\", edge_tts.__version__)'; echo ---TTS-SELFTEST---; .venv/bin/python -c \"import asyncio,edge_tts;
async def t():
 c=edge_tts.Communicate('Namaste, yeh ek test hai','hi-IN-SwaraNeural'); n=0
 async for ch in c.stream():
  if ch.get('type')=='audio': n+=len(ch.get('data') or b'')
 print('audio bytes:',n)
asyncio.run(t())\"; systemctl restart leadgen && sleep 12 && systemctl is-active leadgen" > fix_edgetts.log 2>&1
echo FE_EXIT_%ERRORLEVEL% >> fix_edgetts.log
echo FE_DONE
