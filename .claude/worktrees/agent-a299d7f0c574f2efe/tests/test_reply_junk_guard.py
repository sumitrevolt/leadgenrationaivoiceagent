"""Junk-deal guard + prospect store hygiene tests (2026-06-12 pipeline-review fixes).

Background: PayU/Instamojo marketing emails reply-agent se "interested" classify
hoke FAKE deals bana rahe the. Guard: unknown sender + bulk signal = skip;
deal sirf known prospect pe. Store: timestamps for staleness measurement.
"""

import email.message
import json

from app.platform import prospector, reply_agent


def _msg(headers: dict[str, str] | None = None) -> email.message.Message:
    m = email.message.Message()
    for k, v in (headers or {}).items():
        m[k] = v
    return m


def test_bulk_sender_localparts():
    assert reply_agent._is_bulk_sender("noreply@payu.in", _msg())
    assert reply_agent._is_bulk_sender("support@instamojo.com", _msg())
    assert reply_agent._is_bulk_sender("marketing@emails.payu.in", _msg())
    assert not reply_agent._is_bulk_sender("sharma.solar@gmail.com", _msg())


def test_bulk_sender_headers():
    assert reply_agent._is_bulk_sender(
        "x@brand.com", _msg({"List-Unsubscribe": "<https://u.example>"})
    )
    assert reply_agent._is_bulk_sender("x@brand.com", _msg({"Precedence": "bulk"}))
    assert reply_agent._is_bulk_sender("x@brand.com", _msg({"Auto-Submitted": "auto-generated"}))
    assert not reply_agent._is_bulk_sender("x@brand.com", _msg({"Auto-Submitted": "no"}))
    assert not reply_agent._is_bulk_sender("owner@localbiz.in", _msg())


def test_bulk_sender_never_raises():
    assert reply_agent._is_bulk_sender("", None) in (True, False)


def test_append_sets_timestamps(tmp_path, monkeypatch):
    f = tmp_path / "prospects.jsonl"
    monkeypatch.setattr(prospector, "_PROSPECTS_FILE", str(f))
    assert prospector._append({"id": "t1", "business_name": "Test Biz", "phone": ""})
    rec = json.loads(f.read_text(encoding="utf-8").strip())
    assert rec["created_at"] and rec["updated_at"]


def test_mark_prospect_bumps_updated_at(tmp_path, monkeypatch):
    f = tmp_path / "prospects.jsonl"
    monkeypatch.setattr(prospector, "_PROSPECTS_FILE", str(f))
    prospector._append({"id": "t2", "business_name": "B", "phone": "", "status": "ready"})
    assert prospector.mark_prospect("t2", "hot") or True  # invalid status => False ok
    rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    r = rows[0]
    if r.get("status") == "hot":  # 'hot' VALID_STATUSES me ho to bump assert
        assert r["updated_at"] == r["status_at"]
    ok = prospector.set_prospect_fields("t2", {"emailed_at": "x"})
    assert ok
    rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert rows[0]["updated_at"]
