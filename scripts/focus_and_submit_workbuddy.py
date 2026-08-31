import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Set DPI awareness
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
print(f"DPI Aware Screen: {sw}x{sh}")

# Target coordinates: bottom of left half of screen
target_x = int(sw * 0.22)  # ~420px on 1920
target_y = int(sh * 0.94)  # ~1015px on 1080

from scripts.desktop_action_overlay import notify_computer_action
from scripts.desktop_mouse_visualizer import click_mouse, move_mouse, press_hotkey, show_screen_glow_frame

# Visual indicator on screen
show_screen_glow_frame(duration_seconds=4.0, title="Submitting SDXL Task to WorkBuddy")
notify_computer_action("WorkBuddy Control", "Typing and submitting task to WorkBuddy", duration=4.0)
time.sleep(0.5)

# Set clipboard content
prompt_text = "Haan, SDXL (AI Image generation) ka setup shuru karo for automated video thumbnails and visual content assets. Free local stack follow karo."
subprocess.run(
    ["powershell", "-NoProfile", "-Command", f'Set-Clipboard -Value "{prompt_text}"'],
    check=True,
)

print(f"Moving to target ({target_x}, {target_y})...")
move_mouse(target_x, target_y, smooth=True, duration=0.4)
time.sleep(0.2)

# Double click to ensure focus
click_mouse(target_x, target_y, visual_ripple=True)
time.sleep(0.1)
click_mouse(target_x, target_y, visual_ripple=True)
time.sleep(0.3)

# Paste from clipboard
print("Pasting text...")
press_hotkey("ctrl+v")
time.sleep(0.6)

# Submit
print("Pressing Enter...")
press_hotkey("enter")
time.sleep(0.5)
print("Done!")
