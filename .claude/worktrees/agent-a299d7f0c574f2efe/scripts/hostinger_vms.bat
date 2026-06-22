@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaiagent
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
del /q scripts\hostinger_vms.log 2>nul
%SSH% -i %KEY% -o BatchMode=yes -o ConnectTimeout=20 root@72.61.245.204 "echo Y2QgL29wdC9sZWFkZ2VuClRPS0VOPSQoZ3JlcCAtRSAnXkhPU1RJTkdFUl9BUElfVE9LRU49JyAuZW52IHwgY3V0IC1kPSAtZjItIHwgdHIgLWQgJyInIHwgdHIgLWQgIiciKQppZiBbIC16ICIkVE9LRU4iIF07IHRoZW4gZWNobyAiTk9fVE9LRU4iOyBleGl0IDA7IGZpCmVjaG8gIlRPS0VOX0xFTiAkeyNUT0tFTn0iCmN1cmwgLXMgLUggIkF1dGhvcml6YXRpb246IEJlYXJlciAkVE9LRU4iIC1IICJVc2VyLUFnZW50OiBNb3ppbGxhLzUuMCAoWDExOyBMaW51eCB4ODZfNjQpIiAiaHR0cHM6Ly9kZXZlbG9wZXJzLmhvc3Rpbmdlci5jb20vYXBpL3Zwcy92MS92aXJ0dWFsLW1hY2hpbmVzIiB8IGhlYWQgLWMgMTUwMAplY2hvCmVjaG8gVk1TX0RPTkUK | base64 -d | bash" > scripts\hostinger_vms.log 2>&1
echo BAT_EXIT_%ERRORLEVEL% >> scripts\hostinger_vms.log
echo BATDONE
