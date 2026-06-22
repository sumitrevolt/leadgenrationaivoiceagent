@echo off
REM ===========================================================================
REM graphify_refresh.bat - staleness-aware graphify graph refresh (Windows)
REM Compares app\graphify-out\GRAPH_REPORT.md "Built from commit" vs git HEAD.
REM Stale (ya report missing) -> `graphify update app` (FREE, AST-only, incremental).
REM Fresh -> kuch nahi. Prereq: `uv tool install graphifyy` (graphify on PATH).
REM Usage:  scripts\graphify_refresh.bat        (auto: rebuild only if stale)
REM         scripts\graphify_refresh.bat --force (always rebuild)
REM ===========================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0.."
set "REPORT=app\graphify-out\GRAPH_REPORT.md"

for /f "delims=" %%h in ('git rev-parse HEAD 2^>nul') do set "HEADFULL=%%h"
if not defined HEADFULL (
  echo [graphify-refresh] ERROR: git HEAD nahi mila ^(git PATH me hai?^)
  exit /b 1
)
set "HEAD8=!HEADFULL:~0,8!"

set "BUILT="
if exist "%REPORT%" (
  for /f "tokens=2 delims=:" %%a in ('findstr /c:"Built from commit" "%REPORT%"') do set "RAW=%%a"
  if defined RAW (
    set "BUILT=!RAW: =!"
    set "BUILT=!BUILT:`=!"
    set "BUILT=!BUILT:~0,8!"
  )
)

echo [graphify-refresh] HEAD=!HEAD8!  graph_built_from=!BUILT!

if /i "%~1"=="--force" goto :rebuild
if not defined BUILT goto :rebuild
if /i "!HEAD8!"=="!BUILT!" (
  echo [graphify-refresh] graph FRESH - no rebuild needed.
  goto :end
)

:rebuild
echo [graphify-refresh] STALE/forced -^> running: graphify update app
call graphify update app
if errorlevel 1 (
  echo [graphify-refresh] ERROR: graphify update failed ^(installed? `uv tool install graphifyy`^)
  exit /b 1
)
echo [graphify-refresh] done. ^(optional labels: graphify label app --backend=ollama --model=qwen2.5:3b-instruct^)

:end
endlocal
