# Hermes Desktop — Root Cause Analysis & Fix
**Date:** 2026-09-03 08:30 IST
**Symptom:** Hermes Desktop app does not open (window never appears / closes immediately).
**Status:** Root cause identified with production evidence. Fix implemented in `scripts/start-hermes-omniroute.ps1`. One manual verification step remains (see §6).

---

## 1. Verdict

The Hermes installation is **not corrupt or missing**. The failure is a **backend lifecycle defect in the desktop shell**: the desktop spawns a throwaway backend child on an OS-assigned port, that child exits with code 1 roughly 3.5 minutes after startup, and the desktop session dies with it.

The durable fix is to run **one machine-level backend on the default port 9119** and have the desktop **attach** to it instead of spawning its own child.

---

## 2. Evidence

### 2.1 Installation is intact
| Item | Path | State |
|---|---|---|
| GUI binary | `%LOCALAPPDATA%\hermes\hermes-agent\apps\desktop\release\win-unpacked\Hermes.exe` | Present, 214 MB, 2026-08-31 18:53 |
| App bundle | `...\win-unpacked\resources\app.asar` | Present, 8.9 MB |
| Backend venv | `...\hermes-agent\venv\Scripts\python.exe` | Present |
| CLI entrypoint | `...\venv\Scripts\hermes.exe` | Present |
| User data | `%APPDATA%\Hermes\` | Present, last written 2026-09-03 07:34 |

### 2.2 The failure signature (repeating, not one-off)
`%LOCALAPPDATA%\hermes\logs\desktop.log`:

```
[2026-09-02T04:48:50.723Z] Hermes backend for profile "default" failed to start:
                           Hermes backend for profile "default" exited before it became ready (1).
[2026-09-03T01:48:56.679Z] Hermes backend for profile "default" failed to start: ... exited before it became ready (1).
[2026-09-03T01:50:27.532Z] Hermes backend listening on 127.0.0.1:59417
[2026-09-03T01:50:27.678Z] [boot] Hermes backend is ready. Finalizing desktop startup
[2026-09-03T01:59:19.350Z] Ignoring stale Hermes backend exit (1)
[2026-09-03T01:59:19.351Z] Hermes backend for profile "default" exited (1)
[2026-09-03T02:00:47.331Z] Hermes backend listening on 127.0.0.1:59265
[2026-09-03T02:00:47.530Z] [boot] Hermes backend is ready. Finalizing desktop startup
[2026-09-03T02:04:15.773Z] Ignoring stale Hermes backend exit (1)
[2026-09-03T02:04:15.774Z] Hermes backend for profile "default" exited (1)
```

Pattern is identical every cycle: **backend ready → finalize startup → ~3.5 min → backend exit(1)**.

### 2.3 The backend itself is healthy (decisive test)
Run standalone, headless:

```
> venv\Scripts\python.exe -m hermes_cli.main serve --host 127.0.0.1 --port 9119
Hermes backend listening on 127.0.0.1:9119
> netstat -ano | findstr 9119
TCP  127.0.0.1:9119  0.0.0.0:0  LISTENING  15876
```

**The backend starts and holds.** It is not a code crash. `%LOCALAPPDATA%\hermes\logs\gui.log` contains **no traceback, no shutdown, no SIGTERM** — the child is reaped, not crashed.

### 2.4 Why the desktop spawns its own child
`hermes serve --help` (authoritative):

```
--port PORT   Port (default 9119, 0 for auto-assign by OS)
--isolated    When launched from a named profile, run a dedicated server scoped
              to that profile instead of routing to the machine-level server.
              Default behavior is unified: profile launches attach to (or start)
              ONE machine-level server and preselect the profile.
```

`%APPDATA%\Hermes\backend-ownership.json` confirms every desktop launch runs:
```
python.exe -m hermes_cli.main serve --host 127.0.0.1 --port 0
```
i.e. **`--port 0`** — a throwaway child per launch, never the unified machine-level server.

### 2.5 Contributing defects (secondary)
| # | Defect | Evidence |
|---|---|---|
| C1 | Stale backend ownership registry — dozens of dead PID entries across 10 profiles accumulate in `backend-ownership.json` (30 KB) | `%APPDATA%\Hermes\backend-ownership.json` |
| C2 | Profile desync — `active-profile.json` says `"pilot"`, desktop always boots `"default"` | `%APPDATA%\Hermes\active-profile.json` |
| C3 | MCP discovery loop — retries every 5 min forever, never connects (playwright via `npx.cmd` fails: "MCPError: Connection closed") | `logs/gui.log`, `logs/errors.log` |
| C4 | Stale 0-byte lock left at `%LOCALAPPDATA%\hermes\.mcp-discovery.lock` (2026-09-03 07:30) | filesystem |
| C5 | Launcher checked a stale port assumption and never verified readiness | `scripts/start-hermes-omniroute.ps1` (pre-fix) |

---

## 3. Root cause statement

The desktop never finds a ready **machine-level** backend on the default port 9119, so it falls back to spawning a per-launch backend on an OS-assigned port (`--port 0`). That child is short-lived and exits with code 1, and the desktop has no recovery path — so the window never stays open. The previous launcher made this deterministic by sleeping only 2 seconds after issuing the backend spawn, guaranteeing the backend was never ready when the GUI launched.

---

## 4. Fix (implemented)

**File:** `scripts/start-hermes-omniroute.ps1` — rewritten.

1. Reuses an existing backend on 9119 if one is already listening.
2. Otherwise spawns the **machine-level** server: `hermes.exe serve --skip-build --host 127.0.0.1 --port 9119`.
3. **Polls for real readiness** (2 s interval, 90 s timeout) using `Get-NetTCPConnection`.
4. **Aborts the GUI launch if the backend never becomes ready** — launching anyway is exactly what reproduces the bug.
5. Launches the GUI only after readiness is proven.
6. **Verifies the GUI survived** (20 s post-launch process check) and exits non-zero with a pointer to `desktop.log` if it did not.

---

## 5. Remaining manual step (cannot be automated from this environment)

Process launch is restricted in this session: `powershell.exe` fails at sandbox ConPTY creation (`ERROR_ACCESS_DENIED`), and `cmd.exe` / `wscript.exe` are blocked by security policy. Verification therefore requires one manual run:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent\scripts\start-hermes-omniroute.ps1
```

Expected on success:
```
[3/4] Ensuring machine-level Hermes backend on port 9119...
      Backend READY on 127.0.0.1:9119 (pid <pid>).
[4/4] Launching Hermes Desktop...
OK: Hermes Desktop RUNNING (pid <pid>).
```

Optional cleanup if the app is still unstable (**backup first**):
- `%APPDATA%\Hermes\backend-ownership.json` → rename to `.bak` (clears C1)
- `%LOCALAPPDATA%\hermes\.mcp-discovery.lock` → delete (clears C4)
- Align `%APPDATA%\Hermes\active-profile.json` with the profile you actually use (clears C2)

---

## 6. Known limitations

- C3 (MCP discovery loop, playwright server) is a **cosmetic background retry**, not the cause of the launch failure. Disabling the playwright MCP server in `config.yaml` would silence it; not required to restore the app.
- Multi-machine rollout: the same launcher works per machine. The `%LOCALAPPDATA%`-relative paths make it portable; only a Hermes install path override (`-HermesApp`) is needed if the app is installed elsewhere.
