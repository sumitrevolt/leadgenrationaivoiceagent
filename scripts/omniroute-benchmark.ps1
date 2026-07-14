param(
    [string]$OmniRouteUrl = "http://127.0.0.1:20128/v1/responses",
    [string]$BaselineUrl = "",
    [string]$Model = "groq/llama-3.3-70b-versatile",
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
    $body = @{
        model = $Model
        input = @(@{ role = "user"; content = $prompt })
        max_output_tokens = 180
    } | ConvertTo-Json -Depth 6
    $headers = @{ Authorization = "Bearer $env:OMNIROUTE_API_KEY"; "Content-Type" = "application/json" }
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $response = Invoke-RestMethod -Uri $Url -Method Post -Headers $headers -Body $body -TimeoutSec 90
    $sw.Stop()
    if (-not $response.output_text) {
        throw "OmniRoute Responses API returned no output_text."
    }
    [pscustomobject]@{
        elapsed_ms = $sw.ElapsedMilliseconds
        input_tokens = $response.usage.input_tokens
        output_tokens = $response.usage.output_tokens
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
