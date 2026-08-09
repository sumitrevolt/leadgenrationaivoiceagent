#!/usr/bin/env python3
"""Automation wiring audit — every declared flag actually read, every staff job dispatchable.

Catches "declared-but-not-connected" automation gaps:
  1. AUTOMATION_FLAGS (growth.py) entries that are NEVER read anywhere in app/
     (registry entry but no os.environ/getenv/settings usage = dead switch).
  2. STAFF_JOBS (staff_jobs.py) that team_scheduler._run_job_inner can't dispatch.
  3. Celery beat staff-* tasks referencing a job not in STAFF_JOBS.
Exit 0 = all automation wired, 1 = gaps.
"""

from __future__ import annotations

import pathlib
import re
import sys
from collections import Counter
from collections.abc import Iterable

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PROBLEMS: list[str] = []

# Registry-only / value-carrying env names that are read indirectly (URL-valued
# "set = ON", or consumed by config/middleware/compose, not a plain getenv gate).
# These are intentionally not simple boolean gates — exclude from "dead" check.
KNOWN_INDIRECT = {
    "OLLAMA_URL",
    "OLLAMA_PRIMARY",
    "SEARXNG_URL",
    "NTFY_URL",
    "NTFY_TOPIC",
    "CLOUDFLARE_TUNNEL_TOKEN",
    "TURNSTILE_SITE_KEY",
    "TURNSTILE_SECRET_KEY",
    "LITELLM_MASTER_KEY",
    "LITELLM_GATEWAY_URL",
    "DR_REPLICA_URL",
    "DR_LAG_WARN_S",
    "DR_LAG_FAIL_S",
    "MEM0_BACKEND",
    "AGENT_MEMORY_MIN_SIM",
    "AGENT_MEMORY_RECALL_LIMIT",
    "TOTP_CHALLENGE_KEY",
    "WHATSAPP_LEAD_FLOW_ID",
    "RUN_IN_PROCESS_SCHEDULER",
    "OPS_ALERT_ENGINEER_THRESHOLD",
    "OPS_ALERT_EVAL_REJECT_BURST",
    "OPS_ALERT_EVAL_REJECT_WINDOW",
    "OPS_ALERT_WEBHOOK_DEAD_LETTER_THRESHOLD",
    "UPI_PENDING_ALERT_HOURS",
    "CUSTOMER_WEBHOOK_DENY_PRIVATE",
    "DLT_",
    "EVAL_GATE_HARD",
    # Read DYNAMICALLY via f-string os.getenv(f"MEMORY_STACK_LAYER_{layer.upper()}")
    # in app/platform/memory_stack.py:106 — literal names never appear in source.
    "MEMORY_STACK_LAYER_WORKING",
    "MEMORY_STACK_LAYER_PROSPECTIVE",
    "MEMORY_STACK_LAYER_EPISODIC",
    "MEMORY_STACK_LAYER_SEMANTIC",
    "MEMORY_STACK_LAYER_PROCEDURAL",
    "MEMORY_STACK_LAYER_SHARED",
}

# Intentionally-reserved future flags (declared now, engine ships later). Documented
# with a "# Phase-N future" comment in the registry — not a wiring bug.
RESERVED_FUTURE = {
    "HERMES_HANDOFF",  # Phase-2: code_upgrader -> Hostinger Hermes draft-PR executor
    "CONSENT_CONFIRM",  # TRAI verbal/DTMF consent-confirm gate — ships at DLT unlock (docs/TRAI_CONSENT_CONFIRM_SPEC.md)
}


def _all_app_text() -> str:
    chunks = []
    for p in (ROOT / "app").rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        try:
            chunks.append(p.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            pass
    return "\n".join(chunks)


def _reference_counts(blob: str, flags: Iterable[str]) -> Counter[str]:
    """Count exact env symbols in one source scan.

    The old implementation ran one full-blob ``re.findall`` per flag. With a
    ~12 MB app corpus and 350+ flags that multiplied into gigabytes of repeated
    scanning on every prod check. A single alternation preserves the exact
    word-boundary semantics while making the cost proportional to corpus size.
    """
    names = sorted({str(flag) for flag in flags if flag}, key=len, reverse=True)
    if not names:
        return Counter()
    pattern = re.compile(r"\b(?:" + "|".join(re.escape(name) for name in names) + r")\b")
    return Counter(pattern.findall(blob))


def audit_flags(blob: str) -> None:
    from app.api.growth import AUTOMATION_FLAGS

    dead = []
    reserved = 0
    references = _reference_counts(blob, AUTOMATION_FLAGS)
    for flag in AUTOMATION_FLAGS:
        if flag in KNOWN_INDIRECT:
            continue
        if flag in RESERVED_FUTURE:
            reserved += 1
            continue
        # Count references OUTSIDE the registry literal (registry has it once per line).
        refs = references.get(flag, 0)
        # registry line itself counts as 1; need >=2 to prove a real read.
        if refs < 2:
            dead.append(flag)
    print(
        f"[flags] {len(AUTOMATION_FLAGS)} declared, {reserved} reserved-future, {len(dead)} never read"
    )
    for f in dead:
        PROBLEMS.append(f"DEAD FLAG: {f} declared in AUTOMATION_FLAGS but never read in app/")


def audit_jobs(blob: str) -> None:
    from app.tasks.staff_jobs import STAFF_JOBS

    # team_scheduler dispatch source
    sched = (ROOT / "app/platform/team_scheduler.py").read_text(encoding="utf-8", errors="ignore")
    missing = [j for j in STAFF_JOBS if f'"{j}"' not in sched and f"'{j}'" not in sched]
    print(f"[jobs] {len(STAFF_JOBS)} staff jobs, {len(missing)} not dispatchable")
    for j in missing:
        PROBLEMS.append(f"ORPHAN JOB: '{j}' in STAFF_JOBS but not dispatched by team_scheduler")


def audit_beat() -> None:
    from app.tasks.staff_jobs import STAFF_JOBS

    worker = (ROOT / "app/worker.py").read_text(encoding="utf-8", errors="ignore")
    # Full beat task names "staff-<middle>-<freq>"; job names use underscores,
    # beat names use hyphens (staff-email-outreach-daily -> job email_outreach).
    names = re.findall(r'"(staff-[a-z0-9-]+)"', worker)
    NON_JOB = {"selfimprove", "self-improve", "revive", "heartbeat", "growth", "watchdog-revive"}
    unknown = []
    for name in names:
        mid = name[len("staff-") :].replace("-", "_")  # e.g. reply_triage_hourly
        if any(mid.startswith(j) for j in STAFF_JOBS):
            continue
        if any(mid.startswith(n.replace("-", "_")) for n in NON_JOB):
            continue
        unknown.append(name)
    print(f"[beat] {len(names)} staff beat-tasks, {len(unknown)} unrecognized")
    for b in sorted(set(unknown)):
        PROBLEMS.append(f"BEAT REF: '{b}' beat task maps to no STAFF_JOB (review)")


def main() -> int:
    print("=== AUTOMATION WIRING AUDIT ===")
    blob = _all_app_text()
    audit_flags(blob)
    audit_jobs(blob)
    audit_beat()
    print("-" * 48)
    if PROBLEMS:
        print(f"[FAIL] {len(PROBLEMS)} automation gap(s):")
        for p in PROBLEMS:
            print("  -", p)
        return 1
    print("[OK] all automation flags wired + jobs dispatchable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
