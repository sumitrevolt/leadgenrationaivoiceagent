#!/usr/bin/env python3
"""Poll PR #549 required contexts (post re-point: Lint+secrets, harness-redis)
and report merge-block status."""
import json
import subprocess


def gh(*args: str) -> str:
    return subprocess.check_output(
        ["gh", "api", "repos/sumitrevolt/leadgenrationaivoiceagent/" + args[0]],
        text=True, encoding="utf-8", errors="replace",
    )


pr = json.loads(gh("pulls/549"))
head = pr["head"]["sha"]
print(f"PR #549 head={head[:10]} state={pr['state']} merge_state={pr.get('mergeable_state')}")

cr = json.loads(gh(f"commits/{head}/check-runs?per_page=100")).get("check_runs", [])
print("\nRequired contexts status:")
for name in ("Lint + syntax + secrets", "harness real-redis integration"):
    hits = [c.get("conclusion") or c.get("status") for c in cr if c["name"] == name]
    print(f"  {name}: {hits if hits else 'NOT-REPORTED'}")

# all statuses summary
print("\nAll check-runs:")
for c in cr:
    print(f"  [{(c.get('conclusion') or c.get('status') or '?'):9}] {c['name']}")
