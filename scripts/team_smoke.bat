@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del tsmoke.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "cd /opt/leadgen && timeout 90 env PYTHONPATH=/opt/leadgen .venv/bin/python -c \"import asyncio; from app.agents import staff; from app.platform import team; r=asyncio.run(staff.run_ops()); print('OPS:', str(r)[:200]); m=asyncio.run(staff.run_trainer()); print('TRAINER:', str(m)[:200]); from app.marketing.post_generator import gbp_tips; print('TIPS:', len(gbp_tips('solar_residential'))); st=team.team_status(); print('TEAM members:', len(st['members']), 'actions today:', st['totals']['actions_today']); ev=team.recent_events(5); print('FEED:', [(e['name'], e['action']) for e in ev])\" 2>&1 | grep -aE 'OPS:|TRAINER:|TIPS:|TEAM|FEED:'" > tsmoke.log 2>&1
echo SMOKE_EXIT_%ERRORLEVEL% >> tsmoke.log
echo SMOKE_DONE
