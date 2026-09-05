#!/usr/bin/env python3
"""leadgen_admin_harness_mcp.py — 1000-Engineers Talent, Visual Mouse & Admin Computer Use MCP Server.

Standard JSON-RPC 2.0 stdio MCP server for Claude Desktop, Hermes Desktop,
WorkBuddy Desktop, DSH, and any MCP client.

Equips any connected Desktop Agent with:
1. 1000-Engineers Talent & Discipline Knowledge Packs (D1-D12, 10-lens review, doctrine)
2. Visual Mouse Controller (smooth animated mouse movement + visible click ripple ring)
3. Full Screen Perimeter Glow Frame (visual glowing indicator when AI is controlling computer)
4. Hardware Keyboard Typing & Hotkey Execution (type into active windows / hotkeys)
5. Admin Computer-Use Command Execution (with top-right floating HUD banner)
6. Desktop Screen Capture & Visual State Inspector
7. Hot Queue & Ops Triage Harness
8. Automated Self-Harness Verification & Diagnostics
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON_EXE = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
ENGINEERS_1000_FILE = REPO_ROOT / "deploy" / "dsh" / "skills" / "1000-engineers.md"


def _notify_screen(title: str, detail: str = "", duration: float = 3.5):
    """Trigger visual on-screen HUD notification so the owner sees what the agent is doing."""
    try:
        from scripts.desktop_action_overlay import notify_computer_action
        notify_computer_action(title, detail, duration=duration)
    except Exception:
        pass


def tool_thousand_engineers(args: dict) -> dict:
    """Retrieve 1000-engineers doctrine, 10-lens review, or specific discipline packs (D1-D12)."""
    topic = str(args.get("topic") or args.get("discipline") or "doctrine").strip().lower()
    
    if not ENGINEERS_1000_FILE.exists():
        fallback = REPO_ROOT / ".claude" / "skills" / "thousand-engineers" / "SKILL.md"
        if fallback.exists():
            return {"text": fallback.read_text(encoding="utf-8")}
        return {"text": "1000-engineers canonical file missing at deploy/dsh/skills/1000-engineers.md"}
    
    content = ENGINEERS_1000_FILE.read_text(encoding="utf-8")
    
    if topic in ("all", "full"):
        return {"text": content}
    
    if topic in ("doctrine", "rules", "invariants", "0"):
        lines = content.splitlines()[:72]
        return {"text": "\n".join(lines)}
        
    if topic in ("10-lens", "review", "lenses", "1"):
        lines = content.splitlines()
        start = -1
        end = -1
        for i, l in enumerate(lines):
            if "## §1 The 10-Lens Review" in l:
                start = i
            elif start != -1 and l.startswith("---") and i > start + 5:
                end = i
                break
        if start != -1:
            return {"text": "\n".join(lines[start : end if end != -1 else start + 30])}
            
    pack_map = {
        "d1": "### D1. Architecture",
        "arch": "### D1. Architecture",
        "architecture": "### D1. Architecture",
        "d2": "### D2. Backend Engineering",
        "backend": "### D2. Backend Engineering",
        "fastapi": "### D2. Backend Engineering",
        "d3": "### D3. Frontend",
        "frontend": "### D3. Frontend",
        "d4": "### D4. AI/LLM",
        "ai": "### D4. AI/LLM",
        "llm": "### D4. AI/LLM",
        "d5": "### D5. Database",
        "db": "### D5. Database",
        "data": "### D5. Database",
        "postgres": "### D5. Database",
        "d6": "### D6. CI/CD",
        "deploy": "### D6. CI/CD",
        "d7": "### D7. SRE",
        "sre": "### D7. SRE",
        "d8": "### D8. Security",
        "security": "### D8. Security",
        "compliance": "### D8. Security",
        "d9": "### D9. QA",
        "qa": "### D9. QA",
        "test": "### D9. QA",
        "testing": "### D9. QA",
        "d10": "### D10. Performance",
        "perf": "### D10. Performance",
        "d11": "### D11. Product",
        "product": "### D11. Product",
        "pricing": "### D11. Product",
        "d12": "### D12. Debugging",
        "debug": "### D12. Debugging",
    }
    
    target_header = pack_map.get(topic)
    if target_header:
        lines = content.splitlines()
        extracted = []
        capturing = False
        for l in lines:
            if target_header in l:
                capturing = True
            elif capturing and l.startswith("### D") and target_header not in l:
                break
            if capturing:
                extracted.append(l)
        if extracted:
            return {"text": "\n".join(extracted)}
            
    matched = [l for l in content.splitlines() if topic in l.lower()]
    if matched:
        return {"text": "\n".join(matched[:50])}
        
    return {"text": f"Discipline/topic '{topic}' not found in 1000-engineers knowledge pack."}


def tool_execute_admin_command(args: dict) -> dict:
    """Run an administrative or verification command safely within the project workspace with Visual Screen HUD."""
    cmd = str(args.get("command") or "").strip()
    if not cmd:
        return {"text": "Error: 'command' argument is required."}
    
    _notify_screen("Admin Shell Execution", cmd, duration=4.0)

    blocked = ["format ", "rmdir /s /q c:\\", "rm -rf /", "del /f /s /q c:\\"]
    if any(b in cmd.lower() for b in blocked):
        return {"text": f"Blocked by safety guard: command '{cmd}' contains dangerous operations."}
    
    timeout = int(args.get("timeout_seconds") or 120)
    timeout = max(5, min(300, timeout))
    
    run_cmd = cmd
    if cmd.startswith("python "):
        run_cmd = f'"{PYTHON_EXE}" {cmd[7:]}'
    elif cmd.startswith("pytest "):
        run_cmd = f'"{PYTHON_EXE}" -m pytest {cmd[7:]}'
        
    try:
        res = subprocess.run(
            run_cmd,
            shell=True,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        out = []
        out.append(f"Exit Code: {res.returncode}")
        if res.stdout:
            out.append("--- STDOUT ---")
            out.append(res.stdout[-6000:])
        if res.stderr:
            out.append("--- STDERR ---")
            out.append(res.stderr[-3000:])
        return {"text": "\n".join(out)}
    except subprocess.TimeoutExpired:
        return {"text": f"Command timed out after {timeout} seconds: {cmd}"}
    except Exception as exc:
        return {"text": f"Execution error: {type(exc).__name__}: {exc}"}


def tool_mouse_move_and_click(args: dict) -> dict:
    """Smoothly move physical mouse cursor to (x, y), click, and display glowing animated ripple on screen."""
    try:
        from scripts.desktop_mouse_visualizer import click_mouse, get_mouse_position
        x = args.get("x")
        y = args.get("y")
        button = str(args.get("button") or "left")
        clicks = int(args.get("clicks") or 1)
        
        click_mouse(x=x, y=y, button=button, clicks=clicks, visual_ripple=True)
        pos = get_mouse_position()
        return {"text": f"Mouse clicked at ({pos[0]}, {pos[1]}) [button={button}, clicks={clicks}]. Visual ripple displayed."}
    except Exception as e:
        return {"text": f"Mouse click error: {e}"}


def tool_mouse_scroll(args: dict) -> dict:
    """Scroll mouse wheel (positive = up, negative = down)."""
    try:
        from scripts.desktop_mouse_visualizer import scroll_mouse
        amount = int(args.get("amount") or 1)
        scroll_mouse(amount)
        return {"text": f"Scrolled mouse by {amount} units."}
    except Exception as e:
        return {"text": f"Mouse scroll error: {e}"}


def tool_keyboard_type(args: dict) -> dict:
    """Physically type text characters into the currently focused window on screen."""
    try:
        from scripts.desktop_mouse_visualizer import type_text
        text = str(args.get("text") or "")
        delay = float(args.get("delay_seconds") or 0.02)
        type_text(text, delay=delay)
        return {"text": f"Typed {len(text)} characters into active window."}
    except Exception as e:
        return {"text": f"Keyboard typing error: {e}"}


def tool_keyboard_hotkey(args: dict) -> dict:
    """Press keyboard hotkey combination (e.g. 'ctrl+c', 'enter', 'win+r', 'alt+tab')."""
    try:
        from scripts.desktop_mouse_visualizer import press_hotkey
        keys = str(args.get("keys") or "").strip()
        press_hotkey(keys)
        return {"text": f"Pressed keyboard hotkey: {keys}"}
    except Exception as e:
        return {"text": f"Keyboard hotkey error: {e}"}


def tool_show_screen_glow_frame(args: dict) -> dict:
    """Display glowing full-screen perimeter border & top badge indicating AI Computer Control."""
    try:
        from scripts.desktop_mouse_visualizer import show_screen_glow_frame
        duration = float(args.get("duration_seconds") or 3.0)
        title = str(args.get("title") or "AI Computer Use Active")
        show_screen_glow_frame(duration=duration, title=title)
        return {"text": f"Displayed full-screen glow perimeter frame for {duration}s: [{title}]"}
    except Exception as e:
        return {"text": f"Screen glow error: {e}"}


def tool_get_screen_state(args: dict) -> dict:
    """Get screen resolution and current mouse cursor position."""
    try:
        from scripts.desktop_mouse_visualizer import get_mouse_position, get_screen_resolution
        sw, sh = get_screen_resolution()
        mx, my = get_mouse_position()
        return {"text": f"Screen Resolution: {sw}x{sh} | Current Mouse Position: ({mx}, {my})"}
    except Exception as e:
        return {"text": f"Screen state query error: {e}"}


def tool_capture_screen_preview(args: dict) -> dict:
    """Capture a live full desktop screenshot so the owner/agent can see exactly what is on the screen."""
    try:
        from scripts.desktop_mouse_visualizer import capture_screen_preview
        out_file = capture_screen_preview(output_name="latest_screen.png")
        if out_file and os.path.exists(out_file):
            size_kb = round(os.path.getsize(out_file) / 1024, 1)
            _notify_screen("Screen Captured", f"Saved to {out_file} ({size_kb} KB)", duration=2.5)
            return {
                "text": f"Screen preview captured successfully!\nPath: {out_file}\nFile size: {size_kb} KB\nThe active desktop screen has been recorded."
            }
        return {"text": "Screen capture was attempted but no image file was generated."}
    except Exception as e:
        return {"text": f"Screen capture error: {e}"}


def tool_show_screen_hud(args: dict) -> dict:
    """Display a floating HUD banner directly on the owner's desktop screen with an action title and detail."""
    title = str(args.get("title") or "AI Agent Notification")
    detail = str(args.get("detail") or "")
    duration = float(args.get("duration_seconds") or 4.0)
    _notify_screen(title, detail, duration=duration)
    return {"text": f"Displayed visual HUD on owner screen: [{title}] {detail}"}


