import ctypes

user32 = ctypes.windll.user32
EnumWindows = user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)

windows = []

def foreach_window(hwnd, lParam):
    if user32.IsWindowVisible(hwnd):
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            windows.append((hwnd, buff.value))
    return True

EnumWindows(EnumWindowsProc(foreach_window), 0)

print(f"Total Visible Windows with titles: {len(windows)}")
for hwnd, title in windows:
    print(f"HWND: {hwnd} | Title: {repr(title)}")
