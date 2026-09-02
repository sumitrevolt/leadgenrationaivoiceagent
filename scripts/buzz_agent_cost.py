#!/usr/bin/env python3
"""buzz_agent_cost — what the Buzz coding-agent plane actually costs per day.

The Buzz video quotes $200/day. This project runs a free/subscription-only stack,
so the number that matters here is NOT dollars — it is **quota burn**. Codex
reports a real `used_percent` against the subscription; Claude Code reports
tokens. Both are read from local session logs. Nothing is estimated from
guesswork and nothing is sent anywhere unless you pass --post.

    python scripts/buzz_agent_cost.py                 # last 7 days, table
    python scripts/buzz_agent_cost.py --days 1        # today + yesterday
    python scripts/buzz_agent_cost.py --json          # machine-readable
    python scripts/buzz_agent_cost.py --post          # post to Buzz #ops

The USD column is a COUNTERFACTUAL: what these tokens would have cost on
metered API pricing. On a subscription the marginal cost is zero — the column
exists to show when a harness is burning enough to be worth re-tuning, not to
claim money was spent. Per-MTok rates are Anthropic list prices; edit PRICES if
they move.

Protocol: ~/.buzz/GUIDES/BUZZ_END_TO_END_RUNBOOK.md
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

RELAY = "https://leadsgenai.communities.buzz.xyz"
CHANNEL_IDS = Path.home() / ".buzz" / "GUIDES" / "CHANNEL_IDS.json"
IST = timezone(timedelta(hours=5, minutes=30))

CLAUDE_SESSIONS = Path.home() / ".claude" / "projects"
CODEX_SESSIONS = Path.home() / ".codex" / "sessions"

# USD per million tokens: (input, output). Cache write = 1.25x input (5m TTL),
# cache read = 0.1x input. Counterfactual only — see module docstring.
PRICES = {
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-fable-5": (10.0, 50.0),
}
CACHE_WRITE_MULT = 1.25
CACHE_READ_MULT = 0.10
UNKNOWN_MODEL_PRICE = (5.0, 25.0)  # assume Opus-tier rather than silently zero


def _day(ts: str) -> str:
    """UTC ISO timestamp -> IST calendar day. Agents run on IST business hours."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return "?"
    return dt.astimezone(IST).strftime("%Y-%m-%d")


def _cost(model: str, usage: dict) -> float:
    inp, out = PRICES.get(model, UNKNOWN_MODEL_PRICE)
    return (
        usage["input"] * inp
        + usage["cache_write"] * inp * CACHE_WRITE_MULT
        + usage["cache_read"] * inp * CACHE_READ_MULT
        + usage["output"] * out
    ) / 1_000_000


def _blank() -> dict:
    return {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0, "calls": 0}


def _add(bucket: dict, **kw) -> None:
    for k, v in kw.items():
        bucket[k] += v


def scan_claude(cutoff: str, project: str | None) -> dict:
    """Per-day, per-model token totals from Claude Code session logs.

    Deduped by message uuid — the same assistant message can appear more than
    once in a transcript after a resume, and double counting inflates the day.
    """
    days: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(_blank))
    seen: set[str] = set()
    if not CLAUDE_SESSIONS.exists():
        return days

    for path in CLAUDE_SESSIONS.glob("*/*.jsonl"):
        if project and project.lower() not in path.parent.name.lower():
            continue
        try:
            fh = path.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = rec.get("message") or {}
                usage = msg.get("usage")
                if not isinstance(usage, dict):
                    continue
                day = _day(rec.get("timestamp") or "")
                if day == "?" or day < cutoff:
                    continue
                uid = rec.get("uuid") or ""
                if uid:
                    if uid in seen:
                        continue
                    seen.add(uid)
                _add(
                    days[day][msg.get("model") or "unknown"],
                    input=usage.get("input_tokens") or 0,
                    output=usage.get("output_tokens") or 0,
                    cache_write=usage.get("cache_creation_input_tokens") or 0,
                    cache_read=usage.get("cache_read_input_tokens") or 0,
                    calls=1,
                )
    return days


def scan_codex(cutoff: str) -> tuple[dict, dict | None]:
    """Per-day token totals + the newest subscription quota reading.

    Codex emits a cumulative `total_token_usage` and a per-turn
    `last_token_usage`; summing the deltas is what gives a true per-day figure.
    """
    days: dict[str, dict] = defaultdict(_blank)
    quota: dict | None = None
    quota_at = ""
    peak = 0.0
    if not CODEX_SESSIONS.exists():
        return days, quota

    for path in CODEX_SESSIONS.rglob("*.jsonl"):
        try:
            fh = path.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"token_count"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = rec.get("payload") or {}
                if payload.get("type") != "token_count":
                    continue
                ts = rec.get("timestamp") or ""
                day = _day(ts)
                if day == "?" or day < cutoff:
                    continue
                last = ((payload.get("info") or {}).get("last_token_usage")) or {}
                cached = last.get("cached_input_tokens") or 0
                _add(
                    days[day],
                    input=max((last.get("input_tokens") or 0) - cached, 0),
                    cache_read=cached,
                    cache_write=last.get("cache_write_input_tokens") or 0,
                    output=last.get("output_tokens") or 0,
                    calls=1,
                )
                primary = (payload.get("rate_limits") or {}).get("primary")
                if primary and ts > quota_at:
                    quota, quota_at = primary, ts
                if primary is not None:
                    peak = max(peak, primary.get("used_percent") or 0.0)
    if quota is not None:
        quota = dict(quota, peak_percent=peak)
    return days, quota