def tool_self_harness_verify(args: dict) -> dict:
    """Execute standard verification suites (prod_check, secrets, billing truth, mcp_engineer)."""
    suite = str(args.get("suite") or "all").strip().lower()
    _notify_screen("Self-Harness Check", f"Running suite: {suite}", duration=4.0)
    
    results = []
    def run_check(label: str, script_args: list[str]):
        cmd = [PYTHON_EXE] + script_args
        try:
            r = subprocess.run(
                cmd,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            status = "PASS" if r.returncode == 0 else f"FAIL (exit {r.returncode})"
            summary = (r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "") if r.returncode == 0 else (r.stderr or r.stdout)[-300:]
            results.append(f"[{status}] {label}: {summary}")
        except Exception as e:
            results.append(f"[ERR] {label}: {e}")

    if suite in ("all", "prod_check"):
        run_check("prod_check.py", [str(REPO_ROOT / "scripts" / "prod_check.py")])
    if suite in ("all", "secrets"):
        run_check("check_secrets.py", [str(REPO_ROOT / "scripts" / "check_secrets.py")])
    if suite in ("all", "billing"):
        run_check("test_billing_truth_2026.py", ["-m", "pytest", "tests/test_billing_truth_2026.py", "-q"])
    if suite in ("all", "mcp_engineer"):
        run_check("verify_mcp_engineer.py", [str(REPO_ROOT / "scripts" / "verify_mcp_engineer.py")])

    return {"text": "\n".join(results) if results else f"Unknown suite: {suite}"}


def tool_hot_queue_triage(args: dict) -> dict:
    """Triage and inspect LeadGen Hot Queue leads."""
    action = str(args.get("action") or "summary").strip().lower()
    scope = str(args.get("scope") or "boss").strip().lower()
    _notify_screen("Hot Queue Triage", f"Action: {action} ({scope})", duration=3.0)
    
    cmd = [
        PYTHON_EXE,
        "-c",
        f"""
import sys, json
sys.path.insert(0, r'{str(REPO_ROOT)}')
from app.platform import reply_agent

action = '{action}'
scope = '{scope}'
if action == 'summary':
    rows = reply_agent.hot_queue(limit=50, scope=scope)
    print(json.dumps(reply_agent.hot_queue_summary(rows, scope=scope), indent=2))
elif action == 'list':
    rows = reply_agent.hot_queue(limit=30, scope=scope)
    print(json.dumps(rows[:15], indent=2))
elif action == 'mark_done':
    hq_id = '{args.get("hq_id", "")}'
    print('Marked done:', reply_agent.mark_handled(hq_id))
elif action == 'park':
    hq_id = '{args.get("hq_id", "")}'
    note = '{args.get("note", "")}'
    print('Parked:', reply_agent.park_for_admin(hq_id, note=note))
"""
    ]
    try:
        r = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        return {"text": r.stdout if r.returncode == 0 else f"HotQueue error: {r.stderr or r.stdout}"}
    except Exception as exc:
        return {"text": f"HotQueue query failed: {exc}"}


def tool_project_status(args: dict) -> dict:
    """Get high level LeadGen platform status and environment state."""
    summary = []
    summary.append(f"Repository Root: {REPO_ROOT}")
    summary.append(f"Python Executable: {PYTHON_EXE}")
    summary.append(f"1000-Engineers Canonical Doc: {'EXISTS' if ENGINEERS_1000_FILE.exists() else 'NOT FOUND'}")
    
    env_file = REPO_ROOT / ".env"
    summary.append(f".env Config File: {'PRESENT (Secured)' if env_file.exists() else 'NOT FOUND'}")
    
    graph_file = REPO_ROOT / "app" / "graphify-out" / "graph.json"
    summary.append(f"Graphify Code Graph: {'PRESENT (' + str(round(graph_file.stat().st_size / 1024, 1)) + ' KB)' if graph_file.exists() else 'NOT FOUND'}")
    
    return {"text": "\n".join(summary)}


TOOLS = [
    {
        "name": "thousand_engineers_talent",
        "description": "Access 1000-Engineers collective brain: doctrine, 10-lens review, or discipline packs (D1 Architecture, D2 Backend, D3 Frontend, D4 AI/LLM, D5 DB, D6 CI/CD, D7 SRE, D8 Security, D9 QA, D10 Perf, D11 Product, D12 Debugging).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Topic or discipline pack name (e.g., 'doctrine', '10-lens', 'd1', 'backend', 'security', 'all')",
                }
            },
        },
    },
    {
        "name": "mouse_move_and_click",
        "description": "Smoothly move physical mouse cursor to (x, y) on screen, click, and display an animated glowing click ripple ring so the owner visually sees the click.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "Target X pixel coordinate on screen"},
                "y": {"type": "integer", "description": "Target Y pixel coordinate on screen"},
                "button": {"type": "string", "description": "'left' (default), 'right', or 'middle'"},
                "clicks": {"type": "integer", "description": "Number of clicks (default: 1)"},
            },
        },
    },
    {
        "name": "mouse_scroll",
        "description": "Scroll mouse wheel up (positive amount) or down (negative amount).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "amount": {"type": "integer", "description": "Number of scroll clicks (+1 to scroll up, -1 to scroll down)"},
            },
            "required": ["amount"],
        },
    },
    {
        "name": "keyboard_type",
        "description": "Physically type text characters into the currently focused window on the desktop.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to type"},
                "delay_seconds": {"type": "number", "description": "Delay between keystrokes (default: 0.02)"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "keyboard_hotkey",
        "description": "Press keyboard shortcut combination (e.g. 'ctrl+c', 'win+r', 'enter', 'alt+tab', 'backspace').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keys": {"type": "string", "description": "Hotkey string (e.g., 'ctrl+s', 'enter', 'win+r')"},
            },
            "required": ["keys"],
        },
    },
    {
        "name": "show_screen_glow_frame",
        "description": "Display a full-screen perimeter glowing border and top banner on the owner's monitor to clearly indicate that AI Computer Use is active.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Banner text (e.g., 'Automating Form Fill')"},
                "duration_seconds": {"type": "number", "description": "Duration in seconds (default: 3.0)"},
            },
        },
    },
    {
        "name": "get_screen_state",
        "description": "Get primary screen resolution (width, height) and current mouse cursor position (x, y).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "execute_admin_command",
        "description": "Execute administrative, build, git, test, or automation commands in the project workspace (flashes visual HUD on owner screen).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to run in the repository root (e.g., 'pytest tests/test_billing_truth_2026.py -q')",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 120)",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "capture_screen_preview",
        "description": "Capture a live full desktop screenshot so the owner/agent can see exactly what is on the screen.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "show_screen_hud",
        "description": "Display a floating HUD banner directly on the owner's desktop screen with an action title and detail.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Banner title (e.g., 'Starting Browser Task')"},
                "detail": {"type": "string", "description": "Action details"},
                "duration_seconds": {"type": "number", "description": "Banner display duration (default: 4.0)"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "self_harness_verify",
        "description": "Run automated self-harness verification checks: prod_check.py, check_secrets.py, billing truth contract tests, and mcp_engineer audit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "suite": {
                    "type": "string",
                    "description": "Verification suite: 'all', 'prod_check', 'secrets', 'billing', or 'mcp_engineer'",
                }
            },
        },
    },
    {
        "name": "hot_queue_triage",
        "description": "Triage LeadGen Hot Queue leads, inspect summary counts, list warm inquiries, or mark actions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action: 'summary', 'list', 'mark_done', or 'park'",
                },
                "scope": {
                    "type": "string",
                    "description": "Scope: 'boss' (default), 'admin', or 'all'",
                },
                "hq_id": {
                    "type": "string",
                    "description": "Hot Queue Item ID (for mark_done or park)",
                },
                "note": {
                    "type": "string",
                    "description": "Optional note for parked items",
                },
            },
        },
    },
    {
        "name": "project_status",
        "description": "Check LeadGen platform files, Python environment, graph status, and invariants.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

HANDLERS = {
    "thousand_engineers_talent": tool_thousand_engineers,
    "mouse_move_and_click": tool_mouse_move_and_click,
    "mouse_scroll": tool_mouse_scroll,
    "keyboard_type": tool_keyboard_type,
    "keyboard_hotkey": tool_keyboard_hotkey,
    "show_screen_glow_frame": tool_show_screen_glow_frame,
    "get_screen_state": tool_get_screen_state,
    "execute_admin_command": tool_execute_admin_command,
    "capture_screen_preview": tool_capture_screen_preview,
    "show_screen_hud": tool_show_screen_hud,
    "self_harness_verify": tool_self_harness_verify,
    "hot_queue_triage": tool_hot_queue_triage,
    "project_status": tool_project_status,
}


def _resp(id, result=None, error=None) -> dict:
    msg = {"jsonrpc": "2.0", "id": id}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    return msg


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = req.get("id")
        method = req.get("method", "")
        if method == "initialize":
            out = _resp(
                rid,
                {
                    "protocolVersion": req.get("params", {}).get("protocolVersion", "2024-11-05"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "leadgen-admin-harness", "version": "1.0.0"},
                },
            )
        elif method == "notifications/initialized" or method.startswith("notifications/"):
            continue
        elif method == "ping":
            out = _resp(rid, {})
        elif method == "tools/list":
            out = _resp(rid, {"tools": TOOLS})
        elif method == "tools/call":
            name = req.get("params", {}).get("name", "")
            args = req.get("params", {}).get("arguments", {}) or {}
            handler = HANDLERS.get(name)
            if handler is None:
                out = _resp(rid, error={"code": -32601, "message": f"unknown tool {name}"})
            else:
                try:
                    text = handler(args)["text"]
                    out = _resp(rid, {"content": [{"type": "text", "text": text}]})
                except Exception as exc:
                    out = _resp(
                        rid, error={"code": -32603, "message": f"{type(exc).__name__}: {exc}"}
                    )
        else:
            out = _resp(rid, error={"code": -32601, "message": f"method not found: {method}"})
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
