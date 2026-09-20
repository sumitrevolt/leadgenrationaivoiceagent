param(
    [switch]$SkipVps
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$msysShell = "C:\msys64\msys2_shell.cmd"
$msysBash = "C:\msys64\usr\bin\bash.exe"
$gitSsh = "C:\Program Files\Git\usr\bin\ssh.exe"
$sshKey = Join-Path $env:USERPROFILE ".ssh\id_rsa"

function Check-Path($label, $path) {
    if (Test-Path $path) {
        Write-Host "[OK] ${label}: $path"
        return $true
    }
    Write-Host "[MISS] ${label}: $path"
    return $false
}

function Check-Command($label, $command) {
    $found = Get-Command $command -ErrorAction SilentlyContinue
    if ($found) {
        Write-Host "[OK] ${label}: $($found.Source)"
        return $true
    }
    Write-Host "[MISS] ${label}: $command not on PATH"
    return $false
}

$ok = $true
$ok = (Check-Path "repo" $root) -and $ok
$ok = (Check-Path "MSYS2 launcher" $msysShell) -and $ok
$ok = (Check-Path "MSYS2 bash" $msysBash) -and $ok
$ok = (Check-Path "Git SSH" $gitSsh) -and $ok
$ok = (Check-Path "SSH key" $sshKey) -and $ok
$ok = (Check-Command "graphify" "graphify") -and $ok
$ok = (Check-Command "graphify-mcp" "graphify-mcp") -and $ok

if (Test-Path $msysBash) {
    & $msysBash -lc "command -v tmux >/dev/null && tmux -V"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] tmux available in MSYS2"
    } else {
        Write-Host "[MISS] tmux not available in MSYS2. Run: C:\msys64\usr\bin\pacman.exe -Sy --noconfirm tmux"
        $ok = $false
    }

    & $msysBash -n (Join-Path $root "leadgen-tmux-setup.sh")
    if ($LASTEXITCODE -eq 0) { Write-Host "[OK] leadgen-tmux-setup.sh syntax" } else { $ok = $false }

    & $msysBash -n (Join-Path $root "leadgen-vps.sh")
    if ($LASTEXITCODE -eq 0) { Write-Host "[OK] leadgen-vps.sh syntax" } else { $ok = $false }
}

if (-not $SkipVps -and (Test-Path $gitSsh) -and (Test-Path $sshKey)) {
    & $gitSsh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=12 -i $sshKey root@72.61.245.204 "cd /opt/leadgen && docker compose -f docker-compose.vps.yml ps app worker worker-heavy scheduler --status running --format '{{.Name}} {{.Status}}'"
    if ($LASTEXITCODE -eq 0) { Write-Host "[OK] VPS docker compose reachable" } else { $ok = $false }
}

if ($ok) {
    Write-Host ""
    Write-Host "LeadGen operator cockpit setup: OK"
    exit 0
}

Write-Host ""
Write-Host "LeadGen operator cockpit setup: INCOMPLETE"
exit 1
