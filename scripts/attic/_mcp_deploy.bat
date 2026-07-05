@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent
"C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o StrictHostKeyChecking=no root@72.61.245.204 "bash -s" < scripts\_mcp_deploy_remote.sh
