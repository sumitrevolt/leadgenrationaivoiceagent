"""Compliance-slice regression tests (2026-07-05 council decision):
- transcript PII redaction (DPDP data-at-rest minimization)
- guardrails redact_for_logs actually masks phone/UPI/long-digit-runs
All offline (no network / no live call).
"""

from app.voice_agent.guardrails import get_guardrails


def test_redact_for_logs_masks_phone_and_digits():
    g = get_guardrails()
    out = g.redact_for_logs("mera number 9812345678 hai, upi pe bhej do rahul@okhdfc")
    assert "9812345678" not in out
    assert "REDACTED" in out


def test_persist_transcript_redacts_pii(monkeypatch, tmp_path):
    """_persist_transcript must write redacted message content, never raw caller
    phone numbers, to data/call_transcripts/*.jsonl."""
    import json
    import os
    from datetime import datetime

    import app.telephony.vobiz_stream as vs

    # Build a minimal object with just the attributes _persist_transcript reads.
    obj = object.__new__(vs.VobizStreamSession) if hasattr(vs, "VobizStreamSession") else None
    # Fall back: find the session class that owns _persist_transcript
    if obj is None:
        cls = None
        for name in dir(vs):
            c = getattr(vs, name)
            if isinstance(c, type) and hasattr(c, "_persist_transcript"):
                cls = c
                break
        assert cls is not None, "session class with _persist_transcript not found"
        obj = object.__new__(cls)

    now = datetime(2026, 7, 5, 12, 0, 0)
    obj.hist = [
        {"role": "user", "content": "haan mera number 9812345678 hai"},
        {"role": "assistant", "content": "theek hai, confirm karti hoon"},
    ]
    obj._started_at = now
    obj.stream_sid = "test-sid"
    obj.niche = "solar"
    obj.client_id = None
    obj.client_name = "Demo"
    obj.voice = "swara"
    obj._stt_counts = {}
    obj._interruptions = 0
    obj._turn_metrics = None

    # Redirect the write into tmp_path by chdir
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        obj._persist_transcript(now, 12.3, 1)
        path = tmp_path / "data" / "call_transcripts" / "2026-07-05.jsonl"
        assert path.exists()
        blob = path.read_text(encoding="utf-8")
        assert "9812345678" not in blob  # raw PII must be gone
        rec = json.loads(blob.splitlines()[0])
        assert any("REDACTED" in m.get("content", "") for m in rec["messages"])
    finally:
        os.chdir(cwd)
