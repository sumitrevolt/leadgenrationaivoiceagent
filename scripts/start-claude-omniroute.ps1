# start-claude-omniroute.ps1
# Launches Windows-native Claude Code through the local OmniRoute gateway, using a
# SEPARATE profile/env-block - never touches the normal C:\Users\Ratanshila\.claude\
# config, never modifies user-level/system env vars, never prints a credential.
#
# Usage:
#   powershell -File scripts\start-claude-omniroute.ps1 -DryRun     # preview only, no launch
#   powershell -File scripts\start-claude-omniroute.ps1             # real launch
#
# Design notes (2026-07-13 audit):
# - OmniRoute's OpenAI/Anthropic-compatible endpoint is http://127.0.0.1:20128/v1
#   (confirmed via dashboard Endpoints page).
# - Claude Code (Windows-native, C:\Users\Ratanshila\.local\bin\claude.exe) honors
#   ANTHROPIC_BASE_URL / ANTHROPIC_API_KEY env vars for a custom-gateway target.
#   We set these ONLY on the child process we spawn - never via setx/[Environment]::
#   SetEnvironmentVariable, so the normal claude command Sumit types stays 100%
#   unaffected. --bare mode is used for -Prompt runs: it forces auth to come
#   strictly from ANTHROPIC_API_KEY (never OAuth/keychain), guaranteeing this test
#   cannot accidentally touch Sumit's real Claude subscription session.
# - The OmniRoute API key is read fresh from the Windows User registry at run time
#   (never hard-coded, never echoed to stdout/logs).

param(
    [switch]$DryRun,
    [string]$Prompt,
    [string]$Model,
    [string]$Combo = "leadgen.coding_primary",
    [string]$OmniHost = "127.0.0.1",
    [int]$Port = 20128
)

$ErrorActionPreference = "Stop"
$OmniRouteUrl = "http://${OmniHost}:${Port}"
$OmniRouteApiBase = "$OmniRouteUrl/v1"
$ClaudeExe = "C:\Users\Ratanshila\.local\bin\claude.exe"
$StartScript = Join-Path $PSScriptRoot "start-omniroute.ps1"

function Test-OmniRouteHealth {
    try {
        $resp = Invoke-WebRequest -Uri "$OmniRouteUrl/api/health" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        return $true
    } catch {
        # A 401 still proves the server is up and answering (auth-protected but alive).
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode.value__ -eq 401) {
            return $true
        }
        return $false
    }
}

Write-Output "=== start-claude-omniroute.ps1 ==="
Write-Output "Checking OmniRoute at $OmniRouteUrl ..."

$healthy = Test-OmniRouteHealth
if (-not $healthy) {
    Write-Output "OmniRoute not responding. Attempting to start it (idempotent) ..."
    if (-not $DryRun) {
        if (-not (Test-Path $StartScript)) {
            Write-Output "ERROR: start-omniroute.ps1 not found at $StartScript"
            exit 1
        }
        & powershell -File $StartScript
        Start-Sleep -Seconds 3
        $healthy = Test-OmniRouteHealth
    } else {
        Write-Output "[DRY RUN] Would run: powershell -File $StartScript"
    }
}

if (-not $healthy -and -not $DryRun) {
    Write-Output "ERROR: OmniRoute still unreachable after start attempt. Aborting - will not launch Claude Code without a working gateway. See uat_evidence\omniroute_setup\ for diagnostics."
    exit 1
}

Write-Output "OmniRoute reachable: OK"

# Read the client API key fresh from the Windows User registry (never printed).
$apiKey = [Environment]::GetEnvironmentVariable("OMNIROUTE_API_KEY", "User")
if (-not $apiKey) {
    Write-Output "ERROR: OMNIROUTE_API_KEY not set in your Windows User environment variables."
    Write-Output "Fix: generate a client API key in the OmniRoute dashboard (API Keys page), then run:"
    Write-Output "  setx OMNIROUTE_API_KEY YOUR_VALUE_HERE"
    Write-Output "Run this yourself - this script and Claude will never ask you to paste it here."
    exit 1
}

Write-Output "OmniRoute client key: found (not displayed)."
Write-Output ""
Write-Output "Target base URL for this launch: $OmniRouteApiBase"
Write-Output "This profile is SEPARATE from your normal Claude Code config - your usual"
Write-Output "claude command is completely unaffected by this script."
Write-Output ""

if ($DryRun) {
    Write-Output "[DRY RUN] Would launch (env vars set only for this child process, not persisted):"
    Write-Output "  ANTHROPIC_BASE_URL = $OmniRouteApiBase"
    Write-Output "  ANTHROPIC_API_KEY  = REDACTED (value read from OMNIROUTE_API_KEY)"
    Write-Output "  Executable          = $ClaudeExe"
    if ($Prompt) {
        Write-Output "  Mode                = one-shot (--print --bare), model=$Model"
        Write-Output "  Prompt              = $Prompt"
    } else {
        Write-Output "  Mode                = interactive session"
    }
    Write-Output "No process was started. Re-run without -DryRun to actually launch."
    exit 0
}

if (-not (Test-Path $ClaudeExe)) {
    Write-Output "ERROR: Claude Code executable not found at $ClaudeExe"
    Write-Output "Normal Claude launch is unaffected; only this OmniRoute-routed launch is blocked."
    exit 1
}

# Launch Claude Code with the OmniRoute routing env vars scoped to THIS process only.
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $ClaudeExe
$psi.UseShellExecute = $false
$targetModel = if ($Model) { $Model } else { $Combo }
$psi.EnvironmentVariables["ANTHROPIC_BASE_URL"] = $OmniRouteApiBase
$psi.EnvironmentVariables["ANTHROPIC_API_KEY"] = $apiKey
$psi.EnvironmentVariables["ANTHROPIC_MODEL"] = $targetModel

if ($Prompt) {
    # One-shot, non-interactive, isolated test run.
    # Windows PowerShell 5.1's ProcessStartInfo.ArgumentList is unreliable (null),
    # so build a properly quoted Arguments string instead.
    function Quote-Arg([string]$a) {
        return '"' + ($a -replace '"', '\"') + '"'
    }
    $argParts = @("--print", "--bare")
    if ($Model) { $argParts += @("--model", (Quote-Arg $Model)) }
    $argParts += (Quote-Arg $Prompt)
    $psi.Arguments = ($argParts -join " ")
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true

    try {
        $proc = [System.Diagnostics.Process]::Start($psi)
        $stdout = $proc.StandardOutput.ReadToEnd()
        $stderr = $proc.StandardError.ReadToEnd()
        $proc.WaitForExit()
        Write-Output "=== CLAUDE CODE OUTPUT (via OmniRoute) ==="
        Write-Output $stdout
        if ($stderr) { Write-Output "=== STDERR ==="; Write-Output $stderr }
        Write-Output ("=== EXIT CODE: " + $proc.ExitCode + " ===")
    } catch {
        Write-Output ("ERROR launching Claude Code: " + $_.Exception.Message)
        exit 1
    }
} else {
    try {
        $proc = [System.Diagnostics.Process]::Start($psi)
        Write-Output "Launched Claude Code via OmniRoute (PID $($proc.Id))."
    } catch {
        Write-Output ("ERROR launching Claude Code: " + $_.Exception.Message)
        exit 1
    }
}
