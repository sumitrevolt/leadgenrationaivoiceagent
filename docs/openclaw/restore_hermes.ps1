Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WindowHelper {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool GetWindowPlacement(IntPtr hWnd, ref WINDOWPLACEMENT lpwndpl);
}
public struct WINDOWPLACEMENT {
    public int length;
    public int flags;
    public int showCmd;
    public System.Drawing.Point ptMinPosition;
    public System.Drawing.Point ptMaxPosition;
    public System.Drawing.Rectangle rcNormalPosition;
}
"@

$proc = Get-Process -Id 39104
if ($proc) {
    Write-Host "Found Hermes GUI process: $($proc.Id)"
    Write-Host "MainWindowTitle: $($proc.MainWindowTitle)"
    Write-Host "MainWindowHandle: $($proc.MainWindowHandle)"
    
    if ($proc.MainWindowHandle -ne 0) {
        $wp = New-Object WINDOWPLACEMENT
        $wp.length = [System.Runtime.InteropServices.Marshal]::SizeOf($wp)
        
        # Check if minimized
        if ([WindowHelper]::IsIconic($proc.MainWindowHandle)) {
            Write-Host "Window is minimized - restoring..."
            [WindowHelper]::ShowWindow($proc.MainWindowHandle, 9)  # SW_RESTORE
        }
        
        # Bring to front
        [WindowHelper]::SetForegroundWindow($proc.MainWindowHandle)
        Write-Host "Window restored and brought to front"
    } else {
        Write-Host "No window handle"
    }
} else {
    Write-Host "Process 39104 not found"
}