<#
.SYNOPSIS
  Reproducibly deploy a Unity WebGL build into the LeadGen frontend serving path.

.DESCRIPTION
  Unity emits <src>/index.html + <src>/Build/<leaf>.{loader.js,data.br,framework.js.br,
  wasm.br} (+ optional .symbols.json.br) + TemplateData/ + StreamingAssets/. The office
  shell (frontend/office_blueprint.html) fetches, FLAT:
     /static/office-unity/Build/<BUILD_NAME>.{loader.js,data.br,framework.js.br,wasm.br}
  This script flattens + renames the nested artifacts to <BUILD_NAME>.* so no manual step
  is needed after a rebuild. It enforces the compressed budget, removes stale artifacts,
  is idempotent, supports -DryRun, fails fast, and verifies the shell references the files
  it produced. Exit code is 0 on success, non-zero on any failure.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\deploy-unity-build.ps1 -DryRun
  powershell -ExecutionPolicy Bypass -File scripts\deploy-unity-build.ps1
#>
[CmdletBinding()]
param(
    [string]$SourceDir,
    [string]$DestDir,
    [string]$Name = "LeadGenVirtualOffice",
    [double]$BudgetMB = 12,
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
function Fail($m) { Write-Host "[FAIL] $m" -ForegroundColor Red; exit 1 }
function Info($m) { Write-Host "[deploy-unity] $m" }

$repo = Split-Path -Parent $PSScriptRoot
if (-not $SourceDir) { $SourceDir = Join-Path $repo 'unity\LeadGenVirtualOffice\Build' }
if (-not $DestDir)   { $DestDir   = Join-Path $repo 'frontend\office_unity\Build' }
$shellPath = Join-Path $repo 'frontend\office_blueprint.html'

Info "Source : $SourceDir"
Info "Dest   : $DestDir"
Info "Name=$Name  Budget=${BudgetMB}MB  DryRun=$($DryRun.IsPresent)"
if (-not (Test-Path $SourceDir)) { Fail "Source dir not found: $SourceDir" }
if (-not (Test-Path $shellPath)) { Fail "Shell not found: $shellPath" }

# Artifact suffixes -> target names. loader/data/framework/wasm are mandatory.
$specs = @(
    @{ Suffix = 'loader.js';       Mandatory = $true  }
    @{ Suffix = 'data.br';         Mandatory = $true  }
    @{ Suffix = 'framework.js.br'; Mandatory = $true  }
    @{ Suffix = 'wasm.br';         Mandatory = $true  }
    @{ Suffix = 'symbols.json.br'; Mandatory = $false }
)

function Find-Artifact([string]$suffix) {
    Get-ChildItem -Path $SourceDir -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name.ToLower().EndsWith("." + $suffix.ToLower()) -and $_.Name -notlike "$Name.*" } |
        Sort-Object Length -Descending | Select-Object -First 1
}

$plan = @()
foreach ($spec in $specs) {
    $f = Find-Artifact $spec.Suffix
    if (-not $f) {
        if ($spec.Mandatory) { Fail "Mandatory artifact *.$($spec.Suffix) not found under $SourceDir" }
        Info "optional *.$($spec.Suffix) absent - skipping"; continue
    }
    $plan += [pscustomobject]@{
        Suffix = $spec.Suffix; Src = $f.FullName; Target = "$Name.$($spec.Suffix)";
        Bytes = $f.Length; IsBr = $spec.Suffix.ToLower().EndsWith('.br')
    }
}

# Compressed-asset budget (the .br payload the browser downloads).
$brBytes = ($plan | Where-Object { $_.IsBr } | Measure-Object Bytes -Sum).Sum
$brMB = [math]::Round($brBytes / 1MB, 2)
Info "Compressed (.br) payload: ${brMB}MB (budget ${BudgetMB}MB)"
if ($brMB -gt $BudgetMB) { Fail "Compressed budget exceeded: ${brMB}MB > ${BudgetMB}MB" }

Info "Planned artifacts:"
foreach ($p in $plan) {
    Info ("  {0,-28} <- {1}  ({2} KB)" -f $p.Target, (Split-Path $p.Src -Leaf), [math]::Round($p.Bytes / 1KB, 1))
}

if ($DryRun) {
    Info "DRY-RUN: no files written."
} else {
    New-Item -ItemType Directory -Force -Path $DestDir | Out-Null
    # Remove stale deployed artifacts (previous <Name>.* + Unity's own index.html/TemplateData;
    # the shell provides its own HTML/canvas, so those are not served).
    Get-ChildItem -Path $DestDir -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "$Name.*" } | ForEach-Object { Remove-Item $_.FullName -Force }
    foreach ($stale in @('index.html', 'TemplateData')) {
        $sp = Join-Path $DestDir $stale
        if (Test-Path $sp) { Remove-Item $sp -Recurse -Force }
    }
    foreach ($p in $plan) { Copy-Item -LiteralPath $p.Src -Destination (Join-Path $DestDir $p.Target) -Force }
    # Mirror StreamingAssets if Unity produced it (runtime config; idempotent).
    $srcSA = Join-Path $SourceDir 'StreamingAssets'
    if (Test-Path $srcSA) {
        $dstSA = Join-Path $DestDir 'StreamingAssets'
        if (Test-Path $dstSA) { Remove-Item $dstSA -Recurse -Force }
        Copy-Item $srcSA $dstSA -Recurse -Force
    }
    Info "Deployed to $DestDir"
}

# Verify the office shell references exactly what we produced.
$shellTxt = Get-Content $shellPath -Raw
$mBase = [regex]::Match($shellTxt, 'BUILD_BASE\s*=\s*"([^"]+)"')
$mName = [regex]::Match($shellTxt, 'BUILD_NAME\s*=\s*"([^"]+)"')
if (-not $mBase.Success -or -not $mName.Success) { Fail "Cannot parse BUILD_BASE/BUILD_NAME from shell" }
$shellBase = $mBase.Groups[1].Value
$shellName = $mName.Groups[1].Value
Info "Shell contract: BUILD_BASE=$shellBase  BUILD_NAME=$shellName"
if ($shellName -ne $Name) { Fail "Shell BUILD_NAME '$shellName' != deploy Name '$Name' - office would 404" }

$reqSuffixes = @('loader.js', 'data.br', 'framework.js.br', 'wasm.br')
$missing = @()
foreach ($s in $reqSuffixes) {
    $rel = "$shellBase/$shellName.$s"
    $onDisk = Join-Path $DestDir "$shellName.$s"
    if ($DryRun) {
        Info "  shell will GET $rel  (planned)"
    } elseif (-not (Test-Path $onDisk)) {
        $missing += "$shellName.$s"
    } else {
        Info ("  OK  {0}  ({1} KB)" -f $rel, [math]::Round((Get-Item $onDisk).Length / 1KB, 1))
    }
}
if ($missing.Count -gt 0) { Fail "Shell-referenced files missing after deploy: $($missing -join ', ')" }

Info "SUCCESS: Unity build matches office_blueprint.html contract."
exit 0
