@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del webcall_dbg.log 2>nul

if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add app/api/web_call.py scripts/webcall_debug_deploy.bat > webcall_dbg.log 2>&1
call "%GIT%" commit -m "web-call: surface llm responder failures as warnings" >> webcall_dbg.log 2>&1
call "%GIT%" push origin main >> webcall_dbg.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> webcall_dbg.log

%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && systemctl restart leadgen && sleep 10 && .venv/bin/python - <<'PYEOF' 2>&1 | tail -8
import asyncio, json, aiohttp
async def chat():
    async with aiohttp.ClientSession() as s:
        async with s.ws_connect('http://127.0.0.1:8000/api/web-call/ws', timeout=20) as ws:
            print('ready:', json.loads((await ws.receive()).data).get('responder'))
            await ws.send_json({'type':'start','niche':'solar','flow':'qualify'})
            await ws.receive()
            await ws.send_json({'type':'text','text':'hello'})
            d = json.loads((await asyncio.wait_for(ws.receive(), 40)).data)
            print('BOT:', str(d.get('text'))[:250])
asyncio.run(chat())
PYEOF
echo ---RECENT-WARNINGS--- && journalctl -u leadgen --since '2 minutes ago' --no-pager | grep -iE 'warn|error|fail' | tail -8" >> webcall_dbg.log 2>&1
echo DBG_EXIT_%ERRORLEVEL% >> webcall_dbg.log
echo DBG_DONE
