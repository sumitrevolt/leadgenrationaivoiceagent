"""ADR-027 (council 2026-07-06): phone-type gate + learned DID blocklist + feedback loop.

Prod audit: 6,169 "ready" prospects me 649 FIXED_LINE cloud-IVR DIDs (Livspace
8047759152/34/33 sequential block, HDFC 8071888414) — 05-Jul batch ne inhe dial
karke IVR-machines ko pitch kiya. RED-proven: DIAL_TEST_MODE=0 par purana
dial_gate.check('+918047759152','promotional') == (True,'test_mode_off').

Layers under test:
1. dial_gate.phone_quality — libphonenumber IN-plan mapping (numbers prod-verified).
2. dial_gate.check — promotional par fixed/tollfree/invalid BLOCK; mobile/flom pass;
   allowlist = owner override; transactional kabhi gated nahi; flag rollback.
3. call_feedback.record_ivr_confirmed — number-block turant; prefix-block sirf
   >= 3 DISTINCT confirmed numbers (over-block guard); audit trail; prospect tag.
4. lead_harvester._valid_phone — ab sach me MOBILE enforce karta hai.
"""

from __future__ import annotations

import json

import pytest

from app.platform.lead_harvester import _valid_phone
from app.telephony import call_feedback, dial_gate

# Prod-verified classifications (2026-07-06 audit; libphonenumber IN plan):
FIXED_LINE_IVR = "8047759152"  # Livspace cloud-DID (dialed 05-Jul, IVR)
FIXED_LINE_IVR_2 = "8047759134"  # same DID block
FIXED_LINE_IVR_3 = "8047759133"  # same DID block
MOBILE_REAL = "9623767939"  # real mobile from same batch
FLOM_HOT_LEAD = "7498797259"  # hot lead tha — FLOM ko hard-block NAHI karna
TOLL_FREE = "1800123456"


def _isolate(monkeypatch, tmp_path):
    """dial_gate ko test-mode OFF + saaf config/blocklist files par chalao."""
    monkeypatch.setenv("DIAL_TEST_MODE", "0")
    monkeypatch.setenv("DIAL_TEST_MODE_CONFIG", str(tmp_path / "dial_test_mode.json"))
    monkeypatch.setenv("DIAL_BLOCKLIST_FILE", str(tmp_path / "dial_blocklist.json"))
    monkeypatch.setenv("DIAL_BLOCKLIST_AUDIT", str(tmp_path / "dial_blocklist_audit.jsonl"))
    monkeypatch.delenv("DIAL_TEST_ALLOWLIST", raising=False)
    monkeypatch.delenv("PHONE_TYPE_GATE", raising=False)
    monkeypatch.delenv("LEARNED_DID_BLOCKLIST", raising=False)
    monkeypatch.delenv("LEARNED_BLOCK_THRESHOLD", raising=False)
    monkeypatch.delenv("CALL_FEEDBACK_LOOP", raising=False)


# --------------------------------------------------------------------------- #
# 1. phone_quality
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "num,expected",
    [
        (FIXED_LINE_IVR, "fixed"),
        (MOBILE_REAL, "mobile"),
        (FLOM_HOT_LEAD, "flom"),
        (TOLL_FREE, "tollfree"),
        ("123", "invalid"),
        ("", "invalid"),
    ],
)
def test_phone_quality_mapping(num, expected):
    assert dial_gate.phone_quality(num) == expected


def test_phone_quality_accepts_e164_and_prefixed():
    assert dial_gate.phone_quality("+91" + FIXED_LINE_IVR) == "fixed"
    assert dial_gate.phone_quality("0" + MOBILE_REAL) == "mobile"


# --------------------------------------------------------------------------- #
# 2. dial_gate.check — phone-type layer
# --------------------------------------------------------------------------- #
def test_fixed_line_promotional_blocked(monkeypatch, tmp_path):
    """THE 05-Jul bug: fixed-line IVR DID promotional-dial ab BLOCKED."""
    _isolate(monkeypatch, tmp_path)
    allowed, reason = dial_gate.check("+91" + FIXED_LINE_IVR, "promotional")
    assert allowed is False
    assert "phone_type_gate" in reason


