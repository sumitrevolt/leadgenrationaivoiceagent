Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class WindowHelper {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
}
"@

$proc = Get-Process -Id 39104
if ($proc -and $proc.MainWindowHandle -ne 0) {
    if ([WindowHelper]::IsIconic($proc.MainWindowHandle)) {
        Write-Host "Minimized - restoring..."
        [WindowHelper]::ShowWindow($proc.MainWindowHandle, 9)
    }
    $result = [WindowHelper]::SetForegroundWindow($proc.MainWindowHandle)
    Write-Host "SetForegroundWindow result: $result"
    Write-Host "Hermes GUI should now be visible on screen"
} else {
    Write-Host "Process or window not found"
}