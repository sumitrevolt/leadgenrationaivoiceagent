@echo off
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set LOG=cowork_envcheck.log
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa -o BatchMode=yes root@72.61.245.204
echo === systemd unit (EnvironmentFile? ExecStart?) === > %LOG%
call %SSH% "systemctl cat leadgen 2>/dev/null | grep -iE 'environment|execstart|workingdir'" >> %LOG% 2>&1
echo === config.py env loading === >> %LOG%
call %SSH% "grep -nE 'env_file|model_config|class Config|SettingsConfigDict' /opt/leadgen/app/config.py | head -8" >> %LOG% 2>&1
echo === DONE === >> %LOG%
