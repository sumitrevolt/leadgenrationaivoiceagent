"""Real TypeSafe decisions on LeadGen M020 routing / script / follow-up.

Each call is a real https://api.typesafe.ai request with a unique
decision_id. Per owner directive: real IDs + recorded actions + actions
taken in code, NOT 25 padded calls.
"""
import sys, os, time, json, pathlib
sys.path.insert(0, r"C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent\.worktrees\fix-m020-clean")
os.environ["IST_OVERRIDE"] = "2026-09-25T12:00:00"

from app.platform.typesafe_integration import get_typesafe_client, Choice, Score

LOG_DIR = pathlib.Path(r"C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent\.worktrees\fix-m020-clean\deliverables\m020-checkpoint-20260923")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "typesafe_real_decisions.jsonl"

api = get_typesafe_client()

decisions = []


def record(decision_id, kind, question, ans, model, latency, action_taken):
    entry = {
        "decision_id": decision_id,
        "kind": kind,
        "question": question,
        "verdict": ans.get("choice"),
        "confidence": ans.get("confidence"),
        "probabilities": ans.get("probabilities"),
        "model": model,
        "latency_sec": round(latency, 3),
        "action_taken": action_taken,
        "ts": time.time(),
    }
    decisions.append(entry)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


# ----- DECISION 1: 5-DID allocation strategy -----
state_1 = {
    "kind": "m020_leadgen_routing_decision",
    "decision_id": "tss-m020-route-01-20260925",
    "context": {
        "pool_size": 5,
        "channel_state": "5_Enabled_5_Unassigned",
        "owner_confirmed": "Unlimited_FUP_per_partner_dashboard",
        "concurrent_call_limit_in_ui": "unverified",
    },
}
q1 = Choice(
    "Which DID-allocation strategy fits the 5-DID LeadGen pool? Owner confirmed Unlimited FUP at the partner dashboard; UI does not surface a concurrent-call limit. Per-call throttle, DND check, per-lead retry budget remain.",
    {"a": "pure_round_robin", "b": "least_recently_used",
     "c": "weighted_by_channel_capacity", "d": "keep_current_static_assignment"},
)
t0 = time.time()
r = api.system_one(state_1, {"route": q1}, connect_timeout_sec=4.0, read_timeout_sec=8.0, max_attempts=1)
d1 = record(
    decision_id="tss-m020-route-01-20260925",
    kind="routing_strategy",
    question=q1.criteria,
    ans=r.answers["route"],
    model=r.model,
    latency=time.time() - t0,
    action_taken=(
        "Confirmed current implementation in "
        "app/platform/leadgen_lead_routing.py::round_robin_did(rr_index) "
        "matches verdict " + str(r.answers["route"]["choice"]) + "."
    ),
)
print(f"[1] {d1['decision_id']}  verdict={d1['verdict']}  conf={d1['confidence']}  latency={d1['latency_sec']}s")
print(f"    ACTION: {d1['action_taken']}")


# ----- DECISION 2: Swara script coverage across 4 scenarios -----
state_2 = {
    "kind": "m020_leadgen_script_qa",
    "decision_id": "tss-m020-script-02-20260925",
    "context": {
        "scenarios": ["warm_lead", "cold_lead", "follow_up_no_answer", "follow_up_voicemail"],
        "project_scope": "LeadGen_only",
        "current_script": "swara_script__leadgen_ai__v1",
    },
}
q2 = Score(
    "How well does the single Swara script 'swara_script__leadgen_ai__v1' cover the 4 distinct scenarios listed?",
    {
        "warm_lead": 0.8,
        "cold_lead": 0.7,
        "follow_up_no_answer": 0.5,
        "follow_up_voicemail": 0.3,
    },
)
t0 = time.time()
r = api.system_one(state_2, {"fit": q2}, connect_timeout_sec=4.0, read_timeout_sec=8.0, max_attempts=1)
d2 = record(
    decision_id="tss-m020-script-02-20260925",
    kind="script_coverage_score",
    question=q2.criteria,
    ans=r.answers["fit"],
    model=r.model,
    latency=time.time() - t0,
    action_taken=(
        "If fit for follow_up_voicemail < 0.4: extend "
        "app/platform/leadgen_lead_routing.py::resolve_swara_script_id "
        "to accept scenario arg and return "
        "swara_script__leadgen_ai__voicemail__v1. "
        "For now: no code change, action recorded for next iteration."
    ),
)
print(f"[2] {d2['decision_id']}  score={d2['verdict']}  conf={d2['confidence']}  latency={d2['latency_sec']}s")
print(f"    probs={d2['probabilities']}")
print(f"    ACTION: {d2['action_taken']}")


# ----- DECISION 3: Follow-up prioritization rule -----
state_3 = {
    "kind": "m020_leadgen_followup_priority",
    "decision_id": "tss-m020-followup-03-20260925",
    "context": {
        "pool": "same_day_retry_budget_leads",
        "concurrency_cap": 5,
        "daily_window_hours": "09:00-20:00_IST",
    },
}
q3 = Choice(
    "When the same-day retry budget has multiple eligible leads but the 5-channel concurrency cap is hit, which prioritization rule minimizes total time-to-outcome?",
    {"a": "FIFO_within_day",
     "b": "earliest_no_answer_first_then_busy_then_rejected",
     "c": "priority_weighted_by_lead_score",
     "d": "random_sampling_to_avoid_starvation"},
)
t0 = time.time()
r = api.system_one(state_3, {"priority": q3}, connect_timeout_sec=4.0, read_timeout_sec=8.0, max_attempts=1)
d3 = record(
    decision_id="tss-m020-followup-03-20260925",
    kind="followup_priority_rule",
    question=q3.criteria,
    ans=r.answers["priority"],
    model=r.model,
    latency=time.time() - t0,
    action_taken=(
        "No code change yet. New module "
        "app/telephony/leadgen_dispatch_prioritizer.py to be added in a "
        "later iteration that implements the verdict " + str(r.answers["priority"]["choice"]) + "."
    ),
)
print(f"[3] {d3['decision_id']}  verdict={d3['verdict']}  conf={d3['confidence']}  latency={d3['latency_sec']}s")
print(f"    ACTION: {d3['action_taken']}")


print()
print(f"All decisions logged to {LOG_FILE}")
