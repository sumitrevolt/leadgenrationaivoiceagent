<#
buzz_local_setup.ps1 — Phase 0: local Buzz relay (block/buzz official prod compose).

Owner decision 2026-08-10: local-first relay (ws://127.0.0.1:3000); VPS relay only
after production proof. Buzz = coordination plane ONLY - never production authority
(commands route via Owner OS/OpenClaw -> 31 runtime STAFF).

Steps: docker check -> shallow clone block/buzz -> .env (random secrets, open local
mode - same posture as `just dev`) -> docker compose up -d (prebuilt
ghcr.io/block/buzz:main image - no Rust build) -> _liveness poll -> next steps.

Usage:
  powershell -ExecutionPolicy Bypass -File scripts\buzz_local_setup.ps1
  powershell -ExecutionPolicy Bypass -File scripts\buzz_local_setup.ps1 -BuzzDir "C:\path\to\buzz"
  powershell -ExecutionPolicy Bypass -File scripts\buzz_local_setup.ps1 -ResetData
Idempotent: re-running keeps the existing clone + .env and just ensures it is up.
-ResetData: `docker compose down -v` before up - use ONLY when data volumes were
initialised against a placeholder .env (relay crashes with "password
authentication failed" for user "buzz" — stale postgres volume).
#>
param([string]$BuzzDir = (Join-Path $HOME "Documents\buzz"), [switch]$ResetData)

$ErrorActionPreference = "Stop"
$ComposeDir = Join-Path $BuzzDir "deploy\compose"

function New-Hex([int]$n) {
  $b = New-Object byte[] $n
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  $rng.GetBytes($b)
  ($b | ForEach-Object { $_.ToString("x2") }) -join ""
}
function New-Pw([int]$n) {
  $b = New-Object byte[] $n
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  $rng.GetBytes($b)
  ([Convert]::ToBase64String($b) -replace '[+/=]', '').Substring(0, $n)
}

# 1. Docker must be running
docker info *> $null
if ($LASTEXITCODE -ne 0) { Write-Error "Docker Desktop is not running - start it first." }
Write-Host "[1/5] Docker OK"

# 2. Clone (shallow) if not present
if (-not (Test-Path (Join-Path $ComposeDir "compose.yml"))) {
  Write-Host "[2/5] Cloning block/buzz (shallow)..."
  git clone --depth 1 https://github.com/block/buzz.git $BuzzDir
  if ($LASTEXITCODE -ne 0) { Write-Error "git clone failed" }
} else {
  Write-Host "[2/5] block/buzz already present at $BuzzDir"
}

# 3. .env - copy if missing, then ALWAYS apply the replacement chain (idempotent:
#    it only touches placeholder/example values, never already-generated secrets)
$envFile = Join-Path $ComposeDir ".env"
if (-not (Test-Path $envFile)) {
  Copy-Item (Join-Path $ComposeDir ".env.example") $envFile
  Write-Host "[3/5] .env created from example"
}
$c = Get-Content $envFile -Raw
$c = $c -replace 'BUZZ_RELAY_PRIVATE_KEY=CHANGE_ME_64_HEX_PRIVATE_KEY', "BUZZ_RELAY_PRIVATE_KEY=$(New-Hex 32)"
$c = $c -replace 'BUZZ_GIT_HOOK_HMAC_SECRET=CHANGE_ME_RANDOM_64_HEX', "BUZZ_GIT_HOOK_HMAC_SECRET=$(New-Hex 32)"
$c = $c -replace 'POSTGRES_PASSWORD=CHANGE_ME_RANDOM_PASSWORD', "POSTGRES_PASSWORD=$(New-Pw 24)"
$c = $c -replace 'REDIS_PASSWORD=CHANGE_ME_RANDOM_PASSWORD', "REDIS_PASSWORD=$(New-Pw 24)"
$c = $c -replace 'BUZZ_S3_ACCESS_KEY=CHANGE_ME_RANDOM_ACCESS_KEY', "BUZZ_S3_ACCESS_KEY=$(New-Pw 24)"
$c = $c -replace 'BUZZ_S3_SECRET_KEY=CHANGE_ME_RANDOM_SECRET_KEY', "BUZZ_S3_SECRET_KEY=$(New-Pw 32)"
# local open mode (like `just dev`): no TLS, no closed-relay requirement yet
$c = $c -replace 'BUZZ_DOMAIN=buzz.example.com', 'BUZZ_DOMAIN=localhost'
$c = $c -replace 'RELAY_URL=wss://buzz.example.com', 'RELAY_URL=ws://127.0.0.1:3100'
$c = $c -replace 'BUZZ_MEDIA_BASE_URL=https://buzz.example.com/media', 'BUZZ_MEDIA_BASE_URL=http://127.0.0.1:3100/media'
$c = $c -replace 'BUZZ_MEDIA_SERVER_DOMAIN=buzz.example.com', 'BUZZ_MEDIA_SERVER_DOMAIN=127.0.0.1'
$c = $c -replace 'BUZZ_CORS_ORIGINS=https://buzz.example.com', 'BUZZ_CORS_ORIGINS=http://127.0.0.1:3100'
$c = $c -replace 'BUZZ_REQUIRE_AUTH_TOKEN=true', 'BUZZ_REQUIRE_AUTH_TOKEN=false'
$c = $c -replace 'BUZZ_REQUIRE_RELAY_MEMBERSHIP=true', 'BUZZ_REQUIRE_RELAY_MEMBERSHIP=false'
$c = $c -replace 'RELAY_OWNER_PUBKEY=CHANGE_ME_OWNER_PUBKEY_HEX', '# RELAY_OWNER_PUBKEY=set from Buzz Desktop identity when hardening (see BUZZ_LOCAL_RELAY.md)'
if ($c -match '=CHANGE_ME') { Write-Error "unresolved CHANGE_ME values still in $envFile - fix manually then re-run" }
Set-Content $envFile $c -Encoding ASCII -NoNewline
Write-Host "[3/5] .env ensured (secrets generated once, open local mode). Back this file up - relay identity lives in it."

# 4. Start relay stack
if ($ResetData) {
  Write-Host "[4/5] -ResetData: wiping buzz data volumes..."
  Push-Location $ComposeDir
  try {
    docker compose down -v
    if ($LASTEXITCODE -ne 0) { Write-Error "docker compose down -v failed" }
  } finally {
    Pop-Location
  }
}
Write-Host "[4/5] docker compose up -d (prebuilt ghcr.io/block/buzz image)..."
Push-Location $ComposeDir
try {
  docker compose up -d
  if ($LASTEXITCODE -ne 0) { Write-Error "docker compose up failed" }
} finally {
  Pop-Location
}

# 5. Liveness poll — community host is 3100 (3000 on 0.0.0.0 often already taken).
$port = 3100
try {
  $line = Select-String -Path $envFile -Pattern '^BUZZ_HTTP_PORT=' | Select-Object -First 1
  # Prefer 3100; only use BUZZ_HTTP_PORT if it is already the loopback mapping.
  if ($line -and $line.Line -match '=3100') { $port = 3100 }
} catch {}
$ok = $false
$deadline = (Get-Date).AddSeconds(120)
Write-Host "[5/5] Waiting for relay health on http://127.0.0.1:$port/_liveness ..."
do {
  Start-Sleep -Seconds 3
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/_liveness" -UseBasicParsing -TimeoutSec 5
    if ($r.StatusCode -eq 200) { $ok = $true }
  } catch {}
} while (-not $ok -and (Get-Date) -lt $deadline)
if (-not $ok) {
  $logs = docker compose -f (Join-Path $ComposeDir "compose.yml") logs --tail 200 relay 2>&1 | Out-String
  if ($logs -match 'password authentication failed') {
    Write-Error "STALE DATA VOLUMES: postgres was initialised against a placeholder .env. Re-run with: -ResetData"
  }
  Write-Error "relay not healthy within 120s. Logs: docker compose -f $ComposeDir\compose.yml logs --tail 100 relay"
}

Write-Host "Buzz relay LIVE at ws://127.0.0.1:$port"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Buzz Desktop -> settings/relay -> ws://127.0.0.1:$port (reuse existing identity)"
Write-Host "  2. Point tooling at the local relay (user-level env var, read by buzzlock.py /"
Write-Host "     buzz_staff_pulse.py / buzz_mcp.py):"
Write-Host "       setx BUZZ_RELAY ws://127.0.0.1:$port"
Write-Host "  3. Onboarding + Boss read-only verification: docs/integrations/BUZZ_LOCAL_RELAY.md"
Write-Host "  4. Stop (data stays in volumes):"
Write-Host "       docker compose -f $ComposeDir\compose.yml down"
Write-Host "  WARNING: relay signing key = BUZZ_RELAY_PRIVATE_KEY in $envFile - back it up."
