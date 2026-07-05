@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent
"C:\PROGRA~1\Git\cmd\git.exe" commit -F scripts\_mcp_commit_msg.txt
echo --- after commit ---
"C:\PROGRA~1\Git\cmd\git.exe" log -1 --oneline
