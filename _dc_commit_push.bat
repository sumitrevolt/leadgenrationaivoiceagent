@echo off
set GIT_TERMINAL_PROMPT=0
cd /d C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent
set GIT=C:\PROGRA~1\Git\cmd\git.exe
for /L %%i in (1,1,40) do (
  if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
  "%GIT%" add -A >nul 2>&1
  "%GIT%" commit -m "feat: production voice agent + dashboards + website/PWA + automation + deploy configs + Gemini wired + bug fixes" >_commit_out.txt 2>&1
  if not errorlevel 1 goto committed
  timeout /t 1 /nobreak >nul
)
echo ===COMMIT_FAILED===
type _commit_out.txt
goto end
:committed
echo ===COMMITTED===
"%GIT%" log -1 --oneline
echo ===PUSHING===
for /L %%j in (1,1,20) do (
  "%GIT%" push origin main >_push_out.txt 2>&1
  if not errorlevel 1 goto pushed
  timeout /t 2 /nobreak >nul
)
echo ===PUSH_FAILED===
type _push_out.txt
goto end
:pushed
echo ===PUSHED_OK===
type _push_out.txt
:end
