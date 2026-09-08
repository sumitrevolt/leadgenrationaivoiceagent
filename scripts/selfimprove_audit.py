#!/usr/bin/env python3
"""
Self-Improve Loop Audit Tool

Inspect the health, decisions, cost, and lessons of the automation self-improvement loop.

Reads the LIVE jsonl stores written by the loop (verified against source):
  - data/self_improve_runs.jsonl     (app/agents/self_improve.py `_RUNS`)
  - data/skill_lessons.jsonl         (app/platform/skill_library.py `_LESSONS`)
  - data/skill_uses.jsonl            (app/platform/skill_library.py `_USES`)
  - data/self_improve_approvals.jsonl(app/agents/self_improve.py approvals queue)

NOTE: the stack is 100% FREE (Mistral/Groq/Cerebras/Gemini chain). `cost` here is a
NOTIONAL estimate recorded by the loop's CostTracker, not a real bill.

Usage:
  python scripts/selfimprove_audit.py --last-run
  python scripts/selfimprove_audit.py --skill-stats
  python scripts/selfimprove_audit.py --memory-audit
  python scripts/selfimprove_audit.py --cost-report [--days 7]
  python scripts/selfimprove_audit.py --anomalies
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

# Windows consoles default to cp1252 and choke on the ✅/⚠️ markers when piped.
# Force UTF-8 so the tool prints cleanly on Windows + Linux alike.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Path to LIVE data files (match what the loop actually writes)
DATA_DIR = Path("data")
RUNS_FILE = DATA_DIR / "self_improve_runs.jsonl"  # loop run log
LESSONS_FILE = DATA_DIR / "skill_lessons.jsonl"  # auto-learned lessons
SKILL_USES_FILE = DATA_DIR / "skill_uses.jsonl"  # per-skill use/ok log
APPROVALS_FILE = DATA_DIR / "self_improve_approvals.jsonl"  # approval queue


def load_jsonl(filepath):
    """Load a JSONL file, return list of records. Never raises."""
    if not filepath.exists():
        return []
    records = []
    try:
        with open(filepath, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # skip a single bad line, keep going
    except OSError as e:
        print(f"Error reading {filepath}: {e}")
    return records


# --- field accessors (real run-record shape: id/task/action/source/ok/detail/ms/cost/outcome_value/at) ---
def _ts(rec):
    return str(rec.get("at") or rec.get("timestamp") or "N/A")


def _label(rec):
    return rec.get("action") or rec.get("task") or "unknown"


def _ok(rec):
    if "ok" in rec:
        return bool(rec.get("ok"))
    return bool(rec.get("outcome", {}).get("success", False))  # legacy shape


def _cost(rec):
    try:
        return float(rec.get("cost", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def last_run():
    """Show the last self-improve run."""
    print("\n=== LAST SELF-IMPROVE RUN ===\n")

    runs = load_jsonl(RUNS_FILE)
    if not runs:
        print(f"No self-improve runs found in {RUNS_FILE}.")
        print("(Loop may not have run yet, or SELF_IMPROVE_LOOP is off.)")
        return

    last = runs[-1]
    print(f"Timestamp:    {_ts(last)}")
    print(f"Action/Task:  {_label(last)}")
    print(f"Status:       {'ok' if _ok(last) else 'FAIL'}")
    print(f"Cost (est):   ${_cost(last):.2f}")
    print(f"Latency:      {last.get('ms', 'N/A')} ms")
    print(f"Outcome val:  {last.get('outcome_value', 'N/A')}")
    print(f"Source:       {last.get('source', 'auto')}")
    if last.get("regression"):
        print(f"⚠️ REGRESSION: eval_gate baseline={last.get('baseline', 'N/A')}")
    if last.get("detail"):
        print(f"Detail:       {str(last.get('detail'))[:160]}")

    lessons = load_jsonl(LESSONS_FILE)
    if lessons:
        lg = lessons[-1]
        print(
            f"\nLatest lesson [{lg.get('topic', '?')}] ({lg.get('source', '?')}/{lg.get('agent', '?')}):"
        )
        print(f"  {str(lg.get('lesson', 'N/A'))[:200]}")
    print()


def skill_stats():
    """Success rate + notional cost per self-improve action, plus top skills."""
    print("\n=== SELF-IMPROVE ACTION STATS ===\n")

    runs = load_jsonl(RUNS_FILE)
    if not runs:
        print(f"No runs in {RUNS_FILE}.")
    else:
        stats = {}
        for r in runs:
            name = _label(r)
            d = stats.setdefault(name, {"runs": 0, "successes": 0, "total_cost": 0.0})
            d["runs"] += 1
            if _ok(r):
                d["successes"] += 1
            d["total_cost"] += _cost(r)

        sorted_tasks = sorted(stats.items(), key=lambda x: x[1]["runs"], reverse=True)
        print(f"{'Action':<32} {'Runs':<6} {'Success':<14} {'Cost~':<10} {'Avg~':<8}")
        print("-" * 72)
        for task, d in sorted_tasks:
            rate = d["successes"] / d["runs"] if d["runs"] else 0
            success = f"{rate * 100:.0f}% ({d['successes']}/{d['runs']})"
            avg = d["total_cost"] / d["runs"] if d["runs"] else 0
            marker = ""
            if rate < 0.6 and d["runs"] >= 3:
                marker = " ⚠️ LOW SUCCESS"
            elif rate > 0.8 and d["runs"] > 3:
                marker = " ✅ RELIABLE"
            print(
                f"{task:<32} {d['runs']:<6} {success:<14} ${d['total_cost']:<9.2f} ${avg:<7.2f}{marker}"
            )
        total_cost = sum(d["total_cost"] for d in stats.values())
        total_runs = sum(d["runs"] for d in stats.values())
        print("-" * 72)
        print(f"{'TOTAL':<32} {total_runs:<6} {'':<14} ${total_cost:.2f}  (notional)")

    # Bonus: top skills by Laplace-smoothed ok-rate (skill_uses.jsonl)
    uses = load_jsonl(SKILL_USES_FILE)
    if uses:
        agg = {}
        for r in uses:
            s = r.get("skill") or "unknown"
            d = agg.setdefault(s, {"uses": 0, "ok": 0})
            d["uses"] += 1
            if r.get("ok"):
                d["ok"] += 1
        ranked = sorted(
            agg.items(), key=lambda x: (x[1]["ok"] + 1) / (x[1]["uses"] + 2), reverse=True
        )
        print("\nTop skills (skill_uses.jsonl, Laplace ok-rate):")
        for s, d in ranked[:8]:
            rate = (d["ok"] + 1) / (d["uses"] + 2)
            print(f"  {s[:46]:<46} {rate * 100:4.0f}%  ({d['ok']}/{d['uses']})")
    print()


def memory_audit():
    """Inspect auto-learned lessons (skill_lessons.jsonl)."""
    print("\n=== LESSONS AUDIT ===\n")

    lessons = load_jsonl(LESSONS_FILE)
    if not lessons:
        print(f"No lessons in {LESSONS_FILE}.")
        return

    print(f"Total lessons: {len(lessons)}\n")
    print(f"{'When':<22} {'Topic':<18} {'Lesson':<60}")
    print("-" * 100)
    for e in lessons[-12:]:  # last 12
        when = _ts(e)[:19]
        topic = str(e.get("topic", "?"))[:18]
        lesson = str(e.get("lesson", "N/A"))[:60]
        marker = " ⚠️ thin" if len(str(e.get("lesson", "")).strip()) < 15 else ""
        print(f"{when:<22} {topic:<18} {lesson:<60}{marker}")
    print(f"\nFull lessons: {LESSONS_FILE}")
    print()


def cost_report(days=7):
    """Daily notional-cost breakdown for the last N days."""
    print(f"\n=== COST REPORT (LAST {days} DAYS, notional) ===\n")

    runs = load_jsonl(RUNS_FILE)
    if not runs:
        print(f"No runs in {RUNS_FILE}.")
        return

    daily = defaultdict(lambda: {"count": 0, "total": 0.0})
    for r in runs:
        raw = _ts(r)
        try:
            ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        key = ts.strftime("%Y-%m-%d")
        daily[key]["count"] += 1
        daily[key]["total"] += _cost(r)

    if not daily:
        print("No timestamped runs to report.")
        return

    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    print(f"{'Date':<12} {'Runs':<6} {'Cost~':<12} {'Avg/run~':<12}")
    print("-" * 44)
    total_all, count_all = 0.0, 0
    for date_str in sorted(daily.keys()):
        if date_str < cutoff:
            continue
        d = daily[date_str]
        avg = d["total"] / d["count"] if d["count"] else 0
        print(f"{date_str:<12} {d['count']:<6} ${d['total']:<11.2f} ${avg:<11.2f}")
        total_all += d["total"]
        count_all += d["count"]
    print("-" * 44)
    avg_all = total_all / count_all if count_all else 0
    print(f"{'TOTAL':<12} {count_all:<6} ${total_all:<11.2f} ${avg_all:<11.2f}")
    print()


def anomalies():
    """Detect anomalies in the self-improve loop."""
    print("\n=== ANOMALY DETECTION ===\n")
    runs = load_jsonl(RUNS_FILE)
    found = False

    # 1. High notional-cost runs
    print("1. High notional-cost runs (>$10 est):")
    high = [r for r in runs if _cost(r) > 10]
    if high:
        for r in high[-5:]:
            print(f"   - {_ts(r)}: {_label(r)} = ${_cost(r):.2f}")
        found = True
    else:
        print("   ✅ None")

    # 2. Low success-rate actions
    print("\n2. Actions with low success (<50%, >=3 runs):")
    agg = defaultdict(lambda: {"runs": 0, "ok": 0})
    for r in runs:
        a = agg[_label(r)]
        a["runs"] += 1
        if _ok(r):
            a["ok"] += 1
    low = {k: v for k, v in agg.items() if v["runs"] >= 3 and v["ok"] / v["runs"] < 0.5}
    if low:
        for task, v in low.items():
            print(f"   - {task}: {v['ok'] / v['runs'] * 100:.0f}% ({v['ok']}/{v['runs']})")
        found = True
    else:
        print("   ✅ None")

    # 3. Pending approvals (SELF_IMPROVE_APPROVAL=1)
    print("\n3. Pending approvals:")
    approvals = load_jsonl(APPROVALS_FILE)
    pending = [a for a in approvals if str(a.get("status", "")).lower() in ("pending", "waiting")]
    if pending:
        for a in pending[-5:]:
            print(
                f"   - {_ts(a)}: {a.get('task') or a.get('action') or a.get('id', '?')} (waiting)"
            )
        found = True
    else:
        print("   ✅ None")

    # 4. eval_gate regressions (replaces the dead 'confidence' check — lessons have no confidence)
    print("\n4. eval_gate regressions (action shipped below baseline):")
    regr = [r for r in runs if r.get("regression")]
    if regr:
        for r in regr[-5:]:
            print(f"   - {_ts(r)}: {_label(r)} (baseline={r.get('baseline', 'N/A')})")
        found = True
    else:
        print("   ✅ None")

    if not found:
        print("\n✅ No anomalies detected. Loop looks healthy.\n")
    else:
        print("\n⚠️ Review above; consider pausing SELF_IMPROVE_LOOP if cost/failures spike.\n")


def main():
    parser = argparse.ArgumentParser(
        description="Audit the self-improve loop health, cost, and decisions."
    )
    parser.add_argument("--last-run", action="store_true", help="Show the last run")
    parser.add_argument(
        "--skill-stats", action="store_true", help="Action success rates + cost + top skills"
    )
    parser.add_argument("--memory-audit", action="store_true", help="Inspect auto-learned lessons")
    parser.add_argument("--cost-report", action="store_true", help="Daily notional-cost breakdown")
    parser.add_argument("--days", type=int, default=7, help="Days to include in cost report")
    parser.add_argument("--anomalies", action="store_true", help="Detect issues")
    args = parser.parse_args()

    if not any(
        [args.last_run, args.skill_stats, args.memory_audit, args.cost_report, args.anomalies]
    ):
        args.last_run = True

    if args.last_run:
        last_run()
    if args.skill_stats:
        skill_stats()
    if args.memory_audit:
        memory_audit()
    if args.cost_report:
        cost_report(days=args.days)
    if args.anomalies:
        anomalies()


if __name__ == "__main__":
    main()
