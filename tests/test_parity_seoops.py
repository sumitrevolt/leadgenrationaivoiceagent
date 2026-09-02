"""Tests — Agent D SEO/Ops batch (rank tracker, conversations inbox, dialer).

Pure-python: no network, no DB — file stores tmp_path pe monkeypatch hote.
"""

from __future__ import annotations

import asyncio
import json
import os

# --------------------------------------------------------------------------- #
# F1 — rank_tracker
# --------------------------------------------------------------------------- #


def test_match_position_phone_and_fuzzy_name():
    from app.platform.rank_tracker import match_position

    results = [
        {"name": "Surya Solar Solutions", "phone": "+91 98765 11111"},
        {"name": "Sharma Solar Energy Pvt Ltd", "phone": "098450 22222"},
        {"name": "Green Power Co", "phone": ""},
    ]
    # phone exact (last-10 digits) — position 2
    assert match_position(results, "Totally Different Name", "+919845022222") == 2
    # fuzzy name substring — position 1
    assert match_position(results, "surya solar", None) == 1
    # token-overlap fuzzy — "Sharma Solar" vs full name
    assert match_position(results, "Sharma Solar", None) == 2
    # not in list
    assert match_position(results, "Patel Tiles", None) is None
    # empty inputs never raise
    assert match_position([], "X", None) is None
    assert match_position(results, "", "") is None


def test_rank_track_config_upsert_and_history(tmp_path, monkeypatch):
    from app.platform import rank_tracker as rt

    monkeypatch.setattr(rt, "_CONFIG_FILE", str(tmp_path / "rank_tracking.jsonl"))
    monkeypatch.setattr(rt, "_HISTORY_FILE", str(tmp_path / "rank_history.jsonl"))

    out = rt.track(
        "c1",
        ["solar installer", "solar panel dealer"],
        "Pune",
        business_name="Sharma Solar",
        phone="9845022222",
    )
    assert out.get("ok") is True
    assert out["config"]["keywords"] == ["solar installer", "solar panel dealer"]

    # upsert — same client dobara = 1 hi config
    rt.track("c1", ["solar installer"], "Pune", business_name="Sharma Solar")
    configs = rt.list_configs()
    assert len(configs) == 1
    assert configs[0]["keywords"] == ["solar installer"]

    # validation errors (never raise)
    assert "error" in rt.track("", ["x"], "Pune")
    assert "error" in rt.track("c2", [], "Pune")

    # history read (empty + after manual append)
    assert rt.history("c1") == []
    rt._append_jsonl(
        rt._HISTORY_FILE, {"client_id": "c1", "position": 3, "checked_at": "2026-06-10T00:00:00"}
    )
    h = rt.history("c1")
    assert len(h) == 1 and h[0]["position"] == 3
    assert rt.history("other") == []


def test_rank_run_if_enabled_gated_off(monkeypatch):
    from app.platform import rank_tracker as rt

    monkeypatch.delenv("RANK_TRACKER", raising=False)
    res = asyncio.run(rt.run_if_enabled())
    assert res.get("ok") is False
    assert "RANK_TRACKER" in str(res.get("skipped"))


def test_check_rank_missing_inputs_never_raises():
    from app.platform import rank_tracker as rt

    res = asyncio.run(rt.check_rank("", "", "", ""))
    assert "error" in res


# --------------------------------------------------------------------------- #
# F2 — conversations
# --------------------------------------------------------------------------- #


def test_thread_key_phone_email_session():
    from app.platform.conversations import thread_key

    assert thread_key({"phone": "+91 98765-43210"}) == "p:9876543210"
    assert thread_key({"from": "Ramesh <ramesh@gmail.com>"}) == "e:ramesh@gmail.com"
    assert thread_key({"from": "919876543210@whatsapp"}) == "p:9876543210"
    assert thread_key({"session_id": "abc123"}) == "s:abc123"
    assert thread_key({}) == ""
    assert thread_key({"phone": "123"}) == ""  # too short — unkeyable


