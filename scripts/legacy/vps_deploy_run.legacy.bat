@echo off
cd /d "%~dp0.."
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del deploy_run.log 2>nul

echo === SSH connectivity === > deploy_run.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new root@72.61.245.204 "echo SSH_OK && hostname && cd /opt/leadgen && git log --oneline -1" >> deploy_run.log 2>&1
echo SSH_TEST_EXIT_%ERRORLEVEL% >> deploy_run.log

echo === DEPLOY (git pull + script) === >> deploy_run.log
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=15 root@72.61.245.204 "curl -fsSL https://raw.githubusercontent.com/sumitrevolt/leadgenrationaivoiceagent/main/deploy_vps.sh | bash" >> deploy_run.log 2>&1
echo DEPLOY_EXIT_%ERRORLEVEL% >> deploy_run.log
echo DEPLOY_DONE
