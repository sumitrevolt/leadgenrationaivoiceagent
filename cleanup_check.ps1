
$outFile = "C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent\cleanup_report.txt"
"" | Out-File $outFile

"=== DISK SPACE ===" | Out-File $outFile -Append
$drive = Get-PSDrive C
"C: Used: $([math]::Round($drive.Used/1GB, 2)) GB" | Out-File $outFile -Append
"C: Free: $([math]::Round($drive.Free/1GB, 2)) GB" | Out-File $outFile -Append

"=== TEMP/CACHE FOLDERS ===" | Out-File $outFile -Append

# User temp
$tempPath = [System.IO.Path]::GetTempPath()
$size = (Get-ChildItem -Path $tempPath -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
"User Temp ($tempPath): $([math]::Round($size/1MB, 2)) MB" | Out-File $outFile -Append

# Windows Temp
$size = (Get-ChildItem -Path 'C:\Windows\Temp' -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
"Windows Temp: $([math]::Round($size/1MB, 2)) MB" | Out-File $outFile -Append

# Prefetch
$size = (Get-ChildItem -Path 'C:\Windows\Prefetch' -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
"Prefetch: $([math]::Round($size/1MB, 2)) MB" | Out-File $outFile -Append

# Windows Logs
$size = (Get-ChildItem -Path 'C:\Windows\Logs' -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
"Windows Logs: $([math]::Round($size/1MB, 2)) MB" | Out-File $outFile -Append

# SoftwareDistribution Download
$size = (Get-ChildItem -Path 'C:\Windows\SoftwareDistribution\Download' -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
"SoftwareDistribution: $([math]::Round($size/1MB, 2)) MB" | Out-File $outFile -Append

# Windows.old
if (Test-Path 'C:\Windows.old') {
    $size = (Get-ChildItem -Path 'C:\Windows.old' -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    "Windows.old: $([math]::Round($size/1GB, 2)) GB" | Out-File $outFile -Append
}

# User Downloads
$size = (Get-ChildItem -Path "$env:USERPROFILE\Downloads" -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
"Downloads: $([math]::Round($size/1GB, 2)) GB" | Out-File $outFile -Append

# Local AppData Temp
$size = (Get-ChildItem -Path "$env:LOCALAPPDATA\Temp" -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
"LocalAppData Temp: $([math]::Round($size/1MB, 2)) MB" | Out-File $outFile -Append

# CrashDumps
$size = (Get-ChildItem -Path "$env:LOCALAPPDATA\CrashDumps" -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
"CrashDumps: $([math]::Round($size/1MB, 2)) MB" | Out-File $outFile -Append

# LocalAppData/UploadCache
$size = (Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\Windows\INetCache" -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
"INetCache: $([math]::Round($size/1MB, 2)) MB" | Out-File $outFile -Append

# Recycle Bin
$shell = New-Object -ComObject Shell.Application
$rb = $shell.NameSpace(0xA)
$rbCount = $rb.Items().Count
"Recycle Bin items: $rbCount" | Out-File $outFile -Append

"=== USER PROFILE FOLDERS ===" | Out-File $outFile -Append
$folders = @('Documents','Downloads','Desktop','Videos','Music','Pictures')
foreach ($f in $folders) {
    $p = "$env:USERPROFILE\$f"
    if (Test-Path $p) {
        $s = (Get-ChildItem -Path $p -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        "$f : $([math]::Round($s/1GB, 2)) GB" | Out-File $outFile -Append
    }
}

"=== WINGET PACKAGES ===" | Out-File $outFile -Append
$pkgs = winget list 2>$null
$pkgs | Out-File $outFile -Append

"=== RUNNING PROCESSES (non-system) ===" | Out-File $outFile -Append
$procs = Get-Process | Where-Object { $_.Path -and ($_.Path -notlike 'C:\Windows\*') } | Select-Object Name, Id, Path, @{N='MemMB';E={[math]::Round($_.WorkingSet/1MB)}}
$procs | Format-Table -AutoSize | Out-String | Out-File $outFile -Append

"=== DUPLICATE / ARCHIVE FINDER ===" | Out-File $outFile -Append
$exts = @('*.zip','*.rar','*.7z','*.tar','*.gz','*.iso','*.img')
foreach ($e in $exts) {
    Get-ChildItem -Path "$env:USERPROFILE\Downloads" -Filter $e -Recurse -ErrorAction SilentlyContinue | Select-Object FullName, @{N='SizeMB';E={[math]::Round($_.Length/1MB,1)}} | Format-Table -AutoSize | Out-String | Out-File $outFile -Append
}

"=== DONE ===" | Out-File $outFile -Append
