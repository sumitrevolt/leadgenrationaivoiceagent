#!/usr/bin/env python3
"""Confirm which CI lanes are currently GREEN on PR #543 head 6bb557b3,
so the branch-protection re-point targets real passing lanes."""
import json
import subprocess


def gh(*args: str) -> str:
    return subprocess.check_output(
        ["gh", "api", "repos/sumitrevolt/leadgenrationaivoiceagent/" + args[0]],
        text=True, encoding="utf-8", errors="replace",
    )


pr = json.loads(gh("pulls/543"))
head = pr["head"]["sha"]
print(f"PR #543 head = {head[:12]}  state={pr['state']} mergeable={pr.get('mergeable')} "
      f"merge_state={pr.get('mergeable_state')}")

cr = json.loads(gh(f"commits/{head}/check-runs?per_page=100")).get("check_runs", [])
print("\n=== check-run conclusions on head ===")
for c in sorted(cr, key=lambda x: str(x.get("conclusion") or x.get("status"))):
    print(f"  [{(c.get('conclusion') or c.get('status') or '?'):9}] {c['name']}")

# The re-point target lanes
targets = ["Lint + syntax + secrets", "harness real-redis integration"]
print("\n=== re-point target lanes status ===")
for t in targets:
    hit = [c.get("conclusion") or c.get("status") for c in cr if c["name"] == t]
    print(f"  {t}: {hit if hit else 'NOT REPORTED'}")
