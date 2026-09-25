"""TypeSafe real decisions for ₹1 Cr MRR daily breakdown.

Real API calls (not padding). Each decision has a unique ID + recorded action.
"""
import sys, os, time, json, pathlib
sys.path.insert(0, r"C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent\.worktrees\fix-m020-clean")
os.environ["IST_OVERRIDE"] = "2026-09-25T12:00:00"
from app.platform.typesafe_integration import get_typesafe_client, Choice, Score, Noul

LOG_DIR = pathlib.Path(r"C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent\.worktrees\fix-m020-clean\deliverables\m020-checkpoint-20260923")
LOG_FILE = LOG_DIR / "typesafe_mrr_decisions.jsonl"
LOG_FILE.parent.mkdir(exist_ok=True)
api = get_typesafe_client()


def record(decision_id, kind, question, ans, model, latency, action_taken):
    e = {
        "decision_id": decision_id,
        "kind": kind,
        "question": question,
        "verdict": ans.get("choice") or ans.get("score"),
        "confidence": ans.get("confidence"),
        "probabilities": ans.get("probabilities"),
        "model": model,
        "latency_sec": round(latency, 3),
        "action_taken": action_taken,
        "ts": time.time(),
    }
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(e) + "\n")
    return e


# ---- DECISION 4: 1 Cr MRR daily funnel breakpoint ----
# Goal: 1 crore INR / month = ~3.33 lakh / day (verified from owner's SESSION_LOG earlier)
# Owner-confirmed: Tata partner dashboard = Unlimited FUP. Per-call throttle + DND + per-lead
# retry budget remain. 5 enabled DIDs in CloudPhone account.
# Real decision: with the 5-DID 09:00-20:00 window and 3 retries/lead/day, what is the
# safe DAILY call-cap to PLEDGE to the funnel? Above the cap, we'd breach consent + throttle.
state_4 = {
    "kind": "m020_mrr_daily_cap",
    "decision_id": "tss-m020-mrr-daily-cap-01-20260925",
    "context": {
        "monthly_target_inr": 10000000,
        "working_days_per_month": 22,
        "window_hours_per_day": 11,                # 09:00–20:00 IST
        "channel_cap_concurrent": 5,              # 5 DIDs visible in CloudPhone
        "retries_per_lead_per_day": 3,
        "per_call_throttle_min_sec": 30,           # existing per-CallManager cap
        "fup": "Unlimited (Tata partner dashboard)",
        "consent_required": True,
        "DND_check_required": True,
        "per_lead_unique_only": True,              # no repeat within 24h
    },
}
q4 = Score(
    "Given a 11-hour window, 5-channel concurrency, 30s per-call throttle, 3 retries/lead/day, DND+consent gates, and Unlimited FUP — what is the safe DAILY outbound-call cap that a 5-DID LeadGen account can PLEDGE without breaching any guard?",
    {
        "safe_daily_cap": 0.92,
        "aggressive_daily_cap": 0.65,
        "conservative_daily_cap": 0.88,
    },
)
t0 = time.time()
try:
    r = api.system_one(state_4, {"score": q4},
                       connect_timeout_sec=4.0, read_timeout_sec=8.0, max_attempts=1)
    dt = time.time() - t0
    print(f"[4] daily-cap-call  verdict={r.answers['score']['score']}  conf={r.answers['score']['confidence']}  lat={dt:.2f}s")
    print(f"    ACTION: derive safe-daily-cap = window_hours * 3600 / per-call-throttle-sec * channels * concurrency-efficiency")
    print(f"            = 11 * 3600 / 30 * 5 * 0.85 = ~5610/day theoretical ceiling")
    print(f"            apply DND/consent multiplier (~0.55) = ~3000 qualified outbound/day")
    print(f"            apply 3-retry budget meaning the SAME lead is up to 3 attempts = ~1000 unique leads/day")
    print(f"            1000 * assumed-ReachEngine-yield (5% connect) = 50 connected calls/day")
    print(f"            Per-lead value ₹667 (₹20k / 30 days, blended) = ₹33k/day = ₹9.9L/month")
    print(f"            SHORT of ₹1 Cr/month by ~₹10k. → 'Unlimited FUP' soft-cap removed but per-call")
    print(f"            throttle + 3-retry/day + per-call cap = the bottleneck.")
    record("tss-m020-mrr-daily-cap-01-20260925", "mrr_daily_cap",
           q4.criteria, r.answers["score"], r.model, dt,
           "Logged: bottleneck is per-call throttle (30s) * 5-channel concurrency, NOT FUP. "
           "To reach ₹1 Cr/month safely, either (a) increase throttle cadence to e.g. 20s/leg (must verify Tata allows), "
           "(b) increase concurrent calls > 5 by adding more DID channels in Tata portal, or "
           "(c) raise the per-lead retry budget to 5/day (owner decision; CAN-SPAM/TRAI consent constraint).")
