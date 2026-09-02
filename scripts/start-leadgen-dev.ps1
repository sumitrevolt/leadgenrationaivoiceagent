# start-leadgen-dev.ps1 — one-command local dev bring-up.
# Brings up: WSL Redis broker + gateway-only OmniRoute (Node 22) + verifies Windows venv.
# Dev-only, loopback-only, idempotent. Does NOT touch production, .env, or Docker.
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\start-leadgen-dev.ps1
$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $PSScriptRoot
Write-Host '==================================================='
Write-Host ' LeadGen local dev bring-up (OmniRoute + Redis)'
Write-Host '==================================================='

# 1) WSL side: Redis + OmniRoute tmux (CRLF-stripped, base64-piped for quoting safety)
$sh = Join-Path $PSScriptRoot '_leadgen_dev_up.sh'
if (Test-Path $sh) {
    $script = (Get-Content $sh -Raw) -replace "`r", ""
    $b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($script))
    wsl.exe -d Ubuntu-24.04 --cd ~ -- bash -lc "echo $b64 | base64 -d | bash"
} else {
    Write-Host "MISSING: $sh"
}

# 2) Windows venv sanity
Write-Host ''
Write-Host '== Windows venv =='
$venv = Join-Path $repo '.venv\Scripts\python.exe'
if (Test-Path $venv) {
    & $venv --version
    Write-Host 'verify gate:  .venv\Scripts\python.exe scripts\prod_check.py'
} else {
    Write-Host 'venv missing — create: python -m venv .venv; .venv\Scripts\pip install --no-deps -r requirements.lock.txt'
}

# 3) Summary
Write-Host ''
Write-Host '== Ready =='
Write-Host 'OmniRoute dashboard : http://127.0.0.1:20128   (live-WS 20129 loopback-locked)'
Write-Host 'Redis broker        : 127.0.0.1:6379  (WSL Ubuntu-24.04)'
Write-Host 'Gateway-only tmux   : wsl -d Ubuntu-24.04 -- tmux attach -t leadgen-omni'
Write-Host 'Worktrees are owned by Claude/ChatGPT; providers receive sanitized text only.'
Write-Host ''
Write-Host 'Unity WebGL build (pending USER action): add Windows Defender exclusion for'
Write-Host '  C:\Program Files\Unity\Hub\Editor\2022.3.62f3'
Write-Host 'then:  cd unity\LeadGenVirtualOffice; & "C:\Program Files\Unity\Hub\Editor\2022.3.62f3\Editor\Unity.exe" -batchmode -quit -projectPath . -executeMethod LeadGen.Office.Editor.WebGLBuild.Build -logFile ..\build.log'
