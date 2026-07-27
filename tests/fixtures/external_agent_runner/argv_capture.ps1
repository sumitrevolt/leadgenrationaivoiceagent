# Owned EXTERNAL_AGENT_RUNNER test wrapper — record args as JSON; never Invoke-Expression.
param(
    [string]$CaptureOut = "",
    [string]$Wrapper = "ps1",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $CaptureOut) {
    $CaptureOut = Join-Path $here "_captured_argv_ps1.json"
}
$canary = Join-Path (Get-Location) "SECONDARY_CMD_RAN.txt"
$payload = [ordered]@{
    wrapper = $Wrapper
    argv = @($Rest)
    secondary_canary_exists = [bool](Test-Path -LiteralPath $canary)
    pwd = (Get-Location).Path
    raw_argc = @($Rest).Count
}
$json = ($payload | ConvertTo-Json -Compress -Depth 5)
[System.IO.File]::WriteAllText($CaptureOut, $json)
Write-Output $json
exit 0
