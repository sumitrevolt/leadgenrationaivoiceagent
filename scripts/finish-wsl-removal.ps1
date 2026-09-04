# finish-wsl-removal.ps1 — safe, idempotent WSL-removal completion (data-preserving).
#
# WHAT IT DOES (run once on the owner's machine — needs Docker Desktop + WSL access):
#   1. Verifies Docker engine is up.
#   2. Starts the OmniRoute gateway container (adaptive heap).
#   3. Backs up the WSL /root/.omniroute config (provider keys + OAuth connections) into
#      uat_evidence\omniroute_setup\wsl_config_backup\, so nothing is lost if the distro is
#      later removed.
#   4. Verifies the container via `omniroute doctor`.
#   5. Prints the (gated) WSL distro removal command — does NOT auto-run it.
#
# WHY STEP 5 IS GATED: unregistering Ubuntu-24.04 first would permanently delete the only
# copy of the OmniRoute provider/OAuth config (the 2026-07-16 WSL distro-loss incident).
# Confirm step 3 + 4 succeed, then optionally run the printed unregister to free vmmemWSL RAM.
#
# WSL is NOT required to run the LeadGen app — this only tidy up the now-unused Ubuntu distro.

$ErrorActionPreference = 'Continue'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackupDir = Join-Path $RepoRoot 'uat_evidence\omniroute_setup\wsl_config_backup'
$Compose   = Join-Path $RepoRoot 'deploy\compose\docker-compose.omniroute.yml'

function Test-DockerEngine {
    docker version --format '{{.Server.Version}}' *> $null
    return ($LASTEXITCODE -eq 0)
}

Write-Host '=== finish-wsl-removal.ps1 ==='

# --- 1) Docker engine ---------------------------------------------------------
if (-not (Test-DockerEngine)) {
    Write-Host '[FAIL] Docker engine not reachable. Start Docker Desktop, then re-run.'
    Write-Host '       (The LeadGen app still runs with in-memory/fallback; only the'
    Write-Host '        optional OmniRoute + Redis lane needs Docker.)'
    exit 1
}
Write-Host '[ok] Docker engine reachable'

# --- 2) Start gateway --------------------------------------------------------
Write-Host '[1/4] Starting OmniRoute gateway (auto-sized heap)...'
& (Join-Path $PSScriptRoot 'start-omniroute.ps1')

# --- 3) Back up WSL OmniRoute config (data preservation) ---------------------
Write-Host '[2/4] Backing up WSL /root/.omniroute (provider/OAuth config)...'
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$tarball    = Join-Path $BackupDir 'wsl_omniroute_config.tar.gz'
$tarballWsl = ($tarball -replace '^([A-Za-z]):', '/mnt/$1') -replace '\\', '/'
wsl.exe -d Ubuntu-24.04 -- tar -czf "$tarballWsl" -C /root .omniroute 2>$null
if ($LASTEXITCODE -eq 0 -and (Test-Path $tarball)) {
    Write-Host ("[ok] Backed up to {0} ({1:N0} bytes)" -f $tarball, (Get-Item $tarball).Length)
} else {
    Write-Host '[warn] Could not back up WSL config (WSL not running / access denied).'
    Write-Host '       Provider/OAuth re-setup will be needed in the Docker dashboard.'
}

# --- 4) Verify container -----------------------------------------------------
Write-Host '[3/4] Verifying OmniRoute container (omniroute doctor)...'
if (Test-Path $Compose) {
    docker compose -f $Compose exec -T omniroute omniroute doctor 2>&1 | Select-Object -First 30
} else {
    Write-Host '[warn] Compose file not found: ' $Compose
}

# --- 5) Gated unregister -----------------------------------------------------
Write-Host ''
Write-Host '[4/4] WSL distro removal (gated — NOT auto-run).'
Write-Host 'Run the command below ONLY after the backup above exists and the gateway doctor'
Write-Host 'is healthy. This frees the vmmemWSL RAM the unused Ubuntu-24.04 distro held.'
Write-Host '  wsl.exe --unregister Ubuntu-24.04'
Write-Host 'Rollback (if ever needed):  wsl.exe --install -d Ubuntu-24.04  then re-add providers.'

Write-Host ''
Write-Host 'Core LeadGen dev/revenue/deploy does NOT need WSL. See docs/evidence/WSL_REMOVAL_20260826.md.'
