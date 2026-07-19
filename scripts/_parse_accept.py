import json
from pathlib import Path

path = Path(
    r"c:\Users\Ratanshila\Documents\leadgenrationaiagent\data\tmp_transcript_2026-07-17.jsonl"
)
d = json.loads(path.read_text(encoding="utf-8").strip().splitlines()[-1])
print("sid", d["stream_sid"][:8])
print("turn_p50", d["turn_rollup"]["metrics"]["turn_ms"]["p50"])
print("turn_p95", d["turn_rollup"]["metrics"]["turn_ms"]["p95"])
print("stt_p50", d["turn_rollup"]["metrics"]["stt_ms"]["p50"])
ss = d.get("session_state", {})
print("closing", ss.get("closing_started"), ss.get("session_closed"))
msgs = d["messages"]
for m in msgs[-10:]:
    print(m["role"] + ":", (m.get("content") or "")[:130])
handoff = next(
    (
        i
        for i, m in enumerate(msgs)
        if m.get("role") == "assistant"
        and "perfect" in (m.get("content") or "").lower()
        and "whatsapp" in (m.get("content") or "").lower()
    ),
    None,
)
leak = [
    m
    for i, m in enumerate(msgs)
    if handoff is not None
    and i > handoff
    and m.get("role") == "assistant"
    and "audit" in (m.get("content") or "").lower()
]
print("post_handoff_audit_leak", bool(leak))
for m in leak:
    print("LEAK:", m["content"][:100])
