"""Probe TypeSafe response shape before firing real decisions."""
import sys, os, time
sys.path.insert(0, r"C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent\.worktrees\fix-m020-clean")
os.environ["IST_OVERRIDE"] = "2026-09-25T12:00:00"
from app.platform.typesafe_integration import get_typesafe_client, Choice, Score
api = get_typesafe_client()
print(f"client enabled={api.enabled} base_url={api.base_url} model={api.model}")
print()

state = {
    "kind": "probe",
    "decision_id": "tss-probe-shape",
    "call_index": 0,
}
q = Choice("Pick A or B.", {"a": "A", "b": "B"})
t0 = time.time()
try:
    r = api.system_one(state, {"route": q}, connect_timeout_sec=4.0, read_timeout_sec=8.0, max_attempts=1)
    dt = time.time() - t0
    print(f"model={r.model} latency={dt:.2f}s success={r.success}")
    print(f"answers type: {type(r.answers)}")
    print(f"answers keys: {list(r.answers.keys()) if isinstance(r.answers, dict) else 'N/A'}")
    if isinstance(r.answers, dict):
        for k, v in r.answers.items():
            print(f"  key={k!r}")
            print(f"  value type: {type(v).__name__}")
            print(f"  value dir: {[x for x in dir(v) if not x.startswith('_')][:30]}")
            if isinstance(v, dict):
                for k2, v2 in v.items():
                    print(f"    subkey={k2!r} subtype={type(v2).__name__}")
                    if hasattr(v2, "choice"):
                        print(f"      .choice={v2.choice}")
                    if hasattr(v2, "confidence"):
                        print(f"      .confidence={v2.confidence}")
                    if hasattr(v2, "probabilities"):
                        print(f"      .probabilities={v2.probabilities}")
                    if hasattr(v2, "score"):
                        print(f"      .score={v2.score}")
                    print(f"      raw={str(v2)[:200]}")
            else:
                print(f"    raw={str(v)[:200]}")
except Exception as e:
    print(f"error: {type(e).__name__}: {e}")
