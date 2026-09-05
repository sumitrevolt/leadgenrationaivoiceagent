# Fix Hermes Desktop GUI - Multiple Methods
Write-Host "=== Hermes GUI Fix Script ===" -ForegroundColor Cyan

# Check if process exists
$proc = Get-Process -Id 39104 -ErrorAction SilentlyContinue
if (-not $proc) {
    Write-Host "ERROR: Process 39104 not found!" -ForegroundColor Red
    return
}

Write-Host "Process 39104 found: $($proc.MainWindowTitle)" -ForegroundColor Yellow

# Method 1: Get window rect and check position
$rect = New-Object System.Drawing.Rectangle
$ret = [System.Runtime.InteropServices.Marshal]::Copy($proc.MainWindowHandle, $rect, 0, 1) -ne 0
# Use interop instead

# Get window placement using Win32 API
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NativeMethods {
    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    
    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    
    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    
    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool BringWindowToTop(IntPtr hWnd);
    
    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool IsIconic(IntPtr hWnd);
    
    [DllImport("user32.dll")]
    public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
    
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }
}
"@

Write-Host "Native methods loaded" -ForegroundColor Gray

# Check window state
$rectOut = [System.IntPtr]::Zero
$result = [NativeMethods]::GetWindowRect($proc.MainWindowHandle, [ref] $rectOut)
if ($result) {
    $rect = [System.Runtime.InteropServices.Marshal]::PtrToStructure([System.Runtime.InteropServices.Marshal]::ReadIntPtr($rectOut), [System.Drawing.Rectangle]) -or $rect
    # Actually let's just use simple approach
}

# Simple approach: just try to bring to front
Write-Host "Attempting to bring Hermes to foreground..." -ForegroundColor White

# Try SetForegroundWindow
$fwResult = [NativeMethods]::SetForegroundWindow($proc.MainWindowHandle)
Write-Host "SetForegroundWindow result: $fwResult" -ForegroundColor Gray

# Try BringWindowToTop
$bwtResult = [NativeMethods]::BringWindowToTop($proc.MainWindowHandle)
Write-Host "BringWindowToTop result: $bwtResult" -ForegroundColor Gray

# Try ShowWindow if iconic
$isIconic = [NativeMethods]::IsIconic($proc.MainWindowHandle)
Write-Host "IsIconic: $isIconic" -ForegroundColor Gray

if ($isIconic) {
    Write-Host "Window is minimized - restoring with ShowWindow..." -ForegroundColor Yellow
    [NativeMethods]::ShowWindow($proc.MainWindowHandle, 9)  # SW_RESTORE
}

# Final attempt: Move to visible position if off-screen
# The window was at Left=768, so it's on-screen but maybe hidden behind other windows
Write-Host "Attempting final foreground activation..." -ForegroundColor White
$finalResult = [NativeMethods]::SetForegroundWindow($proc.MainWindowHandle)
Write-Host "Final SetForegroundWindow: $finalResult" -ForegroundColor Gray

# Summary
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "Hermes PID: $($proc.Id)" -ForegroundColor White
Write-Host "Window Title: $($proc.MainWindowTitle)" -ForegroundColor White
Write-Host "SetForegroundWindow succeeded: $fwResult" -ForegroundColor White
Write-Host "Is minimized: $isIconic" -ForegroundColor White
if ($fwResult) { Write-Host "Hermes GUI should now be visible!" -ForegroundColor Green }
else { Write-Host "Try clicking on Hermes taskbar icon manually" -ForegroundColor Yellow }