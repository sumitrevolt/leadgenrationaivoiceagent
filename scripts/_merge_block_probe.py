#!/usr/bin/env python3
"""DEFINITIVE merge-block probe for PR #543.

Answers, from the authoritative APIs (not memory):
  1. Is the PR actually merge-blocked, and by WHICH required check context?
  2. What is the conclusion of EVERY required context (pytest/ruff/secret-scanning)
     on the head commit?
  3. Is 'prod_check runtime gates' a REQUIRED context or just an advisory failing lane?
"""
import json
import subprocess


def gh(*args: str) -> str:
    return subprocess.check_output(
        ["gh", "api", "repos/sumitrevolt/leadgenrationaivoiceagent/" + args[0]],
        text=True, encoding="utf-8", errors="replace",
    )


repo = "sumitrevolt/leadgenrationaivoiceagent"
head = json.loads(gh("pulls/543"))["head"]["sha"]
required = {"pytest", "ruff", "secret-scanning"}

print(f"=== PR #543 head = {head[:12]} ===\n")

# (a) classic protection — the required contexts it enforces
prot = json.loads(gh("branches/main/protection"))
rsc = prot.get("required_status_checks") or {}
print(f"REQUIRED (classic protection): {rsc.get('contexts')}  strict={rsc.get('strict')}")
print(f"  enforcement flag on classic protection: admin_enforcement={prot.get('admin_enforced_by')}")

# (b) every check-run on the head commit + its conclusion
runs = json.loads(gh(f"commits/{head}/check-runs?per_page=100")).get("check_runs", [])
print(f"\nCONCLUSION OF EACH CHECK RUN ON HEAD ({len(runs)} total):")
required_status = {}
for c in runs:
    name = c["name"]
    concl = c.get("conclusion") or c.get("status")
    mark = "  <== REQUIRED" if name in required else ""
    print(f"  [{concl:10}] {name}{mark}")
    if name in required:
        required_status[name] = concl

print("\nREQUIRED-CONTEXT SUMMARY (what branch protection actually evaluates):")
for rq in ("pytest", "ruff", "secret-scanning"):
    st = required_status.get(rq, "NOT-REPORTED (no check-run with this exact name)")
    print(f"  {rq:18} -> {st}")

# (c) is 'prod_check runtime gates' required?
print("\nIs 'prod_check runtime gates' a REQUIRED context?  ",
      "YES" if "prod_check runtime gates" in required else "NO (advisory lane — does not block merge by itself)")
