#Requires -Version 5.1
<#
.SYNOPSIS
  Install Spec Kit CLI pinned to v0.15.2 (dev-operator tool only).

.DESCRIPTION
  Wave 1: NOT for CI or production images. Pins github/spec-kit@v0.15.2.
  Constitution already lives at .specify/memory/constitution.md — init is
  idempotent / ignore-agent-tools when the tree is already present.

.NOTES
  Requires: uv (https://docs.astral.sh/uv/)
#>
$ErrorActionPreference = "Stop"
$Pin = "v0.15.2"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

Write-Host "==> Spec Kit pin: $Pin (LeadGen Wave 1)"
Write-Host "==> Repo: $RepoRoot"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv not found. Install from https://docs.astral.sh/uv/ then re-run."
}

Write-Host "==> uv tool install specify-cli @$Pin"
uv tool install specify-cli --from "git+https://github.com/github/spec-kit.git@$Pin"

Push-Location $RepoRoot
try {
    if (Test-Path (Join-Path $RepoRoot ".specify\memory\constitution.md")) {
        Write-Host "==> .specify/ already present — skipping specify init (constitution committed)."
        Write-Host "    To refresh agent integrations later:"
        Write-Host "    specify init . --integration claude --ignore-agent-tools"
    } else {
        Write-Host "==> specify init . --integration claude --ignore-agent-tools"
        specify init . --integration claude --ignore-agent-tools
    }
} finally {
    Pop-Location
}

Write-Host "==> Verify: specify --version (expect pin lineage $Pin)"
specify --version
Write-Host "Done. Read docs/PR_FACTORY.md and .specify/PIN.md"