def test_tollfree_promotional_blocked(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    assert dial_gate.check(TOLL_FREE, "promotional")[0] is False


def test_mobile_and_flom_promotional_allowed(monkeypatch, tmp_path):
    """Mobile pass; FLOM bhi pass (hot lead isi type ka tha — council decision)."""
    _isolate(monkeypatch, tmp_path)
    assert dial_gate.check("+91" + MOBILE_REAL, "promotional") == (True, "gates_passed")
    assert dial_gate.check("+91" + FLOM_HOT_LEAD, "promotional") == (True, "gates_passed")


def test_transactional_never_type_gated(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    assert dial_gate.check("+91" + FIXED_LINE_IVR, "transactional")[0] is True


def test_allowlist_owner_override_beats_type_gate(monkeypatch, tmp_path):
    """Owner ne explicitly allowlist kiya (test numbers) => type-gate skip."""
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("DIAL_TEST_ALLOWLIST", FIXED_LINE_IVR)
    assert dial_gate.check("+91" + FIXED_LINE_IVR, "promotional") == (True, "allowlisted")


def test_phone_type_gate_flag_rollback(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("PHONE_TYPE_GATE", "0")
    assert dial_gate.check("+91" + FIXED_LINE_IVR, "promotional")[0] is True


def test_test_mode_on_still_blocks_everything_unlisted(monkeypatch, tmp_path):
    """Existing fail-closed test-mode ka behavior unchanged (mobile bhi block)."""
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("DIAL_TEST_MODE", "1")
    assert dial_gate.check("+91" + MOBILE_REAL, "promotional")[0] is False


# --------------------------------------------------------------------------- #
# 3. call_feedback — self-improve loop
# --------------------------------------------------------------------------- #
def _no_prospect_store(monkeypatch):
    from app.platform import prospector

    monkeypatch.setattr(prospector, "_read_all", lambda: [])


def test_confirmed_number_blocks_immediately(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _no_prospect_store(monkeypatch)
    r = call_feedback.record_ivr_confirmed("+91" + FIXED_LINE_IVR, call_sid="test1")
    assert r["ok"] is True and r["prefix_hits"] == 1 and r["prefix_active"] is False
    allowed, reason = dial_gate.check("+91" + FIXED_LINE_IVR, "promotional")
    assert allowed is False
    assert "learned_block:number" in reason


def test_prefix_blocks_only_at_threshold(monkeypatch, tmp_path):
    """Council/risk guard: prefix over-block nahi — 3 DISTINCT confirmed chahiye."""
    _isolate(monkeypatch, tmp_path)
    _no_prospect_store(monkeypatch)
    other_same_prefix = "8047759199"  # unconfirmed number, same 804775 block
    call_feedback.record_ivr_confirmed(FIXED_LINE_IVR)
    call_feedback.record_ivr_confirmed(FIXED_LINE_IVR_2)
    # 2 hits < 3 => doosre numbers ABHI free
    assert "learned_block" not in dial_gate.check(other_same_prefix, "promotional")[1]
    r3 = call_feedback.record_ivr_confirmed(FIXED_LINE_IVR_3)
    assert r3["prefix_hits"] == 3 and r3["prefix_active"] is True
    allowed, reason = dial_gate.check(other_same_prefix, "promotional")
    assert allowed is False
    assert "learned_block:prefix" in reason


def test_duplicate_confirms_count_distinct_numbers(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _no_prospect_store(monkeypatch)
    for _ in range(5):  # same number 5x — sirf 1 distinct
        r = call_feedback.record_ivr_confirmed(FIXED_LINE_IVR)
    assert r["prefix_hits"] == 1 and r["prefix_active"] is False


def test_feedback_writes_audit_trail(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _no_prospect_store(monkeypatch)
    call_feedback.record_ivr_confirmed(
        FIXED_LINE_IVR, source="post_call_bot", detail="ivr_phrase:welcome to"
    )
    lines = (
        (tmp_path / "dial_blocklist_audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    )
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["phone"] == FIXED_LINE_IVR and entry["source"] == "post_call_bot"


def test_feedback_tags_prospect(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    from app.platform import prospector

    tagged = {}
    monkeypatch.setattr(
        prospector, "_read_all", lambda: [{"id": "p1", "phone": "+91" + FIXED_LINE_IVR}]
    )
    monkeypatch.setattr(
        prospector,
        "set_prospect_fields",
        lambda pid, fields: tagged.update({pid: fields}) or True,
    )
    r = call_feedback.record_ivr_confirmed(FIXED_LINE_IVR)
    assert r["prospect_tagged"] is True
    assert tagged["p1"]["dial_block"].startswith("ivr_confirmed")


def test_feedback_loop_flag_off(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("CALL_FEEDBACK_LOOP", "0")
    assert call_feedback.record_ivr_confirmed(FIXED_LINE_IVR)["ok"] is False


def test_learned_blocklist_flag_rollback(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _no_prospect_store(monkeypatch)
    call_feedback.record_ivr_confirmed(FIXED_LINE_IVR)
    monkeypatch.setenv("LEARNED_DID_BLOCKLIST", "0")
    # blocklist off => sirf phone-type gate bacha (fixed line phir bhi block —
    # reason alag hona chahiye)
    allowed, reason = dial_gate.check("+91" + FIXED_LINE_IVR, "promotional")
    assert allowed is False and "learned_block" not in reason


# --------------------------------------------------------------------------- #
# 4. lead_harvester._valid_phone — mobile enforcement
# --------------------------------------------------------------------------- #
def test_harvester_rejects_fixed_line():
    assert _valid_phone("+91" + FIXED_LINE_IVR) == ""
    assert _valid_phone("080-4775 9152") == ""


def test_harvester_accepts_mobile_and_flom():
    assert _valid_phone(MOBILE_REAL) == "+91" + MOBILE_REAL
    # FLOM is_mobile=True in phone_validate (FIXED_LINE_OR_MOBILE included)
    assert _valid_phone(FLOM_HOT_LEAD) == "+91" + FLOM_HOT_LEAD


def test_harvester_rejects_garbage():
    assert _valid_phone("call now 12345") == ""
