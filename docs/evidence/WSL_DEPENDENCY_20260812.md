# WSL DEPENDENCY — 2026-08-12 (FreeBuff final revenue execution)

**Question:** Is WSL required for the core product, revenue operations, OmniRoute, or Buzz — and what exactly causes the repeated WSL window?

**Method:** Read-only inspection of live processes, parent/command-line, scheduled tasks, startup entries, terminal profiles, agent hooks, and every repo script that invokes `wsl.exe`. Nothing was disabled, uninstalled, or changed on the OS.

---

## 1. Live WSL state (probed 2026-08-12)

| Distro | State | Since | Evidence |
|---|---|---|---|
| `Ubuntu-24.04` | **Running** (headless) | wslhost PID 24056 started 2026-08-09 09:42:49 (`--distro-id {5e6eeccb…}`) | `wsl -l -v` = `* Ubuntu-24.04 Running 2` |
| `docker-desktop` | Running | wsl.exe PIDs 20440/33948/35084/40016 started 2026-08-10 12:47:41 (vpnkit-bridge + wsl-bootstrap) | Docker Desktop's own WSL2 backend |

- Ubuntu-24.04 has been up headless since ~09-08 09:42 — it is **not** being launched-and-killed per action; it persists.
- **No `wsl.exe` process with a launcher command line is currently running** (only Docker Desktop's backend processes). The visible popup therefore happens at *invocation time* when a launcher script runs, then exits.
- `wsl --status` → `Default Distribution: Ubuntu-24.04`, `Default Version: 2`. Windows Terminal default profile = **Windows PowerShell** (NOT WSL) — so the popup is not a terminal-profile artifact.

## 2. Root-cause search: what invokes WSL?

### 2a. Repo scripts that call `wsl.exe` (complete list, `grep -rln "wsl" scripts/*.ps1 scripts/*.bat`)

| Script | WSL call | Purpose | Invoked by |
|---|---|---|---|
| `scripts/start-leadgen-dev.ps1` L16 | `wsl.exe -d Ubuntu-24.04 --cd ~ -- bash -lc "echo $b64 \| base64 -d \| bash"` | Local dev bring-up: WSL Redis + OmniRoute tmux | **Manual** (owner/agent runs it) |
| `scripts/start-omniroute.ps1` L33 | `wsl.exe bash /mnt/c/…/omniroute_ensure_running.sh \| Out-Null` | Ensure OmniRoute gateway running | **Manual** + auto-called by `start-claude-omniroute.ps1` when gateway down |
| `scripts/omniroute-check.ps1` L9 | `wsl.exe -d Ubuntu-24.04 -- env -i HOME=/root … omniroute --version` | Gateway health check | Manual |
| `scripts/_canary_omni.bat` | `wsl bash -lc "ssh …"` (×4) | One-off canary: OmniRoute/dial-gate on VPS | Manual (canary) |
| `scripts/_canary_run.bat` | `wsl bash -lc "ssh … date +%H"` **in a `:WAIT_LOOP` every ~60 s until 9am IST** | One-off calling canary | Manual (canary); **if left running it pops a WSL window every minute** |
| `scripts/_canary_verify.bat` | `wsl bash -lc "ssh …"` (×4) | One-off deploy-verify canary | Manual |

### 2b. OS/Desktop triggers — inspected, NONE launch WSL with a window

- **Scheduled tasks**: only two match the project —
  - `\LeadGen Buzz Staff Pulse` (hourly, `cmd /d /c scripts\buzz_staff_pulse.bat`). The .bat runs **`python buzz_staff_pulse.py`** (SSH to VPS + Buzz relay send) — **no WSL in the .bat** (verified content). `LastTaskResult=3` (path not found) at 20:15 — the .bat was **recreated 2026-08-12 20:26** (parallel agent session), so the hourly run was flashing a **cmd** console (Interactive logon), not a WSL window.
  - `\OpenClaw Watchdog` (PowerShell, `-WindowStyle Hidden`, restarts loopback gateway :18789 if dead). **No WSL.**
- **Startup folder** (`…\Startup`): `Ollama.lnk`, `OpenClaw Gateway.vbs` (hidden WScript launch of `~\.openclaw\gateway.cmd` → node, no WSL), `TrendMaster_AutoStart.vbs.disabled`, `Wispr Flow.lnk`. **No WSL entry.**
- **HKCU\…\CurrentVersion\Run**: OneDrive, Warp, MiniMax Code, Edge, Teams. **No WSL/leadgen entry.**
- **Terminal profiles**: default = Windows PowerShell; Ubuntu-24.04 profiles present but **hidden=false, not default, not auto-started**.
- **Agent hooks**: `.claude/hooks/` (guard.py, write_guard.py, skill_reminder.py, reward_capture.py) — **no WSL references** (verified full contents). `.codex/config.toml` — no hooks invoking WSL. `.codex/environments/environment.toml` — empty setup script. Repo `.claude/settings.json` / user `~/.claude/settings.json` — permission allow/deny lists, no WSL launch.
- **`.wslconfig`**: absent (no auto-start config).

### 2c. Verdict on the "repeated WSL window"

**ROOT-CAUSE CLASSIFICATION: `PROBABLE` — NOT `VERIFIED`.** The popup-time `wsl.exe` PID, its parent PID and its command line were **not captured** (no popup occurred during the probe window). The per-action-launcher explanation below is an **inference** drawn from (a) the complete absence of any OS/Desktop/scheduled/startup/hook trigger that launches WSL, and (b) the existence of manual launchers that spawn `wsl.exe` from console-less parents. **The mere existence of WSL launchers is NOT proof of causation** — something else (e.g. a tool-call harness, a desktop app, a keystroke combo) could equally be the caller. Upgrade path to `VERIFIED`: capture popup-time process correlation — poll `Get-CimInstance Win32_Process` during the next popup (or Sysmon/Procmon event 1) and record `wsl.exe` PID → parent PID → command line → owning script, then reproduce at least twice with matching results.

- **No OS/Desktop setting launches WSL at login or on a timer** (inspected: scheduled tasks, Startup folder, HKCU Run, terminal profiles, agent hooks, `.wslconfig` absent). The only project scheduled task (Buzz Staff Pulse) uses **cmd + python + SSH**, not WSL.
- **Most plausible per-action mechanism (PROBABLE):** every time `start-leadgen-dev.ps1`, `start-omniroute.ps1`, `omniroute-check.ps1`, or a `_canary_*.bat` is run (by an owner or an agent tool call), `wsl.exe` spawns a **visible console window** from the PowerShell/agent context, runs, and closes. `_canary_run.bat`'s `:WAIT_LOOP` can repeat this **every 60 seconds** if left running.
- These launchers are **explicitly opt-in** (manual scripts; `start-buzz-omniroute.ps1` is preview-by-default; nothing calls them automatically). No repo change is required for revenue — see §4.

---

## 3. Task-by-task WSL matrix

| Workflow | WSL required? | Current trigger | Windows-native alternative | Revenue impact |
|---|---|---|---|---|
| Editing + testing FastAPI | **NOT REQUIRED** | — (`.venv\Scripts\python.exe`, Windows uvicorn) | Native Windows venv; Redis missing → in-memory fallback (fail-open) | None |
| Public website + Marketing funnel | **NOT REQUIRED** | — (prod is VPS Docker; `/audit` `/pricing` `/start` served from prod) | Plain browser/curl | None |
| Hot Queue owner workflow (`/app/inbox`) | **NOT REQUIRED** | — (web app, admin login) | Browser | None |
| Manual UPI approval | **NOT REQUIRED** | — (web app admin) | Browser | None |
| Production deployment | **NOT REQUIRED** | — (`deploy_vps.sh` on VPS; local = Windows git push + SSH) | Git for Windows ssh.exe + `deploy_vps.sh` | None |
| OmniRoute gateway | **REQUIRED (optional feature)** | Manual `start-leadgen-dev.ps1` / `start-omniroute.ps1` | Only gateway host is WSL; skip = free_ai fallback chain still works (degraded-mode documented in launcher) | None (optional cost-saving lane) |
| Buzz coordination | **OPTIONAL** | Manual `start-buzz-omniroute.ps1 -Launch` (preview by default) | Buzz Desktop native harness + `buzz_staff_pulse.py` (SSH) run **without** WSL; **only** the optional OmniRoute routing lane requires WSL | None |
| FreeBuff worktrees | **NOT REQUIRED** | — (git worktree + Windows tools) | None | None |
| Optional voice/provider canaries (`_canary_*.bat`) | **NOT REQUIRED** | Manual; `_canary_run.bat` waits for 9am IST | Same SSH via Git ssh.exe in PowerShell | None (voice FROZEN) |
| Docker Desktop local (not prod) | Uses WSL2 backend silently | Docker Desktop auto-start | Docker Desktop needs WSL2, but this is the app's own distro, windowless | None (prod unaffected) |

### Required-WSL verdicts
- **Core product (Marketing Automation): `WSL_NOT_REQUIRED`**
- **Revenue operations (Hot Queue, UPI, funnel): `WSL_NOT_REQUIRED`**
- **OmniRoute: `WSL_REQUIRED` (only as an optional free-LLM cost lane; skip = graceful degraded mode)**
- **Buzz: `WSL_OPTIONAL` (Buzz Desktop + SSH-based pulse run without WSL; only the OmniRoute routing lane needs it)**

**The core Marketing/revenue lane remains fully usable with WSL stopped.**

---

## 4. If the owner wants the popups gone

1. **Stop the hourly cmd-window flash** (if unwanted): the `LeadGen Buzz Staff Pulse` scheduled task runs hourly, `cmd /d /c`, Interactive logon → flashes a console. It was just re-created by a parallel agent session (2026-08-12 20:26); do not disable it without checking with that workstream. Reversible owner action (not performed here):
   ```powershell
   Disable-ScheduledTask -TaskName "LeadGen Buzz Staff Pulse"   # rollback: Enable-ScheduledTask -TaskName "LeadGen Buzz Staff Pulse"
   ```
2. **Do not run the WSL launchers from agent tool calls** unless OmniRoute is actually needed; prefer:
   - `wsl.exe -d Ubuntu-24.04 --exec …` does **not** exist as a window-hiding flag — the window comes from spawning `wsl.exe` from a console-less parent. If a silent run is ever required, invoke it inside an already-hidden host (e.g. `Start-Process wsl.exe -WindowStyle Hidden -ArgumentList … -Wait`) — **not done here** because no revenue blocker exists and the tested bring-up path (`tests/test_omniroute_scripts.py` pins `wsl.exe -d Ubuntu-24.04` in launcher text) should not be churned for a cosmetic issue.
3. **No `.wslconfig` / startup / terminal change is needed** — none of them launches WSL with a window today.

---

## 5. Evidence inventory

| Check | Result | Source |
|---|---|---|
| `wsl -l -v` | Ubuntu-24.04 Running, docker-desktop Running | probe 2026-08-12 |
| Running `wsl.exe` parents | docker-desktop only (vpnkit/wsl-bootstrap), parent `com.docker.backend.exe` | `Get-CimInstance Win32_Process` |
| Scheduled tasks (project) | Buzz Staff Pulse (cmd+python, **no WSL**), OpenClaw Watchdog (hidden PS, no WSL) | `Get-ScheduledTask` |
| Startup folder / HKCU Run | Ollama, OpenClaw Gateway.vbs (hidden node), Wispr Flow, OneDrive/Warp/MiniMax/Edge/Teams — **no WSL** | `Get-ChildItem` + registry |
| Terminal default profile | Windows PowerShell (not WSL) | Windows Terminal settings.json |
| Repo WSL callers | 6 scripts, all manual/opt-in; none scheduled | `grep -rln "wsl" scripts/` |
| Agent hooks | `.claude/hooks/*.py`, `.codex/*`, settings.json — no WSL | full file reads |
| `.wslconfig` | absent | `cat` |
| Popup-time `wsl.exe` PID/parent/cmdline correlation | **NOT CAPTURED** — no popup observed during probe window ⇒ root cause `PROBABLE`, not `VERIFIED` | live probes 2026-08-12 |

**Label:** DIRECT_HOST_VERIFIED (probes 2026-08-12 — idle-state process tree, tasks, startup, hooks) · GIT_VERIFIED (repo grep) · **ROOT CAUSE: `PROBABLE` (popup-time correlation pending)** · No OS/Desktop mutation performed.

---
**Canary:** 🐦 pelican
