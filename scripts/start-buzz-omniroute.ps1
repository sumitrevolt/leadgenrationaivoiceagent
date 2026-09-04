# start-buzz-omniroute.ps1
# Launch Buzz Desktop with its Claude-harness agents routed through the LOCAL
# OmniRoute gateway (free-provider combo) instead of the Anthropic subscription.
#
#   powershell -ExecutionPolicy Bypass -File scripts\start-buzz-omniroute.ps1            # preview (default)
#   powershell -ExecutionPolicy Bypass -File scripts\start-buzz-omniroute.ps1 -Launch    # actually start Buzz
#
# WHY: scripts/buzz_agent_cost.py measured 591M Claude tokens and a Codex
# subscription peak of 100% in one week. The combo lane is the pressure valve.
#
# SCOPE — read this before trusting it:
#   * Env is set on the SPAWNED PROCESS ONLY. No setx, no [Environment]::Set*,
#     no .env edit. The Buzz Desktop you normally click stays untouched.
#   * This is WORKSPACE-WIDE, not per-agent. Buzz Desktop spawns the harness, so
#     every Claude-harness agent in that instance inherits the routing. Buzz's
#     create-agent form is the only place a per-agent override could live, and
#     the CLI (`buzz agents draft-create`) exposes no env field — so per-agent
#     routing is UNVERIFIED. Do not claim it.
#   * The harness reads ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN / ANTHROPIC_MODEL
#     (confirmed present in claude-agent-acp's dist). That it reads them is not
#     proof Buzz forwards them — hence the -Launch verification step below.
#
# VERIFY AFTER LAUNCH (this is the whole point — a launched app proves nothing):
#   1. @mention an agent in #dev with a resolved mention chip. Plain text that
#      merely looks like a mention does NOT wake a Buzz agent.
#   2. Open the OmniRoute dashboard call log. Traffic there = routing worked.
#      No traffic = Buzz did not forward the env; fall back to the keyboard-tool
#      lane (scripts\start-claude-omniroute.ps1), which IS proven.
#
# Runbook: ~/.buzz/GUIDES/BUZZ_END_TO_END_RUNBOOK.md

param(
    [switch]$Launch,
    [string]$Combo = "leadgen-project-best",
    [string]$BaseUrl = "http://127.0.0.1:20128"
)

$ErrorActionPreference = "Stop"

$ApiBase = "$BaseUrl/v1"
$BuzzDesktop = Join-Path $env:LOCALAPPDATA "Buzz\buzz-desktop.exe"
$StartDev = Join-Path $PSScriptRoot "start-leadgen-dev.ps1"

Write-Output "=== start-buzz-omniroute.ps1 ==="
Write-Output "combo   : $Combo"
Write-Output "endpoint: $ApiBase"
Write-Output ""

# --- Gate 1: the gateway must be genuinely ready, not merely listening -------
# A listening port is not readiness (2026-08-06 lesson). /v1/models answering
# 200 is. A 401 on /api/health means alive-but-auth-protected, not broken.
$ready = $false
try {
    $resp = Invoke-WebRequest -Uri "$ApiBase/models" -TimeoutSec 8 -UseBasicParsing -ErrorAction Stop
    $ready = ($resp.StatusCode -eq 200)
} catch {
    $ready = $false
}

if (-not $ready) {
    Write-Output "OmniRoute is NOT ready at $ApiBase."
    Write-Output ""
    Write-Output "Bring it up first (Docker: Redis + OmniRoute gateway):"
    Write-Output "  powershell -ExecutionPolicy Bypass -File scripts\start-leadgen-dev.ps1"
    Write-Output "  powershell -ExecutionPolicy Bypass -File scripts\omniroute-check.ps1"
    Write-Output ""
    Write-Output "Then re-run this script. Refusing to launch Buzz pointed at a dead"
    Write-Output "endpoint - the agents would fail on every mention with no clear reason."
    exit 2
}
Write-Output "[ok] gateway ready (/v1/models = 200)"

# --- Gate 2: credential ------------------------------------------------------
# Read fresh from the User registry at run time. Never printed, never persisted.
$key = [Environment]::GetEnvironmentVariable('OMNIROUTE_API_KEY', 'User')
if (-not $key) {
    Write-Output "[fail] OMNIROUTE_API_KEY is not set for this user. Set it in the"
    Write-Output "       OmniRoute dashboard, then store it as a User env var."
    exit 3
}
Write-Output "[ok] OMNIROUTE_API_KEY present (value not shown)"
Write-Output "[note] 2026-08-09 smoke: an authenticated combo request returned HTTP 200"
Write-Output "       with a real completion, so the key is accepted. An ANONYMOUS request"
Write-Output "       also succeeded - loopback does not enforce auth. Treat the key as"
Write-Output "       working but not load-bearing, and never expose 20128 beyond loopback."

# --- The process-scoped env block -------------------------------------------
$envBlock = @{
    "ANTHROPIC_BASE_URL"   = $ApiBase
    "ANTHROPIC_AUTH_TOKEN" = "<OMNIROUTE_API_KEY>"
    "ANTHROPIC_MODEL"      = $Combo
}

Write-Output ""
Write-Output "Process-scoped env for the spawned Buzz Desktop:"
foreach ($k in $envBlock.Keys | Sort-Object) {
    Write-Output ("  {0} = {1}" -f $k, $envBlock[$k])
}

if (-not $Launch) {
    Write-Output ""
    Write-Output "PREVIEW ONLY - nothing launched. Re-run with -Launch to start Buzz."
    exit 0
}

# --- Launch ------------------------------------------------------------------
if (-not (Test-Path $BuzzDesktop)) {
    Write-Output "[fail] Buzz Desktop not found at $BuzzDesktop"
    exit 4
}

Write-Output ""
Write-Output "Close any running Buzz Desktop first - a second instance will reuse the"
Write-Output "existing process and silently ignore this env block."
Write-Output ""

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $BuzzDesktop
$psi.UseShellExecute = $false
$psi.EnvironmentVariables["ANTHROPIC_BASE_URL"] = $ApiBase
$psi.EnvironmentVariables["ANTHROPIC_AUTH_TOKEN"] = $key
$psi.EnvironmentVariables["ANTHROPIC_MODEL"] = $Combo
[void][System.Diagnostics.Process]::Start($psi)

Write-Output "[ok] Buzz Desktop launched with process-scoped OmniRoute routing."
Write-Output ""
Write-Output "NOW VERIFY (launching is not evidence):"
Write-Output "  1. @mention an agent in #dev using a resolved mention chip."
Write-Output "  2. Check the OmniRoute call log for that request."
Write-Output "     traffic  -> routing works, combo lane is live."
Write-Output "     no traffic -> Buzz did not forward the env. Use the proven"
Write-Output "                   keyboard lane: scripts\start-claude-omniroute.ps1"
