#!/usr/bin/env python3
"""Per-component voice latency report (P1 observability).

Reads ``data/turn_metrics/*.jsonl`` (written by ``app.voice_agent.turn_metrics``)
and prints P50/P95/avg/max/n for every ``*_ms`` component — stt / llm_first /
tts_first / turn / total. Read-only: never writes, never touches a live call.

Why: research principle #2 — "you can't improve what you can't see." This rolls
the per-turn metrics up into a quick scorecard against best-practice latency
targets (TTFA ~1.2-1.5s) so you can spot which component is slow.

Usage:
    python scripts/latency_report.py                 # today (UTC)
    python scripts/latency_report.py 2026-06-22      # a specific day
    python scripts/latency_report.py --days 7        # combine last 7 days
    python scripts/latency_report.py --by-path       # split by path (vobiz_stream/...)
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

# Make the repo importable when run from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.voice_agent import turn_metrics as tm  # noqa: E402

# Best-practice p95 targets (ms). TTFA (time-to-first-audio) ~1.2-1.5s end-to-end;
# component budgets are rough guidance from the production-voice-agent research.
TARGETS = {
    "stt_ms": 400,
    "llm_first_ms": 700,
    "llm_ms": 1200,
    "tts_first_ms": 400,
    "tts_ms": 800,
    "turn_ms": 1500,
    "total_ms": 1500,
}


def _load_days(days: int) -> list[dict]:
    recs: list[dict] = []
    today = datetime.now(timezone.utc).date()
    for i in range(days):
        day = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        recs.extend(tm.load_day(day))
    return recs


def _fmt_metrics(roll: dict) -> str:
    metrics = roll.get("metrics", {})
    if not metrics:
        return "  (no *_ms data in these turns)"
    lines = []
    hdr = f"  {'component':<16}{'p50':>8}{'p95':>8}{'avg':>8}{'max':>8}{'n':>7}   status"
    lines.append(hdr)
    lines.append("  " + "-" * (len(hdr) - 2))
    for key, m in metrics.items():
        tgt = TARGETS.get(key)
        status = ""
        p95 = m.get("p95")
        if tgt is not None and p95 is not None:
            status = "OK" if p95 <= tgt else f"SLOW (>{tgt})"
        lines.append(
            f"  {key:<16}{m['p50']:>8}{p95:>8}{m['avg']:>8}{m['max']:>8}{m['n']:>7}   {status}"
        )
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Voice per-component latency report")
    ap.add_argument("date", nargs="?", help="YYYY-MM-DD (UTC). Default: today.")
    ap.add_argument("--days", type=int, default=1, help="combine the last N days")
    ap.add_argument("--by-path", action="store_true", help="also split by the 'path' field")
    args = ap.parse_args()

    if args.date:
        recs = tm.load_day(args.date)
        label = args.date
    else:
        recs = _load_days(max(1, args.days))
        label = "today" if args.days == 1 else f"last {args.days} days"

    print(f"\nVoice latency - {label}  ({len(recs)} turns)\n")
    if not recs:
        print("  No turn_metrics found. Make sure TURN_METRICS != 0 and the voice")
        print("  paths are recording to data/turn_metrics/YYYY-MM-DD.jsonl.")
        print()
        return

    print(_fmt_metrics(tm.rollup(recs)))

    if args.by_path:
        by: dict[str, list[dict]] = {}
        for r in recs:
            by.setdefault(str(r.get("path", "?")), []).append(r)
        for path, rs in sorted(by.items()):
            print(f"\n  path = {path}  ({len(rs)} turns)")
            print(_fmt_metrics(tm.rollup(rs)))
    print()


if __name__ == "__main__":
    main()
