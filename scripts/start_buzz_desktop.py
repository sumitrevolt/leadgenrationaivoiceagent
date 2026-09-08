import os
import sys
import time
import ctypes
from ctypes import wintypes
import psutil

SW_SHOWNORMAL = 1
SW_SHOW = 5
SW_RESTORE = 9

class STARTUPINFO(ctypes.Structure):
    _fields_ = [
        ('cb', wintypes.DWORD),
        ('lpReserved', wintypes.LPWSTR),
        ('lpDesktop', wintypes.LPWSTR),
        ('lpTitle', wintypes.LPWSTR),
        ('dwX', wintypes.DWORD),
        ('dwY', wintypes.DWORD),
        ('dwXSize', wintypes.DWORD),
        ('dwYSize', wintypes.DWORD),
        ('dwXCountChars', wintypes.DWORD),
        ('dwYCountChars', wintypes.DWORD),
        ('dwFillAttribute', wintypes.DWORD),
        ('dwFlags', wintypes.DWORD),
        ('wShowWindow', wintypes.WORD),
        ('cbReserved2', wintypes.WORD),
        ('lpReserved2', ctypes.c_char_p),
        ('hStdInput', wintypes.HANDLE),
        ('hStdOutput', wintypes.HANDLE),
        ('hStdError', wintypes.HANDLE),
    ]

class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('hProcess', wintypes.HANDLE),
        ('hThread', wintypes.HANDLE),
        ('dwProcessId', wintypes.DWORD),
        ('dwThreadId', wintypes.DWORD),
    ]

def cleanup_old():
    for p in psutil.process_iter(['pid', 'name']):
        try:
            if 'buzz-desktop' in p.info['name'].lower():
                print(f"[start_buzz] Terminating old buzz PID {p.info['pid']}...")
                p.kill()
        except Exception:
            pass
    time.sleep(1)

def main():
    cleanup_old()
    
    exe_path = os.path.expandvars(r"%LOCALAPPDATA%\Buzz\buzz-desktop.exe")
    work_dir = os.path.dirname(exe_path)
    
    # Environment variables for Buzz
    os.environ["BUZZ_RELAY"] = "ws://127.0.0.1:3100"
    os.environ["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:22000"
    os.environ["ANTHROPIC_MODEL"] = "leadgen-project-best"
    
    si = STARTUPINFO()
    si.cb = ctypes.sizeof(STARTUPINFO)
    si.lpDesktop = "WinSta0\\Default"
    
    pi = PROCESS_INFORMATION()
    
    # CREATE_NEW_PROCESS_GROUP = 0x00000200
    flags = 0x00000200
    
    print(f"[start_buzz] Spawning {exe_path} onto WinSta0\\Default...")
    success = ctypes.windll.kernel32.CreateProcessW(
        exe_path,
        None,
        None,
        None,
        False,
        flags,
        None,
        work_dir,
        ctypes.byref(si),
        ctypes.byref(pi)
    )
    
    if not success:
        err = ctypes.windll.kernel32.GetLastError()
        print(f"[start_buzz] CreateProcessW failed: {err}")
        sys.exit(1)
        
    pid = pi.dwProcessId
    print(f"[start_buzz] Spawned successfully with PID {pid}!")
    
    # Open user's Default desktop to monitor and restore window
    hdesk = ctypes.windll.user32.OpenDesktopW("Default", 0, False, 0x0100)
    
    for attempt in range(1, 20):
        time.sleep(1)
        if not psutil.pid_exists(pid):
            print(f"[start_buzz] Process {pid} exited unexpectedly.")
            sys.exit(1)
            
        if hdesk:
            found_hwnds = []
            def cb(hwnd, _):
                wpid = wintypes.DWORD()
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
                if wpid.value == pid:
                    cbuf = ctypes.create_unicode_buffer(256)
                    ctypes.windll.user32.GetClassNameW(hwnd, cbuf, 256)
                    if cbuf.value == 'Tauri Window':
                        found_hwnds.append(hwnd)
                return True
                
            EnumDesktopWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            ctypes.windll.user32.EnumDesktopWindows(hdesk, EnumDesktopWindowsProc(cb), 0)
            
            if found_hwnds:
                for hwnd in found_hwnds:
                    print(f"[start_buzz] Found Tauri Window HWND {hwnd}! Restoring to foreground...")
                    ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
                    ctypes.windll.user32.ShowWindow(hwnd, SW_SHOW)
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                print("[start_buzz] Window is now live on screen!")
                break
            else:
                print(f"[start_buzz] Waiting for Tauri Window on Default desktop ({attempt}/20)...")
                
    # Keep process handle open and monitor
    while psutil.pid_exists(pid):
        time.sleep(5)
        
    print("[start_buzz] Process terminated.")

if __name__ == "__main__":
    main()
