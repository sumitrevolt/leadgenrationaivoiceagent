#!/usr/bin/env python3
"""
Self-Improve Loop Audit Tool

Inspect the health, decisions, cost, and lessons of the automation self-improvement loop.

Usage:
  python scripts/selfimprove_audit.py --last-run
  python scripts/selfimprove_audit.py --skill-stats
  python scripts/selfimprove_audit.py --memory-audit
  python scripts/selfimprove_audit.py --cost-report [--days 7]
  python scripts/selfimprove_audit.py --anomalies
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta
import argparse

# Path to data files
DATA_DIR = Path("data")
AUTOMATION_AUDIT_FILE = DATA_DIR / "automation_audit.jsonl"
SKILL_LIBRARY_FILE = DATA_DIR / "skill_library.jsonl"
MEMORY_FILE = DATA_DIR / "agent_memory.jsonl"
SELFIMPROVE_RUNS_DIR = DATA_DIR / "selfimprove_runs"


def load_jsonl(filepath):
    """Load a JSONL file, return list of records."""
    if not filepath.exists():
        return []
    records = []
    try:
        with open(filepath) as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
    except json.JSONDecodeError as e:
        print(f"Error parsing {filepath}: {e}")
    return records


def last_run():
    """Show the last self-improve run."""
    print("\n=== LAST SELF-IMPROVE RUN ===\n")

    # Load automation audit
    audit = load_jsonl(AUTOMATION_AUDIT_FILE)
    selfimprove_runs = [r for r in audit if r.get("category") == "selfimprove"]

    if not selfimprove_runs:
        print("No self-improve runs found in automation_audit.jsonl")
        return

    last = selfimprove_runs[-1]

    print(f"Timestamp:  {last.get('timestamp', 'N/A')}")
    print(f"Task:       {last.get('task', 'N/A')}")
    print(f"Cost:       ${last.get('cost', 0):.2f}")
    print(f"Status:     {last.get('status', 'N/A')}")
    print(f"Approval:   {last.get('approval', 'auto')}")
    print(f"Reason:     {last.get('reason', 'N/A')}")
    print(f"Outcome:    {last.get('outcome', 'N/A')}")

    # Try to find corresponding memory/lesson
    memory = load_jsonl(MEMORY_FILE)
    if memory:
        latest_memory = memory[-1]
        print(f"\nLesson:     {latest_memory.get('lesson', 'N/A')}")
        print(f"Confidence: {latest_memory.get('confidence', 0):.2f}")

    print()


def skill_stats():
    """Show success rates and cost per task."""
    print("\n=== SKILL LIBRARY STATS ===\n")

    library = load_jsonl(SKILL_LIBRARY_FILE)
    if not library:
        print("No skill library found.")
        return

    # Group by task, calculate stats
    stats = {}
    for entry in library:
        task_name = entry.get("action", "unknown")
        if task_name not in stats:
            stats[task_name] = {
                "runs": 0,
                "successes": 0,
                "total_cost": 0,
                "success_rate": 0,
            }

        stats[task_name]["runs"] += 1
        if entry.get("outcome", {}).get("success", False):
            stats[task_name]["successes"] += 1
        stats[task_name]["total_cost"] += entry.get("cost", 0)

    # Compute rates and sort by runs (descending)
    for task, data in stats.items():
        if data["runs"] > 0:
            data["success_rate"] = data["successes"] / data["runs"]

    sorted_tasks = sorted(stats.items(), key=lambda x: x[1]["runs"], reverse=True)

    print(f"{'Task':<35} {'Runs':<6} {'Success':<10} {'Cost':<12} {'Avg Cost':<10}")
    print("-" * 73)

    for task, data in sorted_tasks:
        success_pct = f"{data['success_rate']*100:.0f}% ({data['successes']}/{data['runs']})"
        cost_str = f"${data['total_cost']:.2f}"
        avg_cost = f"${data['total_cost']/data['runs']:.2f}" if data["runs"] > 0 else "$0"

        # Highlight anomalies
        marker = ""
        if data["success_rate"] < 0.6 and data["total_cost"] > 20:
            marker = " ⚠️ HIGH COST, LOW SUCCESS"
        elif data["success_rate"] > 0.8 and data["runs"] > 3:
            marker = " ✅ RELIABLE"

        print(f"{task:<35} {data['runs']:<6} {success_pct:<10} {cost_str:<12} {avg_cost:<10}{marker}")

    total_cost = sum(d["total_cost"] for d in stats.values())
    total_runs = sum(d["runs"] for d in stats.values())
    print("-" * 73)
    print(f"{'TOTAL':<35} {total_runs:<6} {'':<10} ${total_cost:.2f}")
    print()


def memory_audit():
    """Inspect memory/lessons for quality."""
    print("\n=== MEMORY AUDIT (LESSONS) ===\n")

    memory = load_jsonl(MEMORY_FILE)
    if not memory:
        print("No memory/lessons found.")
        return

    print(f"Total lessons: {len(memory)}\n")
    print(f"{'Timestamp':<25} {'Confidence':<12} {'Lesson':<70}")
    print("-" * 107)

    for entry in memory[-10:]:  # Last 10
        ts = entry.get("timestamp", "N/A")[:19]  # Truncate
        conf = entry.get("confidence", 0)
        lesson = entry.get("lesson", "N/A")[:70]

        marker = ""
        if conf < 0.5:
            marker = " ⚠️ LOW CONFIDENCE"
        elif conf > 0.85:
            marker = " ✅ HIGH CONFIDENCE"

        print(f"{ts:<25} {conf:<12.2f} {lesson:<70}{marker}")

    print("\nTo inspect a specific lesson, see data/agent_memory.jsonl")
    print()


def cost_report(days=7):
    """Show daily cost breakdown for the last N days."""
    print(f"\n=== COST REPORT (LAST {days} DAYS) ===\n")

    audit = load_jsonl(AUTOMATION_AUDIT_FILE)
    selfimprove_runs = [r for r in audit if r.get("category") == "selfimprove"]

    if not selfimprove_runs:
        print("No self-improve runs found.")
        return

    # Group by date
    daily_cost = defaultdict(lambda: {"count": 0, "total": 0, "tasks": []})

    for run in selfimprove_runs:
        try:
            ts = datetime.fromisoformat(run.get("timestamp", "").replace("Z", "+00:00"))
            date_str = ts.strftime("%Y-%m-%d")
            cost = run.get("cost", 0)
            task = run.get("task", "unknown")

            daily_cost[date_str]["count"] += 1
            daily_cost[date_str]["total"] += cost
            daily_cost[date_str]["tasks"].append((task, cost))
        except (ValueError, AttributeError):
            continue

    # Print sorted by date
    cutoff = datetime.now() - timedelta(days=days)

    print(f"{'Date':<12} {'Runs':<6} {'Total Cost':<12} {'Avg Per Run':<14}")
    print("-" * 44)

    total_all = 0
    count_all = 0

    for date_str in sorted(daily_cost.keys()):
        data = daily_cost[date_str]
        date_obj = datetime.fromisoformat(date_str)

        if date_obj < cutoff:
            continue

        avg = data["total"] / data["count"] if data["count"] > 0 else 0
        print(f"{date_str:<12} {data['count']:<6} ${data['total']:<11.2f} ${avg:<13.2f}")

        total_all += data["total"]
        count_all += data["count"]

    print("-" * 44)
    avg_all = total_all / count_all if count_all > 0 else 0
    print(f"{'TOTAL':<12} {count_all:<6} ${total_all:<11.2f} ${avg_all:<13.2f}")
    print()


def anomalies():
    """Detect anomalies in the self-improve loop."""
    print("\n=== ANOMALY DETECTION ===\n")

    audit = load_jsonl(AUTOMATION_AUDIT_FILE)
    selfimprove_runs = [r for r in audit if r.get("category") == "selfimprove"]
    library = load_jsonl(SKILL_LIBRARY_FILE)

    found_issues = False

    # 1. Check for high-cost runs
    print("1. High-cost runs (>$10):")
    high_cost = [r for r in selfimprove_runs if r.get("cost", 0) > 10]
    if high_cost:
        for run in high_cost[-5:]:
            print(f"   - {run.get('timestamp', 'N/A')}: {run.get('task', 'N/A')} = ${run.get('cost', 0):.2f}")
        found_issues = True
    else:
        print("   ✅ None found")

    # 2. Check for repeated failures
    print("\n2. Tasks with low success rates (<50%):")
    library_stats = defaultdict(lambda: {"runs": 0, "successes": 0})
    for entry in library:
        task = entry.get("action", "unknown")
        library_stats[task]["runs"] += 1
        if entry.get("outcome", {}).get("success", False):
            library_stats[task]["successes"] += 1

    low_success = {
        task: data for task, data in library_stats.items()
        if data["runs"] >= 3 and data["successes"] / data["runs"] < 0.5
    }

    if low_success:
        for task, data in low_success.items():
            rate = (data["successes"] / data["runs"] * 100)
            print(f"   - {task}: {rate:.0f}% ({data['successes']}/{data['runs']})")
        found_issues = True
    else:
        print("   ✅ None found")

    # 3. Check for unapproved tasks (if approval is enabled)
    print("\n3. Pending approvals (SELF_IMPROVE_APPROVAL=1):")
    pending = [r for r in selfimprove_runs if r.get("approval") == "pending" and r.get("status") == "waiting"]
    if pending:
        for run in pending[-5:]:
            ts = run.get("timestamp", "N/A")
            task = run.get("task", "N/A")
            print(f"   - {ts}: {task} (waiting)")
        found_issues = True
    else:
        print("   ✅ None found")

    # 4. Check for memory/lesson hallucinations
    print("\n4. Low-confidence lessons (<0.5):")
    memory = load_jsonl(MEMORY_FILE)
    low_conf = [m for m in memory if m.get("confidence", 1) < 0.5]
    if low_conf:
        for m in low_conf[-5:]:
            print(f"   - {m.get('lesson', 'N/A')[:60]}... (conf={m.get('confidence', 0):.2f})")
        found_issues = True
    else:
        print("   ✅ None found")

    if not found_issues:
        print("\n✅ No anomalies detected. Loop is healthy.\n")
    else:
        print("\n⚠️ Review findings above and consider pausing SELF_IMPROVE_LOOP if needed.\n")


def main():
    parser = argparse.ArgumentParser(
        description="Audit the self-improve loop health, cost, and decisions."
    )
    parser.add_argument("--last-run", action="store_true", help="Show the last run")
    parser.add_argument("--skill-stats", action="store_true", help="Show task success rates + cost")
    parser.add_argument("--memory-audit", action="store_true", help="Inspect lessons/reflections")
    parser.add_argument("--cost-report", action="store_true", help="Daily cost breakdown")
    parser.add_argument("--days", type=int, default=7, help="Days to include in cost report")
    parser.add_argument("--anomalies", action="store_true", help="Detect issues")

    args = parser.parse_args()

    # If no args, show last run
    if not any([args.last_run, args.skill_stats, args.memory_audit, args.cost_report, args.anomalies]):
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
