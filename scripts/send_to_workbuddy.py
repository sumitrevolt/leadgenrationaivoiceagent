import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Make process DPI aware so coordinates match physical screen
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

user32 = ctypes.windll.user32
sw = user32.GetSystemMetrics(0)
sh = user32.GetSystemMetrics(1)
print(f"Screen Resolution (Physical DPI Aware): {sw}x{sh}")

# Find WorkBuddy window
EnumWindows = user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
workbuddy_hwnd = None


def foreach_window(hwnd, lParam):
    global workbuddy_hwnd
    if user32.IsWindowVisible(hwnd):
        length = user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        title = buff.value.lower()
        if "workbuddy" in title or "design multi-platform" in title:
            workbuddy_hwnd = hwnd
            return False
    return True


EnumWindows(EnumWindowsProc(foreach_window), 0)
print(f"WorkBuddy Window HWND: {workbuddy_hwnd}")


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


if workbuddy_hwnd:
    # Force bring window to front
    user32.ShowWindow(workbuddy_hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(workbuddy_hwnd)
    time.sleep(0.5)
    rect = RECT()
    user32.GetWindowRect(workbuddy_hwnd, ctypes.byref(rect))
    print(f"WorkBuddy Rect: left={rect.left}, top={rect.top}, right={rect.right}, bottom={rect.bottom}")
    # WorkBuddy is docked on the left half. The input box is near rect.bottom - 45
    target_x = rect.left + (rect.right - rect.left) // 2
    target_y = rect.bottom - 45
else:
    # Fallback to bottom of left half of screen
    target_x = int(sw * 0.25)
    target_y = int(sh * 0.94)

print(f"Targeting Input Box at: ({target_x}, {target_y})")

# Copy prompt text to clipboard using PowerShell Set-Clipboard
task_text = "Haan, SDXL (AI Image generation) ka setup shuru karo for automated video thumbnails and visual content assets. Free local stack follow karo."
subprocess.run(
    ["powershell", "-NoProfile", "-Command", f'Set-Clipboard -Value "{task_text}"'],
    check=True,
)
print("Clipboard set successfully.")

# Visual action indicator
from scripts.desktop_action_overlay import notify_computer_action
from scripts.desktop_mouse_visualizer import click_mouse, move_mouse, press_hotkey, show_screen_glow_frame

show_screen_glow_frame(duration_seconds=4.0, title="Automating WorkBuddy Prompt")
notify_computer_action("WorkBuddy Automation", "Pasting planned task into WorkBuddy chat input", duration=4.0)
time.sleep(0.5)

# Move mouse to the input area and click to focus
move_mouse(target_x, target_y, smooth=True, duration=0.4)
time.sleep(0.2)
click_mouse(target_x, target_y, visual_ripple=True)
time.sleep(0.4)

# Paste from clipboard via Ctrl+V
print("Sending Ctrl+V...")
press_hotkey("ctrl+v")
time.sleep(0.5)

# Press Enter
print("Sending Enter...")
press_hotkey("enter")
time.sleep(1.5)

# Take screenshot to verify
from scripts.desktop_mouse_visualizer import capture_screen_preview

scr = capture_screen_preview("workbuddy_task_submitted_live.png")
print(f"Verification screenshot saved: {scr}")
