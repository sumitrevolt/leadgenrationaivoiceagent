Get-Process | Sort-Object WorkingSet64 -Descending | ForEach-Object {
    $mem = [math]::Round($_.WorkingSet64/1MB,1)
    "$($_.Id)`t$($_.ProcessName)`t$($mem)`t$($_.Description)"
}