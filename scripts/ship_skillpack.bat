@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent
del /q pytest_new.log 2>nul
set GIT=C:\PROGRA~1\Git\cmd\git.exe
%GIT% add docs/AUTONOMOUS_INFRA_DESIGN.md app/platform/skill_pack.py app/agents/code_upgrader.py app/platform/team.py app/agents/self_improve.py app/platform/team_scheduler.py app/api/growth.py tests/test_skill_pack_upgrader.py scripts/ship_skillpack.bat > scripts\ship_skillpack.log 2>&1
%GIT% commit -m "skill pack to vps agents, code upgrader hybrid autonomy, vikram guru staff, scheduler wiring" >> scripts\ship_skillpack.log 2>&1
%GIT% push origin main >> scripts\ship_skillpack.log 2>&1
%GIT% log -1 --oneline >> scripts\ship_skillpack.log 2>&1
echo DONE >> scripts\ship_skillpack.log
