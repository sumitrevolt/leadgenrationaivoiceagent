@echo off
setlocal
set SSH=C:\PROGRA~1\Git\usr\bin\ssh.exe
set KEY=C:\Users\Ratanshila\.ssh\id_rsa
set HOST=root@72.61.245.204

for %%J in (qa trainer pipeline) do (
  echo === Trigger %%J ===
  "%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "docker exec leadgen_app python -c \"from app.tasks.staff_jobs import run_staff_job; r=run_staff_job.delay('%%J'); print(r.id)\""
)
exit /b 0