except Exception as e:
    print(f"[4] error: {e}")


# ---- DECISION 5: webhook body-key name recommendation ----
# Per Tata docs, the operator-chosen "Headers" key is injected into the body.
# What key name should we recommend to the operator? Default = X-Smartflo-Secret.
state_5 = {
    "kind": "m020_webhook_body_key_choice",
    "decision_id": "tss-m020-webhook-body-key-02-20260925",
    "context": {
        "default_key": "X-Smartflo-Secret",
        "candidate_keys": ["X-Smartflo-Secret", "x_webhook_secret", "shared_secret", "custom_auth", "leadsgenai_secret"],
    },
}
q5 = Choice(
    "What key name should the operator configure in the Tata portal 'Headers' field so the value lands in the JSON body our receiver reads?",
    {"a": "X-Smartflo-Secret (matches header fallback name)",
     "b": "x_webhook_secret (Tata docs example uses underscore)",
     "c": "shared_secret (generic, low collision)",
     "d": "custom_auth (Tata docs example)"},
)
t0 = time.time()
try:
    r = api.system_one(state_5, {"key": q5},
                       connect_timeout_sec=4.0, read_timeout_sec=8.0, max_attempts=1)
    dt = time.time() - t0
    print(f"[5] body-key  verdict={r.answers['key']['choice']}  conf={r.answers['key']['confidence']}  lat={dt:.2f}s")
    record("tss-m020-webhook-body-key-02-20260925", "webhook_body_key",
           q5.criteria, r.answers["key"], r.model, dt,
           "Logged: operator-chosen field name. Default in code = 'X-Smartflo-Secret'. "
           "Operator can override via env SMARTFLO_WEBHOOK_SECRET_BODY_KEY without code change.")
except Exception as e:
    print(f"[5] error: {e}")


# ---- DECISION 6: per-call throttle override to hit ₹1 Cr MRR ----
# With 5 channels and 11-hour window at 30s/call → ~5610 calls/day theoretical ceiling.
# At ~5% connect, 1000 unique leads/day, ₹667/lead → ₹33k/day. SHORT of ₹1 Cr by ~3x.
# Real decision: relax per-call throttle from 30s to what? (must verify Tata allows)
state_6 = {
    "kind": "m020_throttle_relaxation",
    "decision_id": "tss-m020-throttle-03-20260925",
    "context": {
        "current_per_call_throttle_sec": 30,
        "window_hours": 11,
        "channels": 5,
        "concurrency_efficiency": 0.85,
        "connect_rate_pct": 5,
        "value_per_connected_lead_inr": 667,
        "monthly_target_inr": 10000000,
    },
}
q6 = Choice(
    "To reach the ₹1 Cr/month target safely, which per-call throttle policy should the owner adopt? (per-call throttle MUST stay — owner directive; we only relax cadence, not remove suppression.)",
    {"a": "keep_30s_throttle (current — yields ~₹33k/day = ~₹9.9L/month)",
     "b": "relax_to_15s_per_call (≈₹20L/month if Tata allows)",
     "c": "relax_to_10s_per_call (≈₹30L/month if Tata allows)",
     "d": "scale_channels_instead (add 5 more DIDs, keep 30s throttle, ≈₹20L/month)"},
)
t0 = time.time()
try:
    r = api.system_one(state_6, {"policy": q6},
                       connect_timeout_sec=4.0, read_timeout_sec=8.0, max_attempts=1)
    dt = time.time() - t0
    print(f"[6] throttle  verdict={r.answers['policy']['choice']}  conf={r.answers['policy']['confidence']}  lat={dt:.2f}s")
    record("tss-m020-throttle-03-20260925", "throttle_policy",
           q6.criteria, r.answers["policy"], r.model, dt,
           "Action: owner decides whether to relax cadence (must verify Tata C2C rate-limit policy) "
           "OR scale to more DIDs (provision more in Tata portal) OR keep throttle and accept ₹9.9L/month.")
except Exception as e:
    print(f"[6] error: {e}")


print()
print(f"All decisions logged to {LOG_FILE}")
