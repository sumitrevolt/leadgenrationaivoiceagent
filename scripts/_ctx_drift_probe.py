#!/usr/bin/env python3
"""DEFINITIVE: do required contexts (pytest/ruff/secret-scanning) EVER report on
recent MAIN commits? If they report there but not on our PR, it's timing. If
they never report anywhere, the classic branch protection is STALE drift that
blocks every merge."""
import json
import subprocess


def gh(*args: str) -> str:
    return subprocess.check_output(
        ["gh", "api", "repos/sumitrevolt/leadgenrationaivoiceagent/" + args[0]],
        text=True, encoding="utf-8", errors="replace",
    )


required = ["pytest", "ruff", "secret-scanning"]

# Latest 3 main-branch commits
commits = json.loads(gh("commits?per_page=3"))
for c in commits:
    sha = c["sha"]
    print(f"\n=== main commit {sha[:10]} : {c['commit']['message'].splitlines()[0][:60]} ===")
    cr = json.loads(gh(f"commits/{sha}/check-runs?per_page=100")).get("check_runs", [])
    names = [x["name"] for x in cr]
    for rq in required:
        hit = [n for n in names if n.lower() == rq]
        print(f"  required '{rq}': " + ("REPORTED (" + ", ".join(hit) + ")" if hit else "NOT reported"))
    print(f"  all check names: {names}")
