#!/usr/bin/env python3
"""One bounded TypeSafe System One judgment: should we proceed with the full
gate-fix chain (allowlist + branch-protection + merge + deploy)?

Records a traceable decision (decision_id, task_id, tenant_scope, purpose,
state_hash, evidence_refs, model, answers, latency, observed_at) under
data/typesafe/trace_<epoch>.json.

Compliance gates stay authoritative: this judgment is decision-support, NOT
a bypass. §5 + R8.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.platform import typesafe_integration as ts


def main() -> int:
    started = time.time()
    state = {
        "pr": {
            "number": 543,
            "head_sha": "6bb557b3",
            "mergeable": True,
            "merge_state": "BLOCKED",
            "blocking_contexts": ["pytest", "ruff", "secret-scanning"],
            "note": "Required context names never reported on recent main commits — "
                    "pre-existing branch-protection config drift. CI actually reports "
                    "'Lint + syntax + secrets', 'prod_check + pytest', 'harness real-redis "
                    "integration'. xdist param-id flake already fixed in 6bb557b3.",
        },
        "failing_lanes": [
            {"name": "Pytest Tests", "root_cause": "xdist param-id flake", "in_scope": "fixed in 6bb557b3"},
            {"name": "prod_check runtime gates", "root_cause": "allowlist drift "
                     "(ops.telegram_group_ids stale entries + new script not declared)",
             "in_scope": "will add allowlist entries + manifest for telethon_make_forum_groups.py"},
            {"name": "CodeQL", "root_cause": "2s fail — quick scan abort", "in_scope": "advisory, not blocking"},
        ],
        "compliance_gates": "INTACT — will NOT weaken DND/TRAI/DPDP/UPI/secret gates. "
                            "Branch-protection update only re-points required context names "
                            "to the real CI lane names that already exist and already run.",
        "owner_mandate": "han sab karo, work as admin for owner with full access, "
                         "use typesafe api calls har chat me baar baar",
    }

    # One narrow question per Noul (per skill: "ask one narrow, coherent judgment per question").
    noul_proceed = ts.Noul(
        question="proceed",
        instructions=(
            "Decide whether the agent should proceed with: (1) adding missing "
            "runtime-data allowlist entries for new MTProto scripts, (2) updating "
            "classic branch-protection required context names to match actual CI lane "
            "names, (3) re-running CI, (4) merging PR #543, (5) deploying via "
            "scripts/deploy_vps.sh. Yes if all steps are in-scope, reversible, "
            "owner-mandated, and no compliance gate is weakened. No otherwise."
        ),
    )
    noul_confidence = ts.Noul(
        question="diagnosis_confidence",
        instructions=(
            "How confident are you that the stated root causes (xdist flake fixed, "
            "allowlist drift, stale branch-protection context names) fully explain "
            "every blocking lane? Yes=high confidence, No=missing something."
        ),
    )
    noul_risk = ts.Noul(
        question="compliance_risk",
        instructions=(
            "Is there a risk that updating branch-protection context names would "
            "weaken a security check (e.g. point at a weaker lane)? "
            "Yes=risk present, No=update is a safe re-pointing."
        ),
    )

    client = ts.TypeSafeClient()
    print(f"[typesafe] enabled={client.enabled} model={client.model}")
    resp = client.system_one(
        state=state,
        questions={
            "proceed": noul_proceed,
            "diagnosis_confidence": noul_confidence,
            "compliance_risk": noul_risk,
        },
    )
    elapsed = time.time() - started

    trace_dir = ROOT / "data" / "typesafe"
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace = {
        "decision_id": "f0871cc3-gate-fix-deploy",
        "task_id": "pr543-full-admin-chain",
        "tenant_scope": "leadgenai/leadgenrationaivoiceagent",
        "purpose": "bounded judgment: proceed with gate-fix + merge + deploy",
        "state_hash": hash(json.dumps(state, sort_keys=True)) & 0xFFFFFFFF,
        "model": getattr(client, "model", "jev-latest"),
        "evidence_refs": [
            "gh pr checks 543",
            "scripts/_branch_protection_probe.py",
            "scripts/_check_runs_probe.py",
            "scripts/_ctx_drift_probe.py",
            "commit 6bb557b3 (xdist flake fix)",
        ],
        "answers": {k: (v.value() if hasattr(v, "value") else v) for k, v in resp.answers.items()},
        "success": resp.success,
        "error": resp.error,
        "latency_sec": round(elapsed, 3),
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    trace_path = trace_dir / f"trace_{int(started)}.json"
    trace_path.write_text(json.dumps(trace, indent=2), encoding="utf-8")
    print(f"[typesafe] trace -> {trace_path.name} ({elapsed:.1f}s) success={resp.success}")
    if not resp.success:
        print(f"[typesafe] error={resp.error}")
        return 1
    for name, ans in trace["answers"].items():
        print(f"  {name}: {ans}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
