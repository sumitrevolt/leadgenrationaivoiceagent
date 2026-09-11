$procs = Get-Process python -ErrorAction SilentlyContinue
$found = $false
foreach ($p in $procs) {
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($p.Id)" -ErrorAction SilentlyContinue).CommandLine
    if ($cmd -and ($cmd -like '*workforce*' -or $cmd -like '*orchestrator*')) {
        Write-Output "PID=$($p.Id) CMD=$cmd"
        $found = $true
    }
}
if (-not $found) {
    Write-Output "NO WORKFORCE ORCHESTRATOR PROCESS FOUND"
}
