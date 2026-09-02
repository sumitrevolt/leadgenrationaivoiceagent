# OpenClaw local setup - Owner Copilot (Windows)
# Regenerates config/openclaw/.local from committed templates. Secrets stay local.
# Does NOT enable OPENCLAW on production VPS.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Oc = Join-Path $Root "config\openclaw"
$Local = Join-Path $Oc ".local"
$Plugin = Join-Path $Oc "plugins\leadgen-owner-copilot"

Write-Host "== OpenClaw local setup =="
if (-not (Test-Path $Plugin)) {
  throw "Missing plugin at $Plugin"
}

New-Item -ItemType Directory -Force -Path $Local | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Local "extensions") | Out-Null

$ExtDst = Join-Path $Local "extensions\leadgen-owner-copilot"
if (Test-Path $ExtDst) {
  Remove-Item -Recurse -Force $ExtDst
}
Copy-Item -Recurse -Force $Plugin $ExtDst

$GwSrc = Join-Path $Oc "gateway.openclaw.json5"
$GwDst = Join-Path $Local "openclaw.json"
Copy-Item -Force $GwSrc $GwDst

$absPlugin = ($Plugin -replace '\\', '/')
$json = Get-Content -Raw -Encoding utf8 $GwDst
$json = $json.Replace('"./plugins/leadgen-owner-copilot"', '"' + $absPlugin + '"')
Set-Content -Path $GwDst -Value $json -Encoding utf8

$EnvEx = Join-Path $Oc "env.local.example"
$EnvDst = Join-Path $Local "env.local"
if (-not (Test-Path $EnvDst)) {
  Copy-Item $EnvEx $EnvDst
  Write-Host "Created env.local - fill OPENCLAW_API_TOKEN and OPENCLAW_GATEWAY_TOKEN"
} else {
  Write-Host "Kept existing env.local"
}

Write-Host "OK: plugin synced and openclaw.json written under .local/"
Write-Host "Next steps:"
Write-Host "  1. Edit config/openclaw/.local/env.local tokens"
Write-Host "  2. Local LeadGen .env: OPENCLAW_ENABLED=1 + matching OPENCLAW_API_TOKEN"
Write-Host "  3. OPENCLAW_GATEWAY_ALLOWED_IPS=127.0.0.1,::1"
Write-Host "  4. Start gateway per docs/runbooks/openclaw-owner-copilot.md"
Write-Host "  5. Browser /app/owner Owner Copilot tab"
Write-Host "Prod Stage A: only after owner auth - this script does not touch VPS .env"
