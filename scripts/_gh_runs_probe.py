#!/usr/bin/env python3
"""List the latest GitHub Actions runs + check-status of our PR head."""
import json
import subprocess


def gh(*args: str) -> str:
    return subprocess.check_output(["gh", *args], text=True, encoding="utf-8", errors="replace")


repo = "sumitrevolt/leadgenrationaivoiceagent"
head = "f0871cc3"

# Latest runs
runs = json.loads(gh("api", f"repos/{repo}/actions/runs?per_page=6"))
print("=== recent action runs ===")
for r in runs["workflow_runs"]:
    print(f"  {r['id']}  sha={r['head_sha'][:8]}  branch={r.get('head_ref') or r.get('head_branch')}  "
          f"{r['status']} {r.get('conclusion') or 'running'}  created={r['created_at']}")

# Which run corresponds to our PR head commit?
match = [r for r in runs["workflow_runs"] if r["head_sha"].startswith(head)]
print(f"\n=== run on our head {head}: {'FOUND' if match else 'NOT YET TRIGGERED'} ===")
if match:
    for r in match:
        checks = json.loads(gh("api", f"repos/{repo}/actions/runs/{r['id']}/check-runs"))
        print(f"run {r['id']} status={r['status']} conclusion={r.get('conclusion')}")
        for c in checks.get("check_runs", []):
            print(f"  [{c.get('conclusion') or c.get('status'):10}] {c['name']}")
