"""Summarize latest call transcript on prod."""

import json
import sys
from pathlib import Path

path = Path("/opt/leadgen/data/call_transcripts/2026-07-17.jsonl")
lines = path.read_text(encoding="utf-8").strip().splitlines()
d = json.loads(lines[-1])
print("sid", (d.get("stream_sid") or "")[:36])
print("dur", d.get("duration_s"))
print("version_deploy", "e7956290")
ss = d.get("session_state") or {}
print("closing_started", ss.get("closing_started"))
print("session_closed", ss.get("session_closed"))
tr = (d.get("turn_rollup") or {}).get("metrics") or {}
print("stt_p50", (tr.get("stt_ms") or {}).get("p50"))
print("turn_p50", (tr.get("turn_ms") or {}).get("p50"))
print("turn_p95", (tr.get("turn_ms") or {}).get("p95"))
msgs = d.get("messages") or []
for m in msgs[-8:]:
    role = m.get("role")
    content = (m.get("content") or "")[:140]
    print(f"{role}: {content}")
audit = [
    m for m in msgs if m.get("role") == "assistant" and "audit" in str(m.get("content", "")).lower()
]
post_close_idx = None
for i, m in enumerate(msgs):
    if (
        m.get("role") == "assistant"
        and "perfect" in str(m.get("content", "")).lower()
        and "whatsapp" in str(m.get("content", "")).lower()
    ):
        post_close_idx = i
        break
if post_close_idx is not None:
    after = msgs[post_close_idx + 1 :]
    post_audit = [
        m
        for m in after
        if m.get("role") == "assistant" and "audit" in str(m.get("content", "")).lower()
    ]
    print("post_handoff_audit_leak", bool(post_audit))
else:
    print("post_handoff_audit_leak", "no_handoff_marker")
