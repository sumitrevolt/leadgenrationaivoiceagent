# Trusted operator wrapper: creates one isolated worktree for Claude/ChatGPT.
# It never invokes an external model, applies a patch, commits, pushes, or deploys.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9][a-z0-9-]{2,48}$')]
    [string]$TaskId,

    [ValidateSet('claude', 'chatgpt')]
    [string]$Governor = 'claude',

    [ValidatePattern('^[A-Za-z0-9._/-]{1,180}$')]
    [string]$BaseRef = 'HEAD',

    [string]$WorktreeRoot = '',

    [switch]$PlanOnly
)

$ErrorActionPreference = 'Stop'
$repoText = (& git rev-parse --show-toplevel 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $repoText) {
    throw 'Run this wrapper inside the trusted LeadGen Git checkout.'
}

$repoRoot = [IO.Path]::GetFullPath(($repoText | Select-Object -First 1).Trim())
$safeTask = $TaskId.ToLowerInvariant()
$branch = "codex/$Governor-$safeTask"

if (-not $WorktreeRoot) {
    $parent = Split-Path -Parent $repoRoot
    $leaf = Split-Path -Leaf $repoRoot
    $WorktreeRoot = Join-Path $parent "$leaf-governor-worktrees"
}
$resolvedRoot = [IO.Path]::GetFullPath($WorktreeRoot)
$target = [IO.Path]::GetFullPath((Join-Path $resolvedRoot "$Governor-$safeTask"))

$repoPrefix = $repoRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if ($target.StartsWith($repoPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Governor worktree must be outside the primary checkout.'
}
if (Test-Path -LiteralPath $target) {
    throw "Target already exists: $target"
}

$plan = [ordered]@{
    owner = $Governor
    task_id = $safeTask
    branch = $branch
    worktree_path = $target
    base_ref = $BaseRef
    provider_access = $false
    auto_commit = $false
    auto_push = $false
    auto_deploy = $false
}

if ($PlanOnly) {
    $plan | ConvertTo-Json -Compress
    return
}

New-Item -ItemType Directory -Path $resolvedRoot -Force | Out-Null
& git worktree add -b $branch $target $BaseRef
if ($LASTEXITCODE -ne 0) {
    throw "Git worktree creation failed with exit code $LASTEXITCODE"
}
$plan | ConvertTo-Json -Compress
