@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_p3test.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@72.61.245.204
echo === check_rag (semantic RAG verify) === > %LOG%
call %SSH% "cd /opt/leadgen && PYTHONPATH=. .venv/bin/python scripts/check_rag.py 2>&1 | tail -15" >> %LOG% 2>&1
echo === agent_tester (free voice scorecard) === >> %LOG%
call %SSH% "cd /opt/leadgen && PYTHONPATH=. .venv/bin/python scripts/agent_tester.py 2>&1 | tail -30" >> %LOG% 2>&1
echo === DONE === >> %LOG%