def build_report(days_back: int, project: str | None) -> dict:
    cutoff = (datetime.now(IST) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    claude = scan_claude(cutoff, project)
    codex, quota = scan_codex(cutoff)

    rows = []
    for day in sorted(set(claude) | set(codex), reverse=True):
        per_model = claude.get(day, {})
        c_tokens = sum(
            u["input"] + u["output"] + u["cache_write"] + u["cache_read"]
            for u in per_model.values()
        )
        c_usd = sum(_cost(m, u) for m, u in per_model.items())
        x = codex.get(day) or _blank()
        x_tokens = x["input"] + x["output"] + x["cache_write"] + x["cache_read"]
        rows.append(
            {
                "day": day,
                "claude_tokens": c_tokens,
                "claude_calls": sum(u["calls"] for u in per_model.values()),
                "claude_usd": round(c_usd, 2),
                "claude_models": {m: u["calls"] for m, u in sorted(per_model.items())},
                "codex_tokens": x_tokens,
                "codex_calls": x["calls"],
            }
        )

    return {
        "generated_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"),
        "window_days": days_back,
        # Claude-only: Codex session logs carry no project dir to filter on.
        "project_filter_claude_only": project,
        "codex_quota_percent": (quota or {}).get("used_percent"),
        "codex_quota_peak_percent": (quota or {}).get("peak_percent"),
        "rows": rows,
        "totals": {
            "claude_tokens": sum(r["claude_tokens"] for r in rows),
            "claude_usd": round(sum(r["claude_usd"] for r in rows), 2),
            "codex_tokens": sum(r["codex_tokens"] for r in rows),
        },
    }


def _m(n: int) -> str:
    return f"{n / 1_000_000:.2f}M" if n >= 1_000_000 else f"{n / 1000:.0f}k"


def render(report: dict, usd_inr: float) -> str:
    t = report["totals"]
    quota = report["codex_quota_percent"]
    peak = report["codex_quota_peak_percent"]
    if quota is None:
        quota_txt = "n/a"
    else:
        # The latest reading alone is misleading right after a quota reset —
        # the window peak is what tells you whether you nearly ran out.
        quota_txt = f"{quota:.0f}% now, peak {peak:.0f}%"

    lines = [
        f"**[COST] {report['generated_at']}** — last {report['window_days']}d, "
        f"Codex subscription **{quota_txt}**",
        "",
        f"Claude Code **{_m(t['claude_tokens'])}** tok · Codex **{_m(t['codex_tokens'])}** tok",
        f"Counterfactual at API list price: **${t['claude_usd']:.2f}** "
        f"(≈₹{t['claude_usd'] * usd_inr:,.0f} at ₹{usd_inr:g}/$) — "
        "actual marginal cost on the subscription stack is **₹0**.",
        "",
        "`day        | claude tok | calls |     ~usd | codex tok | calls`",
    ]
    for r in report["rows"]:
        lines.append(
            f"`{r['day']} | {_m(r['claude_tokens']):>10} | {r['claude_calls']:>5} | "
            f"${r['claude_usd']:>7.2f} | {_m(r['codex_tokens']):>9} | {r['codex_calls']:>5}`"
        )
    lines += [
        "",
        "_Read-only. Source: local Claude Code + Codex session logs. "
        "USD is what these tokens WOULD cost on metered API pricing, not money spent._",
    ]
    return "\n".join(lines)


def post(body: str) -> None:
    """Best-effort post to #ops. Import kept local — buzzlock owns the helper."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from buzzlock import _owner_nsec  # noqa: PLC0415

    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise RuntimeError("no LOCALAPPDATA — cannot locate buzz.exe")
    exe = Path(local) / "Buzz" / "buzz.exe"
    if not exe.exists():
        raise RuntimeError(f"buzz.exe not found at {exe}")
    nsec = _owner_nsec()
    if not nsec:
        raise RuntimeError("owner credential not available")

    cid = json.loads(CHANNEL_IDS.read_text(encoding="utf-8-sig"))["ops"]
    env = dict(os.environ)
    env["BUZZ_PRIVATE_KEY"] = nsec
    r = subprocess.run(
        [
            str(exe),
            "--relay",
            RELAY,
            "--format",
            "json",
            "messages",
            "send",
            "--channel",
            cid,
            "--content",
            "-",
        ],
        input=body,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=120,
    )
    if r.returncode != 0:
        raise RuntimeError(f"buzz send failed rc={r.returncode}: {(r.stderr or '')[:300]}")


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="buzz_agent_cost",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--days", type=int, default=7, help="days back to scan (default 7)")
    ap.add_argument(
        "--project",
        help="filter CLAUDE sessions by project dir (Codex logs carry no project "
        "dir, so Codex totals stay machine-wide)",
    )
    ap.add_argument("--usd-inr", type=float, default=88.0, help="FX rate for the ₹ column")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of the table")
    ap.add_argument("--post", action="store_true", help="post the table to Buzz #ops")
    args = ap.parse_args()

    # Windows consoles default to cp1252 and die on ₹ / ≈ — reconfigure, don't
    # drop the characters (this table is meant to be pasted into Buzz as-is).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    if args.days < 0:
        print("--days must be >= 0", file=sys.stderr)
        return 1

    report = build_report(args.days, args.project)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    body = render(report, args.usd_inr)
    print(body)

    if args.post:
        try:
            post(body)
        except Exception as exc:
            print(f"[cost] POST FAILED: {exc}", file=sys.stderr)
            return 3
        print("[cost] posted to #ops")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
