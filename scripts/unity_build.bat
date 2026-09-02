@echo off
REM Unity WebGL build pipeline — generate scenes → EditMode tests → build → copy to static dir.
REM Evidence: uat_evidence\unity_*.log + unity_editmode_results.xml + UNITY_SENTINEL.txt
setlocal
set REPO=C:\Users\Ratanshila\Documents\leadgenrationaiagent
set PROJ=%REPO%\unity\LeadGenVirtualOffice
set EV=%REPO%\uat_evidence
set UNITY=C:\Program Files\Unity\Hub\Editor\2022.3.62f3\Editor\Unity.exe
cd /d %REPO%
if not exist "%EV%" mkdir "%EV%"
del /q "%EV%\UNITY_SENTINEL.txt" 2>nul

set ELOG=%EV%\unity_env.log
echo ===UNITY_EXE=== > "%ELOG%"
if exist "%UNITY%" (echo UNITY_EXE_FOUND >> "%ELOG%") else (echo UNITY_EXE_MISSING >> "%ELOG%")
echo ===WEBGL_MODULE=== >> "%ELOG%"
if exist "C:\Program Files\Unity\Hub\Editor\2022.3.62f3\Editor\Data\PlaybackEngines\WebGLSupport" (echo WEBGL_MODULE_FOUND >> "%ELOG%") else (echo WEBGL_MODULE_MISSING >> "%ELOG%")
echo ===MODULES_DIR=== >> "%ELOG%"
dir /b "C:\Program Files\Unity\Hub\Editor\2022.3.62f3\Editor\Data\PlaybackEngines" >> "%ELOG%" 2>&1

echo ===STEP1_GENERATE=== >> "%ELOG%"
"%UNITY%" -batchmode -quit -projectPath "%PROJ%" -executeMethod LeadGen.Office.Editor.GenerateOfficeScenes.Generate -logFile "%EV%\unity_generate.log"
echo EXIT_GENERATE=%ERRORLEVEL% >> "%ELOG%"

echo ===STEP2_EDITMODE_TESTS=== >> "%ELOG%"
"%UNITY%" -batchmode -projectPath "%PROJ%" -runTests -testPlatform EditMode -testResults "%EV%\unity_editmode_results.xml" -logFile "%EV%\unity_tests.log"
echo EXIT_TESTS=%ERRORLEVEL% >> "%ELOG%"

echo ===STEP3_WEBGL_BUILD=== >> "%ELOG%"
"%UNITY%" -batchmode -quit -projectPath "%PROJ%" -executeMethod LeadGen.Office.Editor.WebGLBuild.Build -logFile "%EV%\unity_build.log"
echo EXIT_BUILD=%ERRORLEVEL% >> "%ELOG%"

echo ===STEP4_COPY_STATIC=== >> "%ELOG%"
if exist "%PROJ%\Build\Build" (
  robocopy "%PROJ%\Build\Build" "%REPO%\frontend\office_unity\Build" /MIR >> "%ELOG%" 2>&1
  echo ROBOCOPY_EXIT=%ERRORLEVEL% >> "%ELOG%"
) else (
  if exist "%PROJ%\Build" (
    robocopy "%PROJ%\Build" "%REPO%\frontend\office_unity\BuildRoot" /MIR >> "%ELOG%" 2>&1
    echo ROBOCOPY_ROOT_EXIT=%ERRORLEVEL% >> "%ELOG%"
  ) else (
    echo NO_BUILD_OUTPUT >> "%ELOG%"
  )
)
echo ===BUILD_DIR_LISTING=== >> "%ELOG%"
dir /s "%PROJ%\Build" >> "%ELOG%" 2>&1

echo UNITY_PIPELINE_DONE > "%EV%\UNITY_SENTINEL.txt"
endlocal
exit
