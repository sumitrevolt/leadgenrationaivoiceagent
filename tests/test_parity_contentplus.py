"""Tests — content/outreach plus batch (agent E).

Pure-python + mocks: NO network, NO ffmpeg, NO LLM (fallback paths assert).
Covers: outreach_variants (spintax/A-B/mailbox rotation), service_reminders,
video_clips (short-circuit + planner), gif_maker, avatar_video (key gate),
contentplus router import.
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest


# --------------------------------------------------------------------------- #
# F1: outreach_variants — spintax + A/B
# --------------------------------------------------------------------------- #
def test_spintax_render_deterministic():
    from app.marketing import outreach_variants as ov

    tpl = "{Hi|Hello|Namaste} ji, {ek idea|2 minute} hai"
    a = ov.render(tpl, seed="shop@example.com")
    b = ov.render(tpl, seed="shop@example.com")
    c = ov.render(tpl, seed="dusra@example.com")
    assert a == b  # same seed = same output
    assert "{" not in a and "|" not in a
    assert a.split(" ")[0] in {"Hi", "Hello", "Namaste"}
    assert isinstance(c, str) and "{" not in c


def test_spintax_preserves_format_placeholders():
    from app.marketing import outreach_variants as ov

    out = ov.render("{name} — {free|FREE} audit", seed=1)
    assert "{name}" in out  # no-pipe braces untouched
    assert out.endswith("audit")


def test_pick_variant_stable():
    from app.marketing import outreach_variants as ov

    vs = ["A-subject", "B-subject"]
    p1 = ov.pick_variant(vs, "owner@shop.in")
    p2 = ov.pick_variant(vs, "owner@shop.in")
    assert p1 == p2  # stable assign
    assert p1["variant"] in vs and p1["id"] in {"A", "B"}
    assert ov.pick_variant([], "x")["id"] == "A"  # empty = graceful


def test_record_and_stats_laplace_winner(tmp_path, monkeypatch):
    from app.marketing import outreach_variants as ov

    monkeypatch.setattr(ov, "_PATH", str(tmp_path / "variants.jsonl"))
    for _ in range(10):
        ov.record_send("A", "a@x.in")
    ov.record_reply("A")
    for _ in range(10):
        ov.record_send("B", "b@x.in")
    for _ in range(4):
        ov.record_reply("B")
    s = ov.stats()
    assert s["variants"]["A"]["sends"] == 10
    assert s["variants"]["B"]["replies"] == 4
    assert s["winner"] == "B"  # Laplace: (4+1)/12 > (1+1)/12
    assert 0 < s["variants"]["B"]["laplace"] < 1


def test_apply_ab_returns_subject_and_records(tmp_path, monkeypatch):
    from app.marketing import outreach_variants as ov

    store = tmp_path / "variants.jsonl"
    monkeypatch.setattr(ov, "_PATH", str(store))
    p = {"business_name": "Sharma Solar", "email": "sharma@solar.in"}
    subj, text, html = ov.apply_ab(p, "orig subject", "body", "<p>body</p>")
    assert subj and "{" not in subj and "Sharma Solar" in subj
    assert text == "body" and html == "<p>body</p>"  # body untouched
    rows = [json.loads(line) for line in store.read_text(encoding="utf-8").splitlines()]
    assert rows and rows[0]["type"] == "send"
    # bad input = original passthrough, never raises
    s2, t2, h2 = ov.apply_ab(None, "s", "t", "h")
    assert (s2, t2, h2)[1:] == ("t", "h")


# --------------------------------------------------------------------------- #
# F2: mailbox rotation
# --------------------------------------------------------------------------- #
def test_next_mailbox_rotation_and_absent(tmp_path, monkeypatch):
    from app.marketing import outreach_variants as ov

    monkeypatch.setattr(ov, "_CURSOR_PATH", str(tmp_path / "cursor.json"))
    monkeypatch.delenv("OUTREACH_MAILBOXES", raising=False)
    assert ov.next_mailbox() is None  # env absent = zero change

    boxes = [
        {"email": "a@leadsgenai.in", "password": "p1"},
        {"email": "b@leadsgenai.in", "password": "p2", "host": "smtp.x.in", "port": 587},
    ]
    monkeypatch.setenv("OUTREACH_MAILBOXES", json.dumps(boxes))
    seq = [ov.next_mailbox()["email"] for _ in range(3)]
    assert seq == ["a@leadsgenai.in", "b@leadsgenai.in", "a@leadsgenai.in"]  # round-robin

    monkeypatch.setenv("OUTREACH_MAILBOXES", "not-json")
    assert ov.next_mailbox() is None  # invalid = graceful


def test_rotate_sender_overrides_creds(tmp_path, monkeypatch):
    from app.marketing import outreach_variants as ov

    class FakeSender:
        host, port, user, password, from_email = "smtp.hostinger.com", 465, "u", "p", "u"

    monkeypatch.setattr(ov, "_CURSOR_PATH", str(tmp_path / "cursor.json"))
    monkeypatch.delenv("OUTREACH_MAILBOXES", raising=False)
    s = FakeSender()
    assert ov.rotate_sender(s) is False
    assert s.user == "u"  # untouched without env

    monkeypatch.setenv(
        "OUTREACH_MAILBOXES",
        json.dumps([{"email": "rot@x.in", "password": "pw", "host": "smtp.x.in", "port": 587}]),
    )
    assert ov.rotate_sender(s) is True
    assert s.user == "rot@x.in" and s.password == "pw"
    assert s.host == "smtp.x.in" and s.port == 587 and s.from_email == "rot@x.in"


# --------------------------------------------------------------------------- #
# F3: service_reminders
# --------------------------------------------------------------------------- #
def test_service_cycle_due_run_dedupe(tmp_path, monkeypatch):
    from datetime import date, timedelta

    from app.platform import service_reminders as sr

    monkeypatch.setattr(sr, "_PATH", str(tmp_path / "sr.jsonl"))
    past = (date.today() - timedelta(days=200)).isoformat()
    res = sr.set_cycle(
        "client-1",
        {"name": "Sharma", "phone": "9876543210"},
        "AC service",
        180,
        last_service_date=past,
    )
    assert res["ok"] and res["cycle"]["next_due"] < date.today().isoformat()

    d = sr.due(days_ahead=3)
    assert len(d) == 1 and d[0]["service"] == "AC service"

    run1 = sr.run_due()
    assert run1["ok"] and run1["count"] == 1
    draft = run1["drafts"][0]
    assert draft["status"] == "draft"
    assert draft["wa_link"].startswith("https://wa.me/919876543210?text=")
    assert "Sharma" in draft["message"] and "6 mahine" in draft["message"]

    run2 = sr.run_due()
    assert run2["count"] == 0  # same-cycle dedupe

    # service ho gayi → naya cycle future me → due empty
    sr.mark_serviced(d[0]["id"])
    assert sr.due(days_ahead=3) == []


def test_service_reminders_gated_flag(tmp_path, monkeypatch):
    from app.platform import service_reminders as sr

    monkeypatch.setattr(sr, "_PATH", str(tmp_path / "sr.jsonl"))
    monkeypatch.delenv("SERVICE_REMINDERS", raising=False)
    out = asyncio.run(sr.run_due_if_enabled())
    assert out.get("skipped") is True  # default OFF = zero change

    monkeypatch.setenv("SERVICE_REMINDERS", "1")
    out = asyncio.run(sr.run_due_if_enabled())
    assert out.get("ok") is True and "skipped" not in out


def test_service_bad_input_never_raises(tmp_path, monkeypatch):
    from app.platform import service_reminders as sr

    monkeypatch.setattr(sr, "_PATH", str(tmp_path / "sr.jsonl"))
    assert sr.set_cycle("c", {"name": "X"}, "svc", 30)["ok"] is False  # no phone
    assert sr.set_cycle("c", None, "svc", "abc")["ok"] is False
    assert sr.draft(None)["ok"] is True or "error" in sr.draft(None)


# --------------------------------------------------------------------------- #
# F4: video_clips (NO ffmpeg in tests)
# --------------------------------------------------------------------------- #
def test_video_clips_unavailable_short_circuit(monkeypatch):
    from app.marketing import video_clips as vc

    monkeypatch.setattr(vc.shutil, "which", lambda _x: None)
    assert vc.available()["ok"] is False
    res = vc.make_clips("nope.mp4")
    assert res["ok"] is False and res["reason"] == "ffmpeg_missing"
    res2 = vc.start_clip_job("nope.mp4")
    assert res2["ok"] is False and res2["reason"] == "ffmpeg_missing"


def test_plan_segments_bounds():
    from app.marketing import video_clips as vc

    segs = vc.plan_segments(600, n=3, duration=30)
    assert len(segs) == 3
    for start, dur in segs:
        assert start >= 600 * 0.05 - 0.01  # first 5% skipped
        assert start + dur <= 600 * 0.95 + 0.01  # last 5% skipped
    assert segs == sorted(segs)
    # chhoti video = single clamped clip
    short = vc.plan_segments(20, n=3, duration=30)
    assert len(short) == 1 and short[0][1] <= 30
    assert vc.plan_segments(0) == []


def test_clip_job_status_not_found(tmp_path, monkeypatch):
    from app.marketing import video_clips as vc

    monkeypatch.setattr(vc, "_JOBS_PATH", str(tmp_path / "jobs.jsonl"))
    assert vc.job_status("deadbeef1234")["reason"] == "not_found"
    assert vc.job_status("../etc")["reason"] == "bad_job_id"  # traversal locked


# --------------------------------------------------------------------------- #
# F5: gif_maker (PIL local — no network)
# --------------------------------------------------------------------------- #
def test_gif_maker_creates_animated_gif(tmp_path, monkeypatch):
    pytest.importorskip("PIL")
    from app.marketing import gif_maker as gm

    monkeypatch.setattr(gm, "_GIF_DIR", str(tmp_path / "gifs"))
    res = gm.make_gif("Offer Hai!", slug="test-client", style="pulse")
    assert res["ok"] is True
    assert os.path.isfile(res["path"]) and os.path.getsize(res["path"]) > 0
    assert res["url"].startswith("/api/contentplus/gif-file/test-client/")
    # bad style/slug = graceful defaults
    res2 = gm.make_gif("", slug="../x", style="weird")
    assert res2["ok"] is True and res2["style"] == "pulse"
    assert ".." not in res2["path"]


# --------------------------------------------------------------------------- #
# F6: avatar_video (key gate, no network)
# --------------------------------------------------------------------------- #
def test_avatar_video_key_missing_graceful(monkeypatch):
    from app.marketing import ai_image
    from app.marketing import avatar_video as av

    monkeypatch.setattr(ai_image, "_api_key", lambda: "")
    res = asyncio.run(av.avatar_post("Diwali offer", niche="solar_dealers"))
    assert res["ok"] is False and res["reason"] == "key_missing"
    # empty topic
    res2 = asyncio.run(av.avatar_post(""))
    assert res2["ok"] is False and res2["reason"] == "empty_topic"


# --------------------------------------------------------------------------- #
# Router import + route shape
# --------------------------------------------------------------------------- #
def test_contentplus_router_routes():
    from app.api.contentplus import router

    paths = {getattr(r, "path", "") for r in router.routes}
    for expected in (
        "/contentplus/service-cycle",
        "/contentplus/service-due",
        "/contentplus/service-run",
        "/contentplus/clips",
        "/contentplus/clips/{job_id}",
        "/contentplus/clip-file/{job}/{name}",
        "/contentplus/gif",
        "/contentplus/gif-file/{slug}/{name}",
        "/contentplus/avatar-video",
        "/contentplus/outreach-variants",
    ):
        assert expected in paths, f"route missing: {expected}"
