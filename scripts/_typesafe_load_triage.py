#!/usr/bin/env python3
"""TypeSafe #10: production is healthy-serving (2962d26e, public 200 earlier) but
the VPS load average is extreme (136 on a 4-core box ~ 34x). Decide posture:
is the heavy load a pre-existing ops condition to triage, or a NEW problem the
deploy/agent actions introduced that must be reversed?"""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.platform import typesafe_integration as ts


def main() -> int:
    started = time.time()
    state = {
        "prod_serving": "leadgen_app on image 2962d26e, local /health 200, uptime ~1h24m, "
                        "WEB_CONCURRENCY=1. Public site returned 200 on multiple probes. "
                        "The TypeSafe/telegram content (PR#543) is LIVE.",
        "vps_load": "load avg ~136-179 on a 4-core VPS (34x-45x oversubscribed). "
                    "Multiple celery workers + python + cadvisor + chromium + observability "
                    "stack + a pre-existing `docker image prune -af until=24h` retention loop "
                    "all resident.",
        "agent_actions_this_session": [
            "deploy_vps.sh (built + rolled workers to e91e45e6; app stayed 2962d26e)",
            "manual recreate of leadgen_app + telegram-jarvis on 2962d26e",
            "a `docker image prune -f` + `docker builder prune -f` I launched (now killed)",
            "git pull --ff-only to e91e45e6 (compose-only diff)",
        ],
        "question": "Given prod is serving correctly, is the extreme load most likely "
                    "PRE-EXISTING platform oversubscription (many resident services) that "
                    "needs ops triage (identify + shed the heaviest non-essential consumer), "
                    "vs a NEW problem I must REVERSE by reverting the deploy?",
        "owner_mandate": "auto-pilot, sab karo, full access admin, typesafe har chat me baar baar",
    }
    questions = {
        "pre_existing_oversubscription": ts.Noul(
            question="Is the extreme load most plausibly PRE-EXISTING platform "
                     "oversubscription (many resident observability/voice/worker services "
                     "on an under-provisioned 4-core box) rather than something my deploy "
                     "introduced? Yes=pre-existing, No=likely agent-introduced."
        ),
        "should_revert_deploy": ts.Noul(
            question="Given the app is serving correctly at 2962d26e with no crash loop, "
                     "should I REVERT the deploy (roll workers back to 883ef713) to reduce "
                     "load? Yes=revert, No=do not revert (load is not from the deploy)."
        ),
        "next_best_action": ts.Noul(
            question="Is the highest-leverage next action to IDENTIFY the heaviest "
                     "CPU/consumer and shed the least-essential load (rather than blind "
                     "revert)? Yes=diagnose-heaviest-first, No=other."
        ),
    }
    client = ts.TypeSafeClient()
    resp = client.system_one(state=state, questions=questions)
    elapsed = time.time() - started
    tdir = ROOT / "data" / "typesafe"; tdir.mkdir(parents=True, exist_ok=True)
    trace = {
        "decision_id": "vps-extreme-load-triage",
        "task_id": "autopilot-load-triage",
        "tenant_scope": "leadgenai/leadgenrationaivoiceagent",
        "purpose": "bounded judgment: pre-existing vs agent-introduced load + whether to revert",
        "state_hash": hash(json.dumps(state, sort_keys=True)) & 0xFFFFFFFF,
        "model": "jev-latest",
        "evidence_refs": [
            "/proc/loadavg ~136 on 4-core",
            "leadgen_app 2962d26e serving, WEB_CONCURRENCY=1",
            "public https://leadsgenai.in/health = 200 (multi-probe)",
            "agent prune jobs already killed",
        ],
        "answers": {k: (v.value() if hasattr(v, "value") else v) for k, v in resp.answers.items()},
        "success": resp.success, "error": resp.error,
        "latency_sec": round(elapsed, 3),
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    tp = tdir / f"trace_{int(started)}.json"
    tp.write_text(json.dumps(trace, indent=2), encoding="utf-8")
    print(f"[typesafe #10] trace -> {tp.name} ({elapsed:.1f}s) success={resp.success}")
    for name, ans in trace["answers"].items():
        print(f"  {name}: {ans}")
    return 0 if resp.success else 1


if __name__ == "__main__":
    sys.exit(main())
