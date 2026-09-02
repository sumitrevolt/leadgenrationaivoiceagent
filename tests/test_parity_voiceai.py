"""Tests — voice/AI parity batch (call_transfer, call_insights, dialer_leaderboard).

Offline + isolated: koi network/DB nahi. Stores tmp_path pe monkeypatch,
free_ai.chat mocked, Exotel leg stubbed. Style: tests/test_parity_memory.py jaisa.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _now_iso(days_ago: float = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


# --------------------------------------------------------------------------- #
# F1 — call_transfer (gated CALL_TRANSFER, Hinglish summary, drafts, jsonl log)
# --------------------------------------------------------------------------- #
def test_detect_transfer_intent():
    from app.telephony import call_transfer as ct

    assert ct.detect_transfer_intent("Mujhe owner se baat karni hai") is True
    assert ct.detect_transfer_intent("Aap mujhe TRANSFER KARO kisi insaan ko") is True
    assert ct.detect_transfer_intent("I want to talk to a human please") is True
    assert ct.detect_transfer_intent("manager se baat karwao") is True
    # negatives — normal conversation pe trigger nahi hona chahiye
    assert ct.detect_transfer_intent("haan theek hai, price batao") is False
    assert ct.detect_transfer_intent("") is False
    assert ct.detect_transfer_intent(None) is False


def test_transfer_disabled_default(tmp_path, monkeypatch):
    from app.telephony import call_transfer as ct

    monkeypatch.delenv("CALL_TRANSFER", raising=False)
    monkeypatch.setattr(ct, "_TRANSFERS", str(tmp_path / "transfers.jsonl"))

    r = asyncio.run(ct.request_transfer({"name": "Ravi"}, "9876543210"))
    assert r["ok"] is False and r["reason"] == "disabled"
    # inert = koi log file nahi bani
    assert not (tmp_path / "transfers.jsonl").exists()
    assert ct.enabled() is False


def test_transfer_enabled_flow(tmp_path, monkeypatch):
    from app.telephony import call_transfer as ct

    monkeypatch.setenv("CALL_TRANSFER", "1")
    monkeypatch.setattr(ct, "_TRANSFERS", str(tmp_path / "transfers.jsonl"))

    # Exotel leg stub (no network)
    async def fake_leg(owner10, call_id):
        assert owner10 == "9876543210"
        return {"initiated": True, "call_sid": "SIDTEST"}

    monkeypatch.setattr(ct, "_initiate_connect_leg", fake_leg)

    import app.voice_agent.free_ai as free_ai

    async def fake_chat(system=None, messages=None, **kw):
        return ("Ravi Solar (Pune) solar quote chahta hai, budget high — turant baat karo.", "mock")

    monkeypatch.setattr(free_ai, "chat", fake_chat)

    ctx = {
        "call_id": "call-1",
        "name": "Ravi Solar",
        "phone": "+919812345678",
        "niche": "solar",
        "conversation": [
            {"role": "user", "content": "solar lagwana hai, kitna kharcha?"},
            {"role": "assistant", "content": "3kW ~₹1.8L, subsidy ke baad kam."},
            {"role": "user", "content": "owner se baat karwao"},
        ],
    }
    r = asyncio.run(ct.request_transfer(ctx, "09876543210"))  # 0-prefixed bhi normalize ho
    assert r["ok"] is True and r["transferred"] is True
    assert "Ravi Solar" in r["summary"]
    assert r["wa_link"].startswith("https://wa.me/919876543210?text=")
    assert r["email_draft"]["auto_sent"] is False
    assert "9812345678" in r["email_draft"]["body"]
    assert r["connect_leg"]["call_sid"] == "SIDTEST"

    # jsonl log + list_transfers round-trip (newest first)
    rows = ct.list_transfers()
    assert len(rows) == 1
    assert rows[0]["call_id"] == "call-1" and rows[0]["owner_phone"] == "9876543210"


def test_transfer_llm_fallback_and_no_exotel(tmp_path, monkeypatch):
    from app.telephony import call_transfer as ct

    monkeypatch.setenv("CALL_TRANSFER", "1")
    monkeypatch.setattr(ct, "_TRANSFERS", str(tmp_path / "transfers.jsonl"))

    async def fake_leg(owner10, call_id):
        return {"initiated": False, "reason": "exotel_not_configured"}

    monkeypatch.setattr(ct, "_initiate_connect_leg", fake_leg)

    import app.voice_agent.free_ai as free_ai

    async def boom(*a, **kw):
        raise RuntimeError("429 rate limited")

    monkeypatch.setattr(free_ai, "chat", boom)

    ctx = {"name": "Meena Gym", "phone": "9811111111", "transcript": "membership price poocha"}
    r = asyncio.run(ct.request_transfer(ctx, "9876543210"))
    # LLM down → template fallback summary, fir bhi ok + drafts
    assert r["ok"] is True and r["transferred"] is False
    assert "Live transfer" in r["summary"] and "Meena Gym" in r["summary"]
    assert r["wa_link"] and r["email_draft"]["subject"]


def test_transfer_invalid_owner(tmp_path, monkeypatch):
    from app.telephony import call_transfer as ct

    monkeypatch.setenv("CALL_TRANSFER", "1")
    monkeypatch.setattr(ct, "_TRANSFERS", str(tmp_path / "transfers.jsonl"))
    r = asyncio.run(ct.request_transfer({}, "12345"))
    assert r["ok"] is False and "invalid" in r["reason"]


# --------------------------------------------------------------------------- #
# F2 — call_insights (quick_stats pure-python + ask LLM/fallback)
# --------------------------------------------------------------------------- #
def _seed_insights(tmp_path, monkeypatch):
    from app.platform import call_insights as ci

    qf = tmp_path / "quals.jsonl"
    df = tmp_path / "dialer.jsonl"
    cf = tmp_path / "cadence.jsonl"
    _write_jsonl(
        qf,
        [
            {
                "call_id": "c1",
                "interest_score": 4,
                "qualified": True,
                "appointment_requested": True,
                "budget_signal": "high",
                "summary": "solar chahiye",
            },
            {
                "call_id": "c2",
                "interest_score": 2,
                "qualified": False,
                "appointment_requested": False,
                "budget_signal": "unknown",
                "summary": "baad me",
            },
        ],
    )
    _write_jsonl(
        df,
        [
            {"phone": "9876543210", "disposition": "interested", "notes": "", "at": _now_iso()},
            {"phone": "9811111111", "disposition": "no-answer", "notes": "", "at": _now_iso()},
        ],
    )
    _write_jsonl(cf, [{"phone": "9876543210", "channel": "email", "action": "intro", "day": 0}])

    monkeypatch.setattr(ci, "_QUALIFICATIONS", str(qf))
    monkeypatch.setattr(ci, "_DIALER_LOGS", str(df))
    monkeypatch.setattr(ci, "_CADENCE_RUNS", str(cf))
    monkeypatch.setattr(ci, "_recent_agent_events", lambda limit=30: [])
    tdir = tmp_path / "call_transcripts"
    tdir.mkdir()
    tfile = tdir / "2026-06-18.jsonl"
    _write_jsonl(
        tfile,
        [
            {
                "stream_sid": "sid-1",
                "niche": "solar",
                "client_name": "Acme",
                "duration_s": 120.5,
                "user_turns": 3,
                "ts": _now_iso(),
                "messages": [{"role": "user", "content": "mujhe solar chahiye"}],
            }
        ],
    )
    monkeypatch.setattr(ci, "_TRANSCRIPTS_DIR", lambda: str(tdir))
    return ci


def test_quick_stats_counts(tmp_path, monkeypatch):
    ci = _seed_insights(tmp_path, monkeypatch)
    s = ci.quick_stats()
    assert s["calls_qualified"]["total"] == 2
    assert s["calls_qualified"]["qualified"] == 1
    assert s["calls_qualified"]["appointments_requested"] == 1
    assert s["calls_qualified"]["avg_interest_score"] == 3.0
    assert s["calls_qualified"]["by_budget_signal"]["high"] == 1
    assert s["dialer"]["total_logged"] == 2 and s["dialer"]["today"] == 2
    assert s["dialer"]["by_disposition"]["interested"] == 1
    assert s["cadence"]["by_channel"]["email"] == 1
    assert s["live_calls"]["total"] == 1
    assert s["live_calls"]["today"] == 1
    assert s["live_calls"]["total_user_turns"] == 3


def test_ask_includes_transcript_context(tmp_path, monkeypatch):
    ci = _seed_insights(tmp_path, monkeypatch)
    import app.voice_agent.free_ai as free_ai

    captured = {}

    async def fake_chat(system=None, messages=None, **kw):
        captured["user"] = messages[0]["content"]
        return ("1 live call aaj, solar niche.", "mock")

    monkeypatch.setattr(free_ai, "chat", fake_chat)
    r = asyncio.run(ci.ask("aaj kitni live calls?"))
    assert r["ok"] is True
    assert "LIVE phone transcripts" in captured["user"]
    assert "mujhe solar chahiye" in captured["user"]


def test_quick_stats_missing_files(tmp_path, monkeypatch):
    from app.platform import call_insights as ci

    monkeypatch.setattr(ci, "_QUALIFICATIONS", str(tmp_path / "nope1.jsonl"))
    monkeypatch.setattr(ci, "_DIALER_LOGS", str(tmp_path / "nope2.jsonl"))
    monkeypatch.setattr(ci, "_CADENCE_RUNS", str(tmp_path / "nope3.jsonl"))
    s = ci.quick_stats()
    assert s["calls_qualified"]["total"] == 0 and s["dialer"]["total_logged"] == 0


def test_ask_with_llm(tmp_path, monkeypatch):
    ci = _seed_insights(tmp_path, monkeypatch)

    import app.voice_agent.free_ai as free_ai

    captured = {}

    async def fake_chat(system=None, messages=None, **kw):
        captured["user"] = messages[0]["content"]
        return ("Aaj 1 interested mila (9876543210) — turant follow-up karo.", "mock")

    monkeypatch.setattr(free_ai, "chat", fake_chat)

    r = asyncio.run(ci.ask("aaj kitne interested the?"))
    assert r["ok"] is True and r["provider"] == "mock"
    assert "interested" in r["answer"]
    # context me dialer + qualification data gaya ho
    assert "interested" in captured["user"] and "solar chahiye" in captured["user"]
    assert r["stats"]["dialer"]["total_logged"] == 2


def test_ask_llm_fail_stats_fallback(tmp_path, monkeypatch):
    ci = _seed_insights(tmp_path, monkeypatch)

    import app.voice_agent.free_ai as free_ai

    async def boom(*a, **kw):
        raise RuntimeError("all providers down")

    monkeypatch.setattr(free_ai, "chat", boom)

    r = asyncio.run(ci.ask("kitne calls hue?"))
    assert r["ok"] is True and r["provider"] == ""
    # stats-based fallback — phir bhi numbers ke saath useful answer
    assert "2" in r["answer"] and "interested 1" in r["answer"]

    # khaali question → fallback answer, ok False
    r2 = asyncio.run(ci.ask(""))
    assert r2["ok"] is False and r2["answer"]


# --------------------------------------------------------------------------- #
# F3 — dialer_leaderboard (ranks, score math, days filter, shoutout)
# --------------------------------------------------------------------------- #
def test_leaderboard_ranks_and_score(tmp_path, monkeypatch):
    from app.platform import dialer_leaderboard as lb

    df = tmp_path / "dialer.jsonl"
    _write_jsonl(
        df,
        [
            # Priya: 2 calls, 2 connects, 1 interested = 2+4+5 = 11
            {
                "phone": "9000000001",
                "disposition": "interested",
                "caller": "Priya",
                "at": _now_iso(),
            },
            {"phone": "9000000002", "disposition": "callback", "caller": "Priya", "at": _now_iso()},
            # Amit: 2 calls, 0 connects = 2
            {"phone": "9000000003", "disposition": "no-answer", "caller": "Amit", "at": _now_iso()},
            {
                "phone": "9000000004",
                "disposition": "wrong-number",
                "caller": "Amit",
                "at": _now_iso(),
            },
            # caller field nahi → "Team" bucket: 1 call + connect = 3
            {"phone": "9000000005", "disposition": "not-interested", "at": _now_iso()},
        ],
    )
    monkeypatch.setattr(lb, "_DIALER_LOGS", str(df))

    r = lb.leaderboard(days=1)
    assert r["total_calls"] == 5
    ranking = {row["caller"]: row for row in r["ranking"]}
    assert ranking["Priya"]["rank"] == 1 and ranking["Priya"]["score"] == 11
    assert ranking["Priya"]["interested"] == 1 and ranking["Priya"]["callbacks"] == 1
    assert ranking["Team"]["score"] == 3
    assert ranking["Amit"]["score"] == 2 and ranking["Amit"]["connects"] == 0
    assert "Priya" in r["shoutout"] and "🏆" in r["shoutout"]


def test_leaderboard_days_filter_and_empty(tmp_path, monkeypatch):
    from app.platform import dialer_leaderboard as lb

    df = tmp_path / "dialer.jsonl"
    _write_jsonl(
        df,
        [
            {
                "phone": "9000000001",
                "disposition": "interested",
                "caller": "Priya",
                "at": _now_iso(days_ago=5),
            },
            {
                "phone": "9000000002",
                "disposition": "callback",
                "caller": "Amit",
                "at": _now_iso(days_ago=0.1),
            },
        ],
    )
    monkeypatch.setattr(lb, "_DIALER_LOGS", str(df))

    # days=1 → sirf Amit (Priya 5 din purani)
    r1 = lb.leaderboard(days=1)
    assert r1["total_calls"] == 1 and r1["ranking"][0]["caller"] == "Amit"
    # days=7 → dono
    r7 = lb.leaderboard(days=7)
    assert r7["total_calls"] == 2 and len(r7["ranking"]) == 2

    # empty store → friendly shoutout, no crash
    monkeypatch.setattr(lb, "_DIALER_LOGS", str(tmp_path / "missing.jsonl"))
    r0 = lb.leaderboard(days=1)
    assert r0["total_calls"] == 0 and r0["ranking"] == [] and "📞" in r0["shoutout"]
