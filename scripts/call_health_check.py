r"""
Call-health / dead-air detector for the live phone agent.
=========================================================

Reads the per-call transcripts (data/call_transcripts/YYYY-MM-DD.jsonl) and
flags the failure mode that made the agent "go silent after 2-3 turns":

  * DEAD-AIR calls   : the caller spoke (user_turns >= 1) but the agent recorded
                       ZERO assistant replies after the greeting -> it went deaf.
  * think_timeout    : turns where the THINK watchdog had to fire (a stuck LLM
                       stream / STT) — should be ~0 once the fix is healthy.
  * turn distribution: how many user turns calls actually reach.

Run locally (Windows):   .venv\Scripts\python.exe scripts\call_health_check.py
Run on the VPS:          docker exec leadgen_app python scripts/call_health_check.py
Optional: pass a day     python scripts/call_health_check.py 2026-06-22
          or N days back  python scripts/call_health_check.py --days 3

Exit code is 1 if any dead-air call is found today — handy for a cron/ntfy gate.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

_DIR = os.path.join("data", "call_transcripts")


def _greeting_only(messages: list[dict]) -> bool:
    """True if every assistant message is the opener (no real reply turns)."""
    return not any(m.get("role") == "assistant" for m in messages)


def _load_day(day: str) -> list[dict]:
    path = os.path.join(_DIR, f"{day}.jsonl")
    rows: list[dict] = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def _analyze(rows: list[dict]) -> dict:
    dead_air: list[dict] = []
    timeouts = 0
    turn_hist: Counter = Counter()
    total = len(rows)
    for r in rows:
        msgs = r.get("messages") or []
        ut = int(r.get("user_turns") or 0)
        turn_hist[ut] += 1
        # assistant replies that are NOT just the opening greeting:
        asst = [m for m in msgs if m.get("role") == "assistant"]
        # A call where the caller spoke but got <=1 assistant message (the greeting)
        # back is the dead-air signature.
        if ut >= 1 and len(asst) <= 1:
            dead_air.append(
                {
                    "sid": r.get("stream_sid"),
                    "niche": r.get("niche"),
                    "dur_s": r.get("duration_s"),
                    "user_turns": ut,
                    "assistant_msgs": len(asst),
                }
            )
        for tm in r.get("turn_metrics") or []:
            if tm.get("outcome") == "think_timeout":
                timeouts += 1
    return {
        "total_calls": total,
        "dead_air_calls": dead_air,
        "think_timeouts": timeouts,
        "turn_distribution": dict(sorted(turn_hist.items())),
    }


def main(argv: list[str]) -> int:
    days_back = 0
    day = None
    if "--days" in argv:
        try:
            days_back = int(argv[argv.index("--days") + 1])
        except Exception:
            days_back = 0
    elif argv and not argv[0].startswith("-"):
        day = argv[0]

    if day:
        days = [day]
    else:
        today = datetime.now(timezone.utc)
        days = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days_back + 1)]

    found_dead_air_today = False
    for d in days:
        rows = _load_day(d)
        rep = _analyze(rows)
        print(f"\n=== {d} ===  calls={rep['total_calls']}")
        print(f"  turn distribution (user_turns -> #calls): {rep['turn_distribution']}")
        print(f"  THINK watchdog fires (think_timeout): {rep['think_timeouts']}")
        da = rep["dead_air_calls"]
        if da:
            print(f"  !! DEAD-AIR calls: {len(da)} (caller spoke, agent gave no reply)")
            for c in da[:10]:
                print(
                    f"     - sid={c['sid']} niche={c['niche']} dur={c['dur_s']}s "
                    f"user_turns={c['user_turns']} assistant_msgs={c['assistant_msgs']}"
                )
            if d == days[0]:
                found_dead_air_today = True
        else:
            print("  OK — no dead-air calls")

    return 1 if found_dead_air_today else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
