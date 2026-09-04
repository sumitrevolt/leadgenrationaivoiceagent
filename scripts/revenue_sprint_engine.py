"""Revenue Sprint Engine — 24x7 continuous cycle manager for the ₹5L/7-day goal.

This is the project-tracked/path-hardened copy of the owner's auto-pilot. It drives
the **owner's Hermes Desktop CLI** (`hermes kanban swarm`) to launch one sprint
cycle of workers -> verifier -> synthesizer. When a cycle's synthesizer card is
done, the next tick launches the next cycle automatically.

Compliance GUARDRAILS (never relax these) are baked into every goal text:

* NO bulk or cold WhatsApp auto-sends — drafts only, owner 1-click review.
* Email volume max 25/day.
* Outbound calling ONLY via the VPS scheduler (DND fail-closed, TRAI window untouched).
* Payment/UPI confirmations are OWNER-ONLY — never automate money steps.

This engine is owner-gated and read-mostly: it spawns Hermes bots that DRAFT
outreach; it never sends, and never automates money.

Usage (run from the project root on the owner's Windows machine):

    python scripts/revenue_sprint_engine.py --status    # print current state + cycle status
    python scripts/revenue_sprint_engine.py --dry-run   # show what a launch would do, no-op
    python scripts/revenue_sprint_engine.py --tick      # default: normal cycle manager
    python scripts/revenue_sprint_engine.py --force     # launch next cycle even if current not done

Env overrides:
    HERMES_CLI        absolute path to the Hermes CLI (binary or .cmd)
    SPRINT_STATE_FILE path to the cycle state JSON (default: repo data/sprint_state.json)
    SPRINT_BRIEF      path to the leadgen_daily_brief.py probe (default: repo scripts/)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

# --- Sprint constants (owner set 2026-08-22) ---------------------------------
START = date(2026, 8, 22)
GOAL_DAYS = 7
GOAL_TOTAL_INR = 500_000

REPO_ROOT = Path(__file__).resolve().parent.parent


# --- Path discovery -----------------------------------------------------------
def find_hermes() -> str:
    """Return a runnable Hermes CLI path. Own machine = venv Scripts/hermes.exe."""
    env = os.environ.get("HERMES_CLI", "").strip()
    if env and Path(env).exists():
        return env

    localappdata = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
    base = Path(localappdata) / "hermes"
    candidates = [
        base / "hermes-agent" / "venv" / "Scripts" / "hermes.exe",
        base / "hermes-agent" / "bin" / "hermes.cmd",
        base / "bin" / "hermes.cmd",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return shutil.which("hermes") or "hermes"


def state_file() -> Path:
    env = os.environ.get("SPRINT_STATE_FILE", "").strip()
    if env:
        return Path(env)
    return REPO_ROOT / "data" / "sprint_state.json"


def brief_path() -> Path:
    env = os.environ.get("SPRINT_BRIEF", "").strip()
    if env:
        return Path(env)
    return REPO_ROOT / "scripts" / "leadgen_daily_brief.py"


# --- State ----------------------------------------------------------------------
def load_state() -> dict:
    p = state_file()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    # Fresh start: cycle 0, no synthesizer yet -> the next tick launches cycle 1.
    return {"cycle": 0, "synth_id": None, "root": None, "started_at": None}


def save_state(s: dict) -> None:
    p = state_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(s, indent=2), encoding="utf-8")


def day_of_sprint() -> int:
    return (date.today() - START).days + 1


# --- Hermes task helpers -------------------------------------------------------
def run(cmd: list, timeout: int = 90) -> subprocess.CompletedProcess:
    # On Windows, .cmd scripts need shell; bare exe does not. Use the resolved name.
    return subprocess.run(
        cmd, capture_output=True, timeout=timeout, text=True,
        encoding="utf-8", errors="replace",
    )


# Statuses that mean "this cycle is still actively working".
_ACTIVE = {"todo", "ready", "running", "review", "verifying", "in_review", "blocked", "scheduled"}


def task_status(task_id: str) -> str:
    out = run([find_hermes(), "kanban", "show", task_id])
    text = (out.stdout or "") + (out.stderr or "")
    m = re.search(r"status:\s+(\S+)", text)
    return m.group(1).lower() if m else "unknown"


def synth_still_active(synth_id: str) -> bool:
    if not synth_id:
        return False
    status = task_status(synth_id)
    # "unknown" == the card no longer exists (state points at a dead/finished id).
    if status == "unknown":
        return False
    return status in _ACTIVE


# --- Cycle launch ---------------------------------------------------------------
def launch_cycle(cycle: int, log) -> tuple[dict | None, str]:
    day = day_of_sprint()
    goal = (
        f"REVENUE SPRINT CYCLE-{cycle} (goal Rs {GOAL_TOTAL_INR:,} in {GOAL_DAYS} days, "
        f"today=day{day}). Live data ke liye run karo: python "
        f"{brief_path()} (read-only prod stats). WORKERS: sales=draft personalized "
        f"follow-up EMAILs for top warm leads; mercury=draft 2 social posts + 1 blog "
        f"outline promoting LeadGen Main plan Rs1999; operations=pipeline audit - "
        f"stale/blocked leads + dialer readiness. VERIFIER sentry: reject compliance "
        f"violations + wrong pricing (Rs1999/Rs5999 only). SYNTHESIZER commander: final "
        f"ranked action list for OWNER. GUARDRAILS: NO bulk/cold WhatsApp auto-sends - "
        f"drafts only for owner 1-click review; email volume max 25/day; outbound calling "
        f"ONLY via VPS scheduler (DND fail-closed, TRAI window untouched); payment/UPI "
        f"confirmations are OWNER-ONLY - never automate money steps."
    )
    cmd = [
        find_hermes(), "kanban", "swarm", goal,
        "--worker", "sales:Draft follow-up emails for top warm leads",
        "--worker", "mercury:Draft content pack for LeadGen marketing",
        "--worker", "operations:Pipeline audit + dialer readiness",
        "--verifier", "sentry",
        "--synthesizer", "commander",
        "--created-by", "revenue-sprint-engine",
        "--priority", "1",
        "--idempotency-key", f"sprint-{cycle}-{START.isoformat()}",
    ]
    log(f"[launch_cycle] {find_hermes()} kanban swarm ...")
    out = run(cmd, timeout=180)
    text = (out.stdout or "") + (out.stderr or "")
    m = re.search(r"Synthesizer:\s*(t_\w+)", text)
    root = re.search(r"Swarm root:\s*(t_\w+)", text)
    if not m:
        return None, text.strip()[:400]
    return {"root": root.group(1) if root else "?", "synth": m.group(1)}, ""


# --- Main ---------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--status", action="store_true", help="print state + current cycle status")
    ap.add_argument("--dry-run", action="store_true", help="show what a launch would do, no-op")
    ap.add_argument("--tick", action="store_true", help="normal cycle manager run (default)")
    ap.add_argument("--force", action="store_true", help="launch next cycle even if current not done")
    args = ap.parse_args(argv)

    log = lambda msg: print(msg, flush=True)  # noqa: E731

    day = day_of_sprint()
    cls = find_hermes()
    st = load_state()

    log(f"HERMES CLI : {cls}")
    log(f"STATE      : {state_file()}")
    log(f"DAY        : {day}/{GOAL_DAYS} (started {START})")

    if day > GOAL_DAYS:
        log(
            f"SPRINT ENDED (day {GOAL_DAYS}/{GOAL_DAYS}). "
            f"Final summary owner ke saath review karo."
        )
        return 0

    if args.status:
        log(f"CYCLE      : {st.get('cycle', 0)}")
        log(f"SYNTH      : {st.get('synth_id')} (root {st.get('root')})")
        if st.get("synth_id"):
            log(f"SYNTH_STAT : {task_status(st['synth_id'])}")
        else:
            log("SYNTH_STAT : none (fresh start — next tick launches cycle 1)")
        return 0

    # If the current cycle's synthesizer is still working, wait for it.
    if not args.force and synth_still_active(st.get("synth_id")):
        log(
            f"CYCLE-{st.get('cycle')} chal raha hai (day {day}/{GOAL_DAYS}) - "
            f"synthesizer status: {task_status(st['synth_id'])}. Next check 4 ghante me."
        )
        return 0

    if args.dry_run:
        nxt = (st.get("cycle") or 0) + (1 if st.get("synth_id") else 0)
        nxt = max(nxt, 1)
        log(f"DRY-RUN    : would launch CYCLE-{nxt} (day {day}/{GOAL_DAYS}) via kanban swarm.")
        s = st.get("synth_id")
        if s and not args.force:
            log(f"DRY-RUN    : current synth '{s}' is active (status {task_status(s)}) -> would SKIP.")
        return 0

    nxt = (st.get("cycle") or 0) + (1 if st.get("synth_id") else 0)
    if nxt < 1:
        nxt = 1

    ids, err = launch_cycle(nxt, log)
    if not ids:
        log(f"CYCLE-{nxt} LAUNCH FAILED: {err}")
        return 1

    save_state({"cycle": nxt, "synth_id": ids["synth"], "root": ids["root"], "started_at": date.today().isoformat()})
    log(
        f"CYCLE-{nxt} LAUNCHED (day {day}/{GOAL_DAYS}) | root={ids['root']} "
        f"synth={ids['synth']} | 3 bots: sales+mercury+operations -> sentry -> commander"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
