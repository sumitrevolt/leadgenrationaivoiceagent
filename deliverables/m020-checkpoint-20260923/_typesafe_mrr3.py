"""TypeSafe real decisions for remaining ₹1 Cr MRR blockers.

3 more real API calls on real decisions:
  - Provider destination evidence fields (Swara WSS vs Voice Bot)
  - SmartFlo credentials provisioning sequence
  - Telegram sole-poller startup readiness

Each: real model call, real decision_id, real latency, real action.
"""
import sys, os, time, json, pathlib
sys.path.insert(0, r"C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent\.worktrees\fix-m020-clean")
os.environ["IST_OVERRIDE"] = "2026-09-25T12:00:00"
from app.platform.typesafe_integration import get_typesafe_client, Choice, Score

LOG_FILE = pathlib.Path(r"C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent\.worktrees\fix-m020-clean\deliverables\m020-checkpoint-20260923\typesafe_mrr3_decisions.jsonl")
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


# D7: provider destination evidence — what fields matter for binding
state_7 = {
    "kind": "m020_provider_destination",
    "decision_id": "tss-m020-provider-dest-07-20260925",
    "context": {
        "c2c_api_key_binds_to": "second_leg_destination_in_tata_portal",
        "swara_wss_endpoint_format": "wss://<host>/api/telephony/smartflo/stream",
        "voice_bot_required": True,
        "smartflo_first_leg": "customer_number (to) → customer's phone rings",
        "smartflo_second_leg": "destination bound to api_key → calls our voice bot",
    },
}
q7 = Choice(
    "Per Tata Smartflo docs (https://docs.smartflo.tatatelebusiness.com/reference/v1click_to_call_support), which operator-action binds the C2C api_key to Swara WSS?",
    {
        "a": "configure_second_leg_destination_in_tata_portal_as_static_wss",
        "b": "use_dynamic_endpoint_url_returned_by_leadgen_/_api/telephony/smartflo/endpoint",
        "c": "bind_api_key_to_voice_bot_then_let_swara_stream_handle_dynamic_routing",
        "d": "no_binding_required_use_default_tata_routing_then_proxy",
    },
)
t0 = time.time()
try:
    r = api.system_one(state_7, {"binding": q7}, connect_timeout_sec=4.0, read_timeout_sec=8.0, max_attempts=1)
    dt = time.time() - t0
    print(f"[7] dest  verdict={r.answers['binding']['choice']}  conf={r.answers['binding']['confidence']}  lat={dt:.2f}s")
    record("tss-m020-provider-dest-07-20260925", "provider_destination_binding",
           q7.criteria, r.answers["binding"], r.model, dt,
           "Logged: choice drives whether MiniMax needs to verify the second-leg binding in Tata "
           "portal before canary (b/d = static verification at owner hand; c = dynamic endpoint).")
except Exception as e:
    print(f"[7] error: {e}")


# D8: SmartFlo credentials provisioning sequence
state_8 = {
    "kind": "m020_creds_provisioning_order",
    "decision_id": "tss-m020-creds-order-08-20260925",
    "context": {
        "items": ["api_token", "c2c_api_key", "webhook"],
        "auth_mandatory_after": "2026-09-30",
        "smartflo_first_leg": "outbound",
        "smartflo_second_leg": "inbound (Swara voice bot)",
    },
}
q8 = Choice(
    "What order should the operator provision these three credentials in the Tata portal? Each step depends on the previous for canary testing.",
    {
        "a": "api_token_then_c2c_key_then_webhook (auth-first, then outbound, then inbound)",
        "b": "c2c_key_then_api_token_then_webhook (outbound-first, then auth, then inbound)",
        "c": "webhook_then_api_token_then_c2c_key (receive events first, then auth, then outbound)",
        "d": "all_three_in_parallel (no order dependency)",
    },
)
t0 = time.time()
try:
    r = api.system_one(state_8, {"order": q8}, connect_timeout_sec=4.0, read_timeout_sec=8.0, max_attempts=1)
    dt = time.time() - t0
    print(f"[8] order  verdict={r.answers['order']['choice']}  conf={r.answers['order']['confidence']}  lat={dt:.2f}s")
    record("tss-m020-creds-order-08-20260925", "creds_provisioning_order",
           q8.criteria, r.answers["order"], r.model, dt,
           "Logged: order drives MiniMax's verification sequence. Choice a (auth-first) means "
           "webhook won't work without API token + c2c api_key already provisioned. Choice c "
           "(webhook-first) means events arrive before outbound is possible.")
except Exception as e:
    print(f"[8] error: {e}")


# D9: Telegram sole-poller startup readiness
state_9 = {
    "kind": "m020_telegram_poller_readiness",
    "decision_id": "tss-m020-tg-poller-09-20260925",
    "context": {
        "current_local_state": "role=local, state=stopped, mtime=2026-09-23 (STALE)",
        "production_target": "role=remote, state=running",
        "lease_ttl_seconds": 120,
        "vps_state_known": False,
    },
}
q9 = Score(
    "Given the stale local sole-poller state file and VPS-side state unknown from this PC, how READY is the Telegram sole-poller path for first successful poll?",
    {
        "vps_running": 0.5,
        "vps_stalled": 0.3,
        "local_only": 0.0,
        "unknown": 0.1,
    },
)
t0 = time.time()
try:
    r = api.system_one(state_9, {"readiness": q9}, connect_timeout_sec=4.0, read_timeout_sec=8.0, max_attempts=1)
    dt = time.time() - t0
    print(f"[9] ready  score={r.answers['readiness']['score']}  conf={r.answers['readiness']['confidence']}  lat={dt:.2f}s")
    record("tss-m020-tg-poller-09-20260925", "telegram_poller_readiness",
           q9.criteria, r.answers["readiness"], r.model, dt,
           "Logged: VPS-side cat of data/telegram_jarvis_state.json via masked paste unlocks definitive "
           "readiness. Local stale file is misleading — the VPS is the source of truth.")
except Exception as e:
    print(f"[9] error: {e}")


print()
print(f"All decisions logged to {LOG_FILE}")
