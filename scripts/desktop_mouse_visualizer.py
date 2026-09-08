#!/usr/bin/env python3
"""desktop_mouse_visualizer.py — Visual Mouse Controller & Screen Glow Frame for Computer Use.

Provides:
1. move_mouse(x, y, smooth=True): Smoothly animates and moves the physical cursor on screen.
2. click_mouse(x, y, button="left", clicks=1): Physically clicks mouse and draws a visual expanding ripple.
3. type_text(text, delay=0.02): Physically types text into the active focused window.
4. press_hotkey(keys): Presses key combinations like 'ctrl+c', 'win+r', 'alt+tab', 'enter'.
5. show_screen_glow_frame(duration_seconds, title): Shows a full-screen perimeter border glow indicating AI Computer Use.
6. capture_screen_preview(): Takes a screenshot with highlighted mouse cursor overlay.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON_EXE = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
user32 = ctypes.windll.user32

# Win32 Mouse Events
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800

KEYEVENTF_KEYUP = 0x0002

VK_MAP = {
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "space": 0x20,
    "backspace": 0x08,
    "esc": 0x1B,
    "escape": 0x1B,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "win": 0x5B,
    "windows": 0x5B,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
}


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def get_mouse_position() -> tuple[int, int]:
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return int(pt.x), int(pt.y)


def get_screen_resolution() -> tuple[int, int]:
    w = user32.GetSystemMetrics(0)
    h = user32.GetSystemMetrics(1)
    return int(w), int(h)


def move_mouse(x: int, y: int, smooth: bool = True, duration: float = 0.2):
    curr_x, curr_y = get_mouse_position()
    target_x = max(0, min(x, user32.GetSystemMetrics(0) - 1))
    target_y = max(0, min(y, user32.GetSystemMetrics(1) - 1))

    if not smooth:
        user32.SetCursorPos(target_x, target_y)
        return

    steps = max(5, int(duration * 60))
    for i in range(1, steps + 1):
        t = i / steps
        ease = 1 - (1 - t) ** 3
        nx = int(curr_x + (target_x - curr_x) * ease)
        ny = int(curr_y + (target_y - curr_y) * ease)
        user32.SetCursorPos(nx, ny)
        time.sleep(duration / steps)
    user32.SetCursorPos(target_x, target_y)


def click_mouse(
    x: int | None = None,
    y: int | None = None,
    button: str = "left",
    clicks: int = 1,
    visual_ripple: bool = True,
):
    if x is not None and y is not None:
        move_mouse(x, y, smooth=True, duration=0.15)
    else:
        x, y = get_mouse_position()

    btn = button.lower().strip()
    if btn == "right":
        down_flag, up_flag = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
        ripple_color = "#ef4444"
    elif btn == "middle":
        down_flag, up_flag = MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP
        ripple_color = "#f59e0b"
    else:
        down_flag, up_flag = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
        ripple_color = "#06b6d4"

    if visual_ripple:
        _spawn_gui_process("ripple", f"{x},{y},{ripple_color}")

    for _ in range(clicks):
        user32.mouse_event(down_flag, 0, 0, 0, 0)
        time.sleep(0.04)
        user32.mouse_event(up_flag, 0, 0, 0, 0)
        if clicks > 1:
            time.sleep(0.08)


def scroll_mouse(amount: int):
    user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, amount * 120, 0)


def _vk_for_char(ch: str) -> tuple[int, bool]:
    res = user32.VkKeyScanW(ord(ch))
    vk = res & 0xFF
    shift = bool((res >> 8) & 1)
    return vk, shift


def type_text(text: str, delay: float = 0.02):
    for ch in text:
        if ch == "\n":
            user32.keybd_event(0x0D, 0, 0, 0)
            time.sleep(0.01)
            user32.keybd_event(0x0D, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(delay)
            continue

        vk, need_shift = _vk_for_char(ch)
        if vk == 0xFF:
            continue

        if need_shift:
            user32.keybd_event(0x10, 0, 0, 0)

        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.01)
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

        if need_shift:
            user32.keybd_event(0x10, 0, KEYEVENTF_KEYUP, 0)

        time.sleep(delay)


def press_hotkey(keys_str: str):
    parts = [k.strip().lower() for k in keys_str.replace("-", "+").split("+")]
    vks = []
    for p in parts:
        if p in VK_MAP:
            vks.append(VK_MAP[p])
        elif len(p) == 1:
            vk, _ = _vk_for_char(p)
            vks.append(vk)

    for vk in vks:
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.02)

    time.sleep(0.05)

    for vk in reversed(vks):
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.01)


def _spawn_gui_process(mode: str, data: str, duration: float = 3.0):
    """Spawns an isolated Python GUI subprocess for flicker-free, crash-proof visual overlays."""
    try:
        script = str(Path(__file__).resolve())
        subprocess.Popen(
            [PYTHON_EXE, script, f"--gui-{mode}", data, str(duration)],
            cwd=str(REPO_ROOT),
        )
    except Exception:
        pass


def show_screen_glow_frame(
    duration: float = 3.0,
    title: str = "AI AGENT IN CONTROL",
    duration_seconds: float | None = None,
):
    """Non-blocking call to display full-screen glowing border frame on the owner's monitor."""
    dur = duration_seconds if duration_seconds is not None else duration
    _spawn_gui_process("glow", title, dur)


