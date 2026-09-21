#!/usr/bin/env python3
"""List ALL check-runs on the PR #543 head commit with conclusions, and mark
which ones are the required branch-protection contexts (pytest, ruff,
secret-scanning)."""
import json
import subprocess


def gh(*args: str) -> str:
    return subprocess.check_output(["gh", *args], text=True, encoding="utf-8", errors="replace")


repo = "sumitrevolt/leadgenrationaivoiceagent"
required = {"pytest", "ruff", "secret-scanning"}

# head commit of our PR (the f0871cc3 tip)
head = json.loads(gh("api", f"repos/{repo}/pulls/543"))["head"]["sha"]
print(f"=== PR #543 head commit: {head[:12]} ===")

# pull check-runs directly against the commit (this is what branch protection reads)
raw = gh("api", f"repos/{repo}/commits/{head}/check-runs?per_page=100")
data = json.loads(raw)
runs = data.get("check_runs", [])
print(f"total check-runs on commit: {len(runs)}\n")

# also fetch the combined status
comb = json.loads(gh("api", f"repos/{repo}/commits/{head}/status"))
print(f"combined status: state={comb['state']}  contexts:")
for s in comb.get("statuses", []):
    tag = "  <== REQUIRED" if s["context"] in required else ""
    print(f"  [{s['state']:9}] {s['context']}{tag}")
print("\n=== individual check-runs ===")
for c in sorted(runs, key=lambda x: 0 if x["name"] in required else 1):
    concl = c.get("conclusion") or c.get("status")
    tag = "  <== REQUIRED CONTEXT" if c["name"] in required else ""
    print(f"  [{concl:10}] {c['name']}{tag}")
