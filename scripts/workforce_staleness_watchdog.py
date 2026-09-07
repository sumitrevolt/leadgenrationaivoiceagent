#!/usr/bin/env python3
"""workforce_staleness_watchdog.py — alert when the 31-agent workforce status goes stale.

WHY
---
`scripts/autonomous_workforce_orchestrator.py` is a `while True` daemon whose
liveness signal is `workforce_live_status.json` (dual-written to
`var/runtime-data/` and `data/`). Two failure modes hide behind a "process
alive" check (see `ensure_workforce_orchestrator.ps1`):

  1. process dead          -> keepalive restarts it (solved)
  2. process alive-but-hung / writing nothing -> NOTHING catches this today

This watchdog is the progress-signal check: it reads the NEWEST of the two
status files and alerts (ntfy) when no cycle has written for
`--max-age-s` (default 900s = 15 min; the orchestrator cycles every ~15s).
Alert fires ONCE on the transition to stale, then a recovery ping when fresh
again — same state machine as `omniroute_combo_watchdog.py`.

STATE & ALERTING
----------------
Consecutive-stale counters live in `data/workforce_staleness_state.json`
(gitignored via `data/*.json`). Alerts go through `app.integrations.ntfy`
(gated NTFY_URL+NTFY_TOPIC — unset = print-only, never raises).

USAGE
-----
    .venv\\Scripts\\python.exe scripts/workforce_staleness_watchdog.py             # one pass
    .venv\\Scripts\\python.exe scripts/workforce_staleness_watchdog.py --loop 300  # every 5 min
    .venv\\Scripts\\python.exe scripts/workforce_staleness_watchdog.py --quiet

Wired into `scripts/ensure_workforce_orchestrator.ps1` (scheduled every 5 min
via task `LeadGen-Workforce-Orchestrator-Keepalive`), so the keepalive restart
covers failure mode 1 while this covers failure mode 2.

Exit codes (one-shot): 0 = status fresh · 1 = stale past threshold ·
2 = no status file found at all.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS_FILES = [
    REPO_ROOT / "var" / "runtime-data" / "workforce_live_status.json",
    REPO_ROOT / "data" / "workforce_live_status.json",
]
STATE_FILE = REPO_ROOT / "data" / "workforce_staleness_state.json"

DEFAULT_MAX_AGE_S = 900  # 15 min; orchestrator cycle interval is ~15s


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_state(state_path: Path) -> dict:
    try:
        with open(state_path, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(state_path: Path, state: dict) -> None:
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001 — state is advisory, never crash
        print(f"[WARN] state write failed: {e}")


def newest_status_age_s(status_paths: list[Path], now: float | None = None) -> float | None:
    """Age (seconds) of the newest status file, or None if none exists.

    Uses file mtime — the orchestrator rewrites both copies every cycle, so the
    newest mtime IS the progress signal (R1: primitive evidence, not vibes).
    """
    now = time.time() if now is None else now
    ages: list[float] = []
    for p in status_paths:
        try:
            ages.append(now - p.stat().st_mtime)
        except OSError:
            continue
    return min(ages) if ages else None


def _alert(title: str, body: str, priority: str = "high") -> None:
    """ntfy push when configured (repo-standard), else print. Never raises."""
    try:
        import asyncio

        from app.integrations import ntfy

        async def _go():
            try:
                await ntfy.push(title, body, priority=priority, tags=["computer"])
            except Exception:
                pass

        asyncio.run(_go())
    except Exception:  # noqa: BLE001 — watchdog must survive missing deps
        pass
    print(f"[ALERT] {title}\n{body}")


def run_once(
    status_paths: list[Path],
    state_path: Path,
    max_age_s: int,
    alert_sink=None,
    now: float | None = None,
    quiet: bool = False,
) -> int:
    """One staleness pass. Returns process exit code."""
    alert = alert_sink or _alert
    state = _load_state(state_path)
    was_alerted = bool(state.get("alerted"))
    fails = int(state.get("fails") or 0)
    age = newest_status_age_s(status_paths, now=now)

    if age is None:
        if not was_alerted:
            _save_state(state_path, {**state, "alerted": True, "fails": fails + 1, "last": _now_iso()})
            alert(
                "🚨 Workforce status MISSING",
                "No workforce_live_status.json found in var/runtime-data/ or data/.\n"
                "The 31-agent orchestrator has likely never run on this machine.\n"
                "Fix: powershell -File scripts\\ensure_workforce_orchestrator.ps1",
                priority="urgent",
            )
        elif not quiet:
            print("[STALE] status file missing (already alerted)")
        return 2

    stale = age > max_age_s
    mins = round(age / 60, 1)
    if stale:
        fails += 1
        if not was_alerted:
            _save_state(state_path, {**state, "alerted": True, "fails": fails, "last": _now_iso()})
            alert(
                "🚨 Workforce status STALE",
                f"No orchestrator cycle write for {mins} min (threshold {max_age_s}s).\n"
                "Process may be hung (alive-but-not-writing) — keepalive no-op hai is case me.\n"
                f"Fix: kill python running autonomous_workforce_orchestrator.py, phir "
                "scripts\\ensure_workforce_orchestrator.ps1",
            )
        elif not quiet:
            print(f"[STALE] {mins} min old (already alerted)")
        return 1

    if was_alerted:
        _save_state(state_path, {"alerted": False, "fails": 0, "last": _now_iso()})
        alert(
            "✅ Workforce status recovered",
            f"Orchestrator cycle write fresh again ({mins} min old, was stale).",
            priority="default",
        )
    else:
        _save_state(state_path, {**state, "alerted": False, "fails": 0, "last": _now_iso()})
    if not quiet:
        print(f"[OK] status fresh ({mins} min old, threshold {max_age_s}s)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Alert when workforce_live_status.json goes stale (hung orchestrator catch)"
    )
    ap.add_argument(
        "--status-file",
        action="append",
        default=None,
        help="status file path (repeatable; default = repo dual-write locations)",
    )
    ap.add_argument("--state-file", default=str(STATE_FILE), help="state JSON path")
    ap.add_argument("--max-age-s", type=int, default=DEFAULT_MAX_AGE_S, help="staleness threshold s")
    ap.add_argument("--loop", type=float, default=0.0, help="run periodically every N seconds (0 = one pass)")
    ap.add_argument("--quiet", action="store_true", help="only print alerts")
    args = ap.parse_args()

    status_paths = (
        [Path(p) for p in args.status_file] if args.status_file else list(STATUS_FILES)
    )
    state_path = Path(args.state_file)

    while True:
        try:
            code = run_once(
                status_paths, state_path, max(1, args.max_age_s), quiet=args.quiet
            )
        except KeyboardInterrupt:
            return 130
        except Exception as e:  # noqa: BLE001 — outer guard
            print(f"[ERR] pass crashed: {type(e).__name__}: {e}")
            code = 2
        if args.loop <= 0:
            return code
        time.sleep(args.loop)


if __name__ == "__main__":
    sys.exit(main())
