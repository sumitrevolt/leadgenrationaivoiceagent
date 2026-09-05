# Fix Hermes Desktop GUI - Bring to Front and Restore if Minimized
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
    [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);
}
public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
"@

$proc = Get-Process -Id 39104 -ErrorAction SilentlyContinue
if ($proc -and $proc.MainWindowHandle -ne 0) {
    $rect = New-Object RECT
    if ([Win32]::GetWindowRect($proc.MainWindowHandle, [ref] $rect)) {
        Write-Host "Window rect: Left=$($rect.Left) Top=$($rect.Top) Right=$($rect.Right) Bottom=$($rect.Bottom)"
        
        if ([Win32]::IsIconic($proc.MainWindowHandle)) {
            Write-Host "Minimized - restoring..."
            [Win32]::ShowWindow($proc.MainWindowHandle, 9)  # SW_RESTORE
        } elseif ($rect.Left -lt -3000 -or $rect.Top -lt -3000) {
            Write-Host "Window off-screen - moving to (100,100)..."
            [Win32]::MoveWindow($proc.MainWindowHandle, 100, 100, 1200, 800, $true)
        }
    }
    
    [Win32]::BringWindowToTop($proc.MainWindowHandle)
    $result = [Win32]::SetForegroundWindow($proc.MainWindowHandle)
    Write-Host "SetForegroundWindow result: $result"
    Write-Host "Hermes GUI should now be visible at front"
} else {
    Write-Host "Process 39104 not found or no window handle"
}