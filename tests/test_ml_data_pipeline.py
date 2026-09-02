"""Regression tests for app/ml/data_pipeline.py training-data plumbing.

Covers the 2026-07-04 missing-work-audit fixes:
- get_training_data() must reconstruct turns + features (was dropping both,
  silently starving the intent classifier and feeding the lead scorer zeros).
- export_for_finetuning() must emit message pairs (was exporting 0 lines)
  and must scrub PII (phone/email) from transcript content.
"""

import json

from app.ml.data_pipeline import (
    ConversationDataPipeline,
    ConversationOutcome,
    scrub_pii,
)


def _write_record(data_dir, conv_id="conv1", outcome="interested"):
    tenant_dir = data_dir / "default"
    tenant_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "conversation_id": conv_id,
        "call_id": f"call_{conv_id}",
        "tenant_id": "default",
        "lead_id": "lead1",
        "lead_phone": "+919876543210",
        "lead_company": "Test Co",
        "lead_industry": "salon",
        "lead_city": "Mumbai",
        "turns": [
            {
                "role": "user",
                "content": "mera number 98765 43210 hai aur email test@example.com",
                "timestamp": "2026-07-01T10:00:00",
                "intent": "share_contact",
                "confidence": 0.9,
                "entities": {},
                "response_time_ms": 100,
            },
            {
                "role": "agent",
                "content": "dhanyavaad, main note kar leti hoon",
                "timestamp": "2026-07-01T10:00:05",
                "intent": None,
                "confidence": 0.0,
                "entities": {},
                "response_time_ms": 800,
            },
            {
                "role": "user",
                "content": "haan interested hoon",
                "timestamp": "2026-07-01T10:00:10",
                "intent": "interested",
                "confidence": 0.8,
                "entities": {},
                "response_time_ms": 100,
            },
        ],
        "outcome": outcome,
        "outcome_details": {"note": "test"},
        "features": {
            "total_turns": 3,
            "user_turns": 2,
            "agent_turns": 1,
            "positive_signals": 1,
            "has_budget": True,
        },
        "conversation_embedding": [],
        "created_at": "2026-07-01T10:00:00",
        "language": "hinglish",
        "model_used": "test",
        "human_rating": None,
        "predicted_quality": 0.0,
        "conversion_probability": 0.0,
    }
    (tenant_dir / f"{conv_id}.json").write_text(
        json.dumps(record, ensure_ascii=False), encoding="utf-8"
    )


def test_get_training_data_reconstructs_turns_and_features(tmp_path):
    pipeline = ConversationDataPipeline(data_dir=str(tmp_path / "conv"))
    _write_record(pipeline.data_dir)

    records = pipeline.get_training_data(min_turns=3)

    assert len(records) == 1
    rec = records[0]
    assert len(rec.turns) == 3
    assert rec.turns[0].role == "user"
    assert rec.turns[0].intent == "share_contact"
    assert rec.features.total_turns == 3
    assert rec.features.has_budget is True
    assert rec.outcome == ConversationOutcome.INTERESTED


def test_export_for_finetuning_emits_scrubbed_pairs(tmp_path):
    pipeline = ConversationDataPipeline(data_dir=str(tmp_path / "conv"))
    _write_record(pipeline.data_dir)
    out = tmp_path / "export.jsonl"

    count = pipeline.export_for_finetuning(str(out))

    assert count == 1
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1  # was 0 before the turns-reconstruction fix
    first = json.loads(lines[0])
    user_content = first["messages"][0]["content"]
    assert "98765" not in user_content
    assert "test@example.com" not in user_content
    assert "[phone]" in user_content
    assert "[email]" in user_content


def test_scrub_pii_masks_phone_and_email():
    assert scrub_pii("call me at 9876543210") == "call me at [phone]"
    assert scrub_pii("ya +91 98765 43210 pe") == "ya [phone] pe"
    assert scrub_pii("mail: abc.xyz+1@gmail.com") == "mail: [email]"
    assert scrub_pii("") == ""
    assert scrub_pii("koi PII nahi") == "koi PII nahi"
