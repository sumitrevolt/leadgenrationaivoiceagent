param(
    [string]$OmniRouteUrl = "http://127.0.0.1:20128/v1/chat/completions",
    [string]$BaselineUrl = "",
    [string]$Model = "auto/coding",
    [int]$Runs = 5
)

$ErrorActionPreference = "Stop"
if (-not $env:OMNIROUTE_API_KEY) {
    throw "Set OMNIROUTE_API_KEY in the process environment only; never commit it."
}

$prompt = @"
You are reviewing a sanitized LeadGen AI codebase. Explain a small Python
function that validates an input dictionary and returns {ok: bool, error: str}.
Do not invent files, credentials, customer data, or production actions. Keep
the answer under 120 words.
"@

function Invoke-Model([string]$Url) {
    $body = @{ model = $Model; messages = @(@{ role = "user"; content = $prompt }); max_tokens = 180 } | ConvertTo-Json -Depth 6
    $headers = @{ Authorization = "Bearer $env:OMNIROUTE_API_KEY"; "Content-Type" = "application/json" }
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $response = Invoke-RestMethod -Uri $Url -Method Post -Headers $headers -Body $body -TimeoutSec 90
    $sw.Stop()
    [pscustomobject]@{
        elapsed_ms = $sw.ElapsedMilliseconds
        prompt_tokens = $response.usage.prompt_tokens
        completion_tokens = $response.usage.completion_tokens
        total_tokens = $response.usage.total_tokens
    }
}

$omni = 1..([Math]::Max(1, $Runs)) | ForEach-Object { Invoke-Model $OmniRouteUrl }
$omni | Format-Table

if ($BaselineUrl) {
    $base = 1..([Math]::Max(1, $Runs)) | ForEach-Object { Invoke-Model $BaselineUrl }
    Write-Host "Baseline"
    $base | Format-Table
}

Write-Host "This is a sanitized smoke benchmark, not a production quality gate by itself."
