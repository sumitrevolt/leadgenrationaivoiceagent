#!/usr/bin/env python3
"""Authoritative merge-gate probe: which required status checks block main."""
import json
import subprocess


def gh(*args: str) -> str:
    return subprocess.check_output(["gh", *args], text=True, encoding="utf-8", errors="replace")


repo = "sumitrevolt/leadgenrationaivoiceagent"

# 1) classic branch protection on main
try:
    prot = json.loads(gh("api", f"repos/{repo}/branches/main/protection"))
    rsc = prot.get("required_status_checks") or {}
    print("=== classic branch protection on main ===")
    print(f"  contexts_required={rsc.get('contexts')}")
    print(f"  strict={rsc.get('strict')}, checked={rsc.get('checks')}")
    print(f"  admin_enforcement={prot.get('admin_enforced_by')} "
          f"pr_req_rule={prot.get('required_pull_request_reviews', {}).get('required_number_of_approvals')}")
except Exception as e:
    print(f"=== classic protection probe: {e} ===")

# 2) rulesets
try:
    rs = json.loads(gh("api", f"repos/{repo}/rulesets?enforce=active"))
    print("\n=== active rulesets ===")
    for r in rs:
        print(f"  {r['id']} {r['name']} enforcement={r['enforcement']} target=branch main")
        rsc2 = r.get("rules", [])
        for rule in rsc2:
            if rule.get("type") == "required_status_checks":
                print(f"    required_status_checks: {json.dumps(rule.get('parameters', {}))[:400]}")
except Exception as e:
    print(f"=== rulesets probe: {e} ===")

# 3) current failing check names on our PR (to match against required contexts)
try:
    checks = gh("api", f"repos/{repo}/actions/runs/35627116162/jobs")
    jobs = json.loads(checks)["jobs"]
    print("\n=== job names + conclusion (ci.yml run) ===")
    for j in jobs:
        print(f"  [{(j.get('conclusion') or j.get('status')):10}] {j['name']}")
except Exception as e:
    print(f"=== jobs probe: {e} ===")
