#!/usr/bin/env python
"""
Coordinator Audit CLI — inspect and validate coordinator runs.

Usage:
    python scripts/coordinator_audit.py --last-run
    python scripts/coordinator_audit.py --runs 5
    python scripts/coordinator_audit.py --mode-stats
    python scripts/coordinator_audit.py --cost-report
    python scripts/coordinator_audit.py --validate-chain <run_id>
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUNS_FILE = "data/coordination_runs.jsonl"


def load_runs() -> list[dict]:
    """Load all coordination runs from jsonl."""
    runs = []
    if not os.path.exists(RUNS_FILE):
        return runs
    try:
        with open(RUNS_FILE, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        runs.append(json.loads(line))
                    except Exception:
                        pass
    except Exception as e:
        print(f"Error loading runs: {e}", file=sys.stderr)
    return runs


def cmd_last_run():
    """Show last coordinator run."""
    runs = load_runs()
    if not runs:
        print("No coordinator runs found.")
        return

    run = runs[-1]
    print("\nLAST COORDINATOR RUN\n")
    print(f"  Run ID:     {run.get('run_id', 'N/A')}")
    print(f"  Goal:       {run.get('goal', 'N/A')}")
    print(f"  Mode:       {run.get('mode', run.get('pattern', 'sequential'))}")
    print(f"  Execute:    {run.get('execute', False)}")
    print(f"  Time:       {run.get('at', 'N/A')}")

    # Count agents/steps
    results = run.get("results", [])
    print(f"  Steps:      {len(results)}")

    # Show agent breakdown
    agents = defaultdict(int)
    for res in results:
        ag = res.get("agent", "unknown")
        agents[ag] += 1
    if agents:
        print(f"  Agents:     {', '.join(f'{k}({v})' for k, v in sorted(agents.items()))}")

    # Show quality for advanced mode
    if "final_score" in run:
        print(f"  Quality:    {run['final_score']:.2f}")
        print(f"  Iterations: {len(run.get('iterations', []))}")

    # Show summary
    summary = run.get("summary", "")
    if summary:
        print(f"\n  Summary:\n    {summary[:200]}...")

    print()


def cmd_runs(limit: int = 5):
    """Show last N runs (summary)."""
    runs = load_runs()
    if not runs:
        print("No coordinator runs found.")
        return

    runs = runs[-limit:]
    print(f"\nLAST {len(runs)} COORDINATOR RUNS\n")
    print(f"{'Run ID':<12} {'Mode':<12} {'Goal':<40} {'Quality':<8} {'Time':<20}")
    print("-" * 92)

    for run in runs:
        run_id = run.get("run_id", "?")[:10]
        mode = run.get("mode", run.get("pattern", "seq"))[:10]
        goal = run.get("goal", "?")[:38]
        quality = f"{run.get('final_score', 0):.2f}" if "final_score" in run else "-"
        at = run.get("at", "?")[-19:]

        print(f"{run_id:<12} {mode:<12} {goal:<40} {quality:<8} {at:<20}")

    print()


def cmd_mode_stats():
    """Show success rate by mode."""
    runs = load_runs()
    if not runs:
        print("No coordinator runs found.")
        return

    stats = defaultdict(lambda: {"count": 0, "ok": 0, "avg_score": []})

    for run in runs:
        mode = run.get("mode", run.get("pattern", "sequential"))
        ok = run.get("ok", False)

        stats[mode]["count"] += 1
        if ok:
            stats[mode]["ok"] += 1

        if "final_score" in run:
            stats[mode]["avg_score"].append(run["final_score"])

    print("\nCOORDINATOR MODE STATISTICS\n")
    print(f"{'Mode':<15} {'Runs':<8} {'OK':<8} {'Avg Quality':<15}")
    print("-" * 46)

    for mode in sorted(stats.keys()):
        st = stats[mode]
        ok_rate = f"{100 * st['ok'] / st['count']:.0f}%" if st["count"] else "-"
        avg_q = f"{sum(st['avg_score']) / len(st['avg_score']):.2f}" if st["avg_score"] else "-"

        print(f"{mode:<15} {st['count']:<8} {ok_rate:<8} {avg_q:<15}")

    print()


def cmd_cost_report():
    """Estimate cost of all runs (LLM calls proxy)."""
    runs = load_runs()
    if not runs:
        print("No coordinator runs found.")
        return

    # Cost estimation based on mode
    costs = {
        "sequential": 1.5,
        "parallel": 1.5,
        "hierarchical": 2.5,
        "reflexion": 3.0,
    }

    total_cost = 0.0
    by_mode = defaultdict(float)

    for run in runs:
        mode = run.get("mode", run.get("pattern", "sequential"))
        base_cost = costs.get(mode, 1.5)

        # Add cost for iterations in advanced mode
        iterations = len(run.get("iterations", []))
        if iterations > 1:
            base_cost *= iterations

        total_cost += base_cost
        by_mode[mode] += base_cost

    print("\nCOORDINATOR COST REPORT (LLM proxy, USD)\n")
    print(f"{'Mode':<15} {'Cost':<10} {'Runs':<8}")
    print("-" * 33)

    for mode in sorted(by_mode.keys()):
        cost = by_mode[mode]
        count = sum(1 for r in runs if r.get("mode", r.get("pattern")) == mode)
        print(f"{mode:<15} ${cost:.2f}     {count:<8}")

    print("-" * 33)
    print(f"{'TOTAL':<15} ${total_cost:.2f}\n")


def cmd_validate_chain(run_id: str):
    """Validate agent chain in a specific run (step N output → step N+1 input)."""
    runs = load_runs()
    matching = [r for r in runs if r.get("run_id", "").startswith(run_id)]

    if not matching:
        print(f"Run {run_id} not found.")
        return

    run = matching[0]
    results = run.get("results", [])

    print(f"\nVALIDATING RUN {run.get('run_id', 'N/A')}\n")
    print(f"Goal: {run.get('goal', 'N/A')}\n")

    if not results:
        print("No results to validate.")
        return

    # Check each step
    for i, res in enumerate(results):
        agent = res.get("agent", "?")
        task = res.get("task", "?")[:50]
        mode = res.get("mode", "?")

        print(f"Step {i}: {agent} ({mode})")
        print(f"  Task: {task}")

        output = res.get("output", "")
        if output:
            if isinstance(output, dict):
                print(f"  Output keys: {list(output.keys())}")
            elif isinstance(output, str):
                print(f"  Output (first 80 chars): {output[:80]}...")
            else:
                print(f"  Output type: {type(output).__name__}")

        # Check context flow to next step
        if i < len(results) - 1:
            next_agent = results[i + 1].get("agent", "?")
            # Simple heuristic: if output has content, next step should have seen it
            if output:
                print(f"  ✓ Output available to {next_agent}")
            else:
                print(f"  ⚠ No output (may affect {next_agent})")

        print()

    # Check final summary
    summary = run.get("summary", "")
    if summary:
        print(f"Final Summary:\n  {summary[:150]}...\n")
    else:
        print("⚠ No final summary generated.\n")


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "--last-run":
        cmd_last_run()
    elif cmd == "--runs":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        cmd_runs(limit)
    elif cmd == "--mode-stats":
        cmd_mode_stats()
    elif cmd == "--cost-report":
        cmd_cost_report()
    elif cmd == "--validate-chain":
        run_id = sys.argv[2] if len(sys.argv) > 2 else ""
        if not run_id:
            print("Usage: --validate-chain <run_id>")
            sys.exit(1)
        cmd_validate_chain(run_id)
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
