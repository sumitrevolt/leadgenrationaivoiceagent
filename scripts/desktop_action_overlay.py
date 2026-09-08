#!/usr/bin/env python3
"""desktop_action_overlay.py — Visual Screen HUD & Action Indicator for Computer Use.

Provides:
1. show_action_hud: Spawns a sleek, modern, top-right floating dark HUD on Windows
   showing the owner what computer action / tool is actively running on their screen.
2. capture_desktop_screenshot: Takes a real desktop screenshot so the owner/agent can see
   what is visually displayed on screen.
"""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON_EXE = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable


def _render_hud(title: str, detail: str, duration: float = 4.0, center: bool = False):
    """Spawns a highly visible floating HUD/Popup window on Windows."""
    import tkinter as tk

    try:
        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.96)

        # High-contrast Cyber Theme
        bg_color = "#0b0f19"
        border_color = "#06b6d4"
        accent_blue = "#38bdf8"
        text_white = "#ffffff"
        text_dim = "#cbd5e1"
        badge_bg = "#064e3b"
        badge_fg = "#34d399"

        root.configure(bg=border_color)

        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()

        if center:
            hud_width = 560
            hud_height = 140
            x_pos = int((screen_width - hud_width) / 2)
            y_pos = int((screen_height - hud_height) / 2) - 80
        else:
            hud_width = 480
            hud_height = 105
            x_pos = screen_width - hud_width - 24
            y_pos = 28

        root.geometry(f"{hud_width}x{hud_height}+{x_pos}+{y_pos}")

        # Outer Frame for glow border
        outer = tk.Frame(root, bg=border_color, padx=2, pady=2)
        outer.pack(fill="both", expand=True)

        inner = tk.Frame(outer, bg=bg_color, padx=16, pady=12)
        inner.pack(fill="both", expand=True)

        # Header with AI Icon & Badge
        header_frame = tk.Frame(inner, bg=bg_color)
        header_frame.pack(fill="x")

        icon_label = tk.Label(
            header_frame,
            text="⚡ AI AGENT COMPUTER USE ACTIVE",
            font=("Segoe UI", 10, "bold"),
            fg=accent_blue,
            bg=bg_color,
        )
        icon_label.pack(side="left")

        badge = tk.Label(
            header_frame,
            text="LIVE WORKFLOW",
            font=("Segoe UI", 8, "bold"),
            fg=badge_fg,
            bg=badge_bg,
            padx=8,
            pady=2,
        )
        badge.pack(side="right")

        # Action Title
        action_lbl = tk.Label(
            inner,
            text=title[:65],
            font=("Segoe UI", 12, "bold"),
            fg=text_white,
            bg=bg_color,
            anchor="w",
        )
        action_lbl.pack(fill="x", pady=(6, 2))

        # Detail line
        detail_lbl = tk.Label(
            inner,
            text=detail[:95],
            font=("Segoe UI", 9),
            fg=text_dim,
            bg=bg_color,
            anchor="w",
            wraplength=hud_width - 32,
            justify="left",
        )
        detail_lbl.pack(fill="x")

        # Bring window aggressively to front
        root.lift()
        root.focus_force()

        # Auto close timer
        root.after(int(duration * 1000), root.destroy)
        root.mainloop()
    except Exception:
        pass


def notify_computer_action(title: str, detail: str = "", duration: float = 4.0, center: bool = False):
    """Spawns an independent GUI popup process that is 100% guaranteed to stay visible on screen."""
    try:
        script = str(Path(__file__).resolve())
        cmd = [
            PYTHON_EXE,
            script,
            "--popup-center" if center else "--popup",
            title,
            detail,
            str(duration),
        ]
        subprocess.Popen(cmd, cwd=str(REPO_ROOT))
    except Exception:
        pass


def show_center_popup(title: str, detail: str = "", duration: float = 5.0):
    """Spawns a prominent center-screen popup card for major task handoffs."""
    notify_computer_action(title, detail, duration=duration, center=True)


def capture_screen(output_name: str = "latest_screen.png") -> str:
    """Takes a full desktop screenshot and saves it to data/screen_previews/."""
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
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_code],
            capture_output=True,
            timeout=8,
        )
        if out_file.exists():
            return str(out_file)
    except Exception:
        pass

    return ""


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].startswith("--popup"):
        is_center = sys.argv[1] == "--popup-center"
        t = sys.argv[2] if len(sys.argv) > 2 else "AI Action Running"
        d = sys.argv[3] if len(sys.argv) > 3 else "Executing task in background..."
        dur = float(sys.argv[4]) if len(sys.argv) > 4 else 4.0
        _render_hud(t, d, dur, center=is_center)
    else:
        action = sys.argv[1] if len(sys.argv) > 1 else "Running Admin Verification"
        det = sys.argv[2] if len(sys.argv) > 2 else "Executing command in project root..."
        print(f"Triggering Visual Screen HUD: {action} ({det})")
        notify_computer_action(action, det, duration=4.0, center=True)
        print("HUD spawned in standalone GUI process.")