def capture_screen_preview(output_name: str = "latest_screen.png") -> str:
    preview_dir = REPO_ROOT / "data" / "screen_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    out_file = preview_dir / output_name

    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        img.save(str(out_file))
        return str(out_file)
    except Exception:
        pass

    ps_code = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bm = New-Object System.Drawing.Bitmap($b.Width, $b.Height)
$g = [System.Drawing.Graphics]::FromImage($bm)
$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
$bm.Save('{str(out_file).replace(os.sep, "/")}', [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$bm.Dispose()
"""
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_code], capture_output=True, timeout=8)
        if out_file.exists():
            return str(out_file)
    except Exception:
        pass

    return ""


# Isolated GUI process entrypoint
def _gui_entrypoint():
    import tkinter as tk

    if len(sys.argv) < 3:
        return

    flag = sys.argv[1]
    data = sys.argv[2]
    duration = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0

    if flag == "--gui-glow":
        title = data
        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        sw, sh = get_screen_resolution()
        root.geometry(f"{sw}x{sh}+0+0")
        trans_bg = "#000001"
        root.config(bg=trans_bg)
        root.wm_attributes("-transparentcolor", trans_bg)

        canvas = tk.Canvas(root, width=sw, height=sh, bg=trans_bg, highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        border_color = "#06b6d4"
        thickness = 4

        canvas.create_rectangle(0, 0, sw, thickness, fill=border_color, outline="")
        canvas.create_rectangle(0, sh - thickness, sw, sh, fill=border_color, outline="")
        canvas.create_rectangle(0, 0, thickness, sh, fill=border_color, outline="")
        canvas.create_rectangle(sw - thickness, 0, sw, sh, fill=border_color, outline="")

        pill_w, pill_h = 440, 38
        px1, px2 = int(sw / 2 - pill_w / 2), int(sw / 2 + pill_w / 2)
        py1, py2 = 8, 8 + pill_h
        canvas.create_rectangle(px1, py1, px2, py2, fill="#0f172a", outline=border_color, width=2)
        canvas.create_text(
            int(sw / 2),
            int(py1 + pill_h / 2),
            text=f"🤖 {title.upper()}",
            fill="#38bdf8",
            font=("Segoe UI", 10, "bold"),
        )
        root.after(int(duration * 1000), root.destroy)
        root.mainloop()

    elif flag == "--gui-ripple":
        parts = data.split(",")
        rx, ry = int(parts[0]), int(parts[1])
        color = parts[2] if len(parts) > 2 else "#06b6d4"

        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        trans_bg = "#010101"
        root.config(bg=trans_bg)
        root.wm_attributes("-transparentcolor", trans_bg)
        size = 80
        root.geometry(f"{size}x{size}+{int(rx - size/2)}+{int(ry - size/2)}")
        canvas = tk.Canvas(root, width=size, height=size, bg=trans_bg, highlightthickness=0)
        canvas.pack()

        def anim(step=0):
            if step > 6:
                root.destroy()
                return
            canvas.delete("all")
            r = (step + 1) * 5
            canvas.create_oval(
                size / 2 - r, size / 2 - r, size / 2 + r, size / 2 + r,
                outline=color, width=max(1, 4 - int(step / 2))
            )
            canvas.create_oval(size / 2 - 3, size / 2 - 3, size / 2 + 3, size / 2 + 3, fill=color, outline=color)
            root.after(35, anim, step + 1)

        anim(0)
        root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].startswith("--gui-"):
        _gui_entrypoint()
    else:
        print(f"Screen Resolution: {get_screen_resolution()}")
        print(f"Current Mouse Position: {get_mouse_position()}")
        print("Flashing Visual Screen Glow Frame + Click Ripple...")
        show_screen_glow_frame(duration=2.5, title="LeadGen AI Computer Use Active")
        sw, sh = get_screen_resolution()
        click_mouse(int(sw / 2), int(sh / 2), button="left", visual_ripple=True)
        time.sleep(2.6)
        print("Visual Mouse & Screen Demo Complete.")