def test_conversations_aggregate_and_reply_draft(tmp_path, monkeypatch):
    from app.platform import conversations as cv

    monkeypatch.setattr(cv, "_REPLY_DRAFTS", str(tmp_path / "reply_drafts.jsonl"))
    monkeypatch.setattr(cv, "_WIDGET_CHATS", str(tmp_path / "widget_chats.jsonl"))
    monkeypatch.setattr(cv, "_INQUIRIES", str(tmp_path / "inquiries.jsonl"))
    monkeypatch.setattr(cv, "_OUR_REPLIES", str(tmp_path / "conversation_replies.jsonl"))
    monkeypatch.setattr(cv, "_CALL_TRANSCRIPTS_DIR", lambda: str(tmp_path / "call_transcripts"))
    monkeypatch.setattr(cv, "_CADENCE_RUNS", str(tmp_path / "cadence_runs.jsonl"))
    monkeypatch.setattr(cv, "_INTERACTIONS", str(tmp_path / "interactions.jsonl"))

    # missing files = empty, never raises
    assert cv.list_threads() == []
    assert cv.get_thread("p:9876543210")["messages"] == []

    # seed: inquiry (phone) + email reply + widget chat (session)
    with open(cv._INQUIRIES, "w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "at": "2026-06-10T05:00:00",
                    "name": "Ramesh",
                    "phone": "+919876543210",
                    "message": "Solar lagwana hai",
                    "niche": "solar",
                    "city": "Pune",
                }
            )
            + "\n"
        )
    with open(cv._REPLY_DRAFTS, "w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "from": "owner@biz.in",
                    "subject": "Re: pricing",
                    "intent": "interested",
                    "draft": "Haan bilkul!",
                    "at": "2026-06-10T06:00:00",
                }
            )
            + "\n"
        )
        f.write("NOT-JSON-LINE\n")  # corrupt line skip hoti hai
    with open(cv._WIDGET_CHATS, "w", encoding="utf-8") as f:
        f.write(
            json.dumps({"session_id": "s9", "text": "price kya hai?", "at": "2026-06-10T07:00:00"})
            + "\n"
        )

    threads = cv.list_threads()
    keys = {t["key"] for t in threads}
    assert keys == {"p:9876543210", "e:owner@biz.in", "s:s9"}

    th = cv.get_thread("p:9876543210")
    assert th["count"] == 1
    assert th["contact"]["wa_link"].endswith("919876543210")
    assert "Solar lagwana hai" in th["messages"][0]["text"]

    # manual reply draft (no auto-send)
    out = cv.add_manual_reply_draft("p:9876543210", "Kal 11 baje call karta hoon")
    assert out.get("ok") is True
    th2 = cv.get_thread("p:9876543210")
    assert th2["count"] == 2
    assert any(m["direction"] == "draft" for m in th2["messages"])

    # validation
    assert "error" in cv.add_manual_reply_draft("", "x")
    assert "error" in cv.add_manual_reply_draft("p:9876543210", "")


# --------------------------------------------------------------------------- #
# F3 — dialer_log
# --------------------------------------------------------------------------- #


def test_dialer_status_mapping():
    from app.platform.dialer_log import status_for

    assert status_for("interested") == "replied"
    assert status_for("wrong-number") == "dead"
    assert status_for("not-interested") == "dead"
    assert status_for("callback") is None
    assert status_for("no-answer") is None
    assert status_for("bogus") is None


def test_dialer_log_and_stats(tmp_path, monkeypatch):
    from app.platform import dialer_log as dl

    monkeypatch.setattr(dl, "_DIALER_LOGS", str(tmp_path / "dialer_logs.jsonl"))

    # invalid inputs = error dicts, never raise
    assert "error" in dl.log_disposition("12", "interested")
    assert "error" in dl.log_disposition("9876543210", "maybe-later")

    out = dl.log_disposition("+91 98765 43210", "interested", notes="bola demo bhejo")
    assert out.get("ok") is True
    assert out["logged"]["phone"] == "9876543210"
    assert out["logged"]["disposition"] == "interested"

    dl.log_disposition("9876543211", "no-answer")
    s = dl.stats_today()
    assert s["total_calls"] == 2
    assert s["by_disposition"]["interested"] == 1
    assert s["by_disposition"]["no-answer"] == 1
    assert os.path.isfile(dl._DIALER_LOGS)


# --------------------------------------------------------------------------- #
# Router import sanity (no app boot, no DB)
# --------------------------------------------------------------------------- #


def test_seoops_router_importable():
    from app.api.seoops import router

    paths = {r.path for r in router.routes}
    assert "/seoops/rank/config" in paths
    assert "/seoops/rank/check" in paths
    assert "/seoops/rank/run" in paths
    assert "/seoops/rank/history" in paths
    assert "/seoops/conversations" in paths
    assert "/seoops/conversations/{key}" in paths
    assert "/seoops/conversations/{key}/reply" in paths
    assert "/seoops/dialer/disposition" in paths
    assert "/seoops/dialer/stats" in paths
