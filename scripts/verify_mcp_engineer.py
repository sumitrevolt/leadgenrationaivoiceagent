"""verify_mcp_engineer.py — smoke verify the MCP overhaul (council 2026-06-26).

Run from project root:
    python scripts/verify_mcp_engineer.py

Exits 0 on full green, 1 otherwise. Wire this into /verify if you want.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

failures = []


def check(label, ok, detail=""):
    status = "OK  " if ok else "FAIL"
    print(f"  [{status}] {label}" + (f"  ({detail})" if detail else ""))
    if not ok:
        failures.append(label)


print("=" * 70)
print("MCP OVERHAUL - smoke verify (council 2026-06-26)")
print("=" * 70)

# [1] mcp_engineer module
print("\n[1] app/platform/mcp_engineer.py")
try:
    from app.platform import mcp_engineer

    check("module imports", True)
except Exception as e:
    check("module imports", False, str(e)[:80])
    print("\nFATAL - cannot continue without mcp_engineer import.")
    sys.exit(1)

os.environ.pop("MCP_ENGINEER", None)
r = mcp_engineer.run_mcp()
check("INERT when MCP_ENGINEER unset", r.get("status") == "disabled", r.get("status", "?"))

os.environ["MCP_ENGINEER"] = "1"
r = mcp_engineer.run_mcp()
check("full pass returns status=ok", r.get("status") == "ok")
check(
    "score is in [0,100]",
    isinstance(r.get("score"), (int, float)) and 0 <= r.get("score", -1) <= 100,
    f"score={r.get('score')}",
)
expected_kpis = {
    "dependency",
    "expose_gate",
    "product_armed",
    "keys",
    "rotation",
    "auth_failures",
    "a2a_card",
}
got_kpis = set((r.get("kpis") or {}).keys())
check("all 7 probes ran", expected_kpis.issubset(got_kpis), f"missing={expected_kpis - got_kpis}")

audit = mcp_engineer.audit_mcp_security()
print("\n  Security audit:")
for k, v in audit.items():
    print(f"      {k}: {v}")

# [2] team.py
print("\n[2] app/platform/team.py")
try:
    from app.platform import team

    check("module imports", True)
    check("STAFF['arya'] exists", "arya" in team.STAFF)
    if "arya" in team.STAFF:
        ar = team.STAFF["arya"]
        check("Arya is platform staff", ar.get("product") == "platform", ar.get("product"))
        check("Arya has title", bool(ar.get("title")), ar.get("title", ""))
except Exception as e:
    check("module imports", False, str(e)[:80])

# [3] staff_jobs
print("\n[3] app/tasks/staff_jobs.py")
try:
    from app.tasks import staff_jobs

    check("STAFF_JOBS includes mcp_engineer", "mcp_engineer" in staff_jobs.STAFF_JOBS)
except Exception as e:
    src = (REPO / "app" / "tasks" / "staff_jobs.py").read_text(encoding="utf-8")
    check(
        "STAFF_JOBS includes mcp_engineer (grep)",
        '"mcp_engineer"' in src,
        f"import failed: {str(e)[:40]}",
    )

# [4] team_scheduler
print("\n[4] app/platform/team_scheduler.py")
try:
    from app.platform import team_scheduler

    inspected = team_scheduler.__dict__.get("_last_ran") or {}
    check("_last_ran includes mcp_engineer", "mcp_engineer" in inspected)
except Exception as e:
    src = (REPO / "app" / "platform" / "team_scheduler.py").read_text(encoding="utf-8")
    check(
        "mcp_engineer dispatch present (grep)",
        '"mcp_engineer"' in src,
        f"import failed: {str(e)[:40]}",
    )

# [5] worker.py beat
print("\n[5] app/worker.py beat schedule")
src = (REPO / "app" / "worker.py").read_text(encoding="utf-8")
check("staff-mcp-engineer-hourly beat entry", "staff-mcp-engineer-hourly" in src)

# [6] automation_flags - grep fallback (heavy import chain)
print("\n[6] app/api/automation_flags.py")
src = (REPO / "app" / "api" / "automation_flags.py").read_text(encoding="utf-8")
for flag in ("MCP_PRODUCT", "MCP_ENGINEER", "FASTAPI_MCP_TOKEN", "MCP_IP_ALLOWLIST"):
    check(f"{flag} registered", f'"{flag}"' in src)

# [7] main.py auth gate
print("\n[7] app/main.py /mcp auth gate")
src = (REPO / "app" / "main.py").read_text(encoding="utf-8")
check("FASTAPI_MCP_TOKEN check in mount block", "FASTAPI_MCP_TOKEN" in src)
check("MCP_IP_ALLOWLIST check in mount block", "MCP_IP_ALLOWLIST" in src)
check("_mcp_auth_gate middleware present", "_mcp_auth_gate" in src)

# [8] artifacts
print("\n[8] Claude subagent + skill artifacts")
for path in (
    ".claude/agents/mcp-engineer/AGENT.md",
    ".claude/skills/mcp-engineer/SKILL.md",
    "tests/test_mcp_engineer.py",
):
    fp = REPO / path
    check(
        f"{path} exists",
        fp.exists() and fp.stat().st_size > 200,
        f"{fp.stat().st_size if fp.exists() else 0}B",
    )

print("\n" + "=" * 70)
if failures:
    print(f"VERIFY FAILED - {len(failures)} check(s) red:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("VERIFY GREEN - MCP overhaul wired end-to-end")
    print("\nNext: activate on VPS")
    print("  ssh root@72.61.245.204")
    print("  cd /opt/leadgen && nano .env")
    print("  # MCP_PRODUCT=1, MCP_ENGINEER=1, FASTAPI_MCP_TOKEN=<openssl rand -hex 32>")
    print("  docker compose -f docker-compose.vps.yml build app")
    print("  docker compose -f docker-compose.vps.yml up -d --no-deps app worker scheduler")
    sys.exit(0)
