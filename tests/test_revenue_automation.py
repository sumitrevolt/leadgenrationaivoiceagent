"""Tests — revenue automation batch (dunning, client_health, lifecycle_nurture,
revenue_digest). Sab sync + asyncio.run pattern (project convention), tmp stores
monkeypatch se. DB/network nahi chahiye — defensive paths hi test hote.
"""

from __future__ import annotations

import asyncio
import os


# ----------------------------- dunning ----------------------------- #
def test_dunning_messages_pure():
    from app.billing import dunning

    for key in ("failed_now", "reminder", "urgent", "winback"):
        m = dunning.build_message(key, "Sharma Solar", 999)
        assert m["subject"] and "Sharma Solar" in m["subject"]
        assert "leadsgenai.in" in m["body"]
        assert m["wa_text"]


def test_dunning_case_open_dedupe_recover(tmp_path, monkeypatch):
    from app.billing import dunning

    monkeypatch.setattr(dunning, "_CASES", str(tmp_path / "cases.jsonl"))
    monkeypatch.setattr(dunning, "_RUNS", str(tmp_path / "runs.jsonl"))
    monkeypatch.delenv("DUNNING_ENGINE", raising=False)

    res = asyncio.run(dunning.on_payment_failed("c123", amount=999, gateway="razorpay"))
    assert res["ok"] is True and res["case"]["status"] == "open"
    # dedupe: same client dobara -> wahi case
    res2 = asyncio.run(dunning.on_payment_failed("c123"))
    assert res2.get("dedupe") is True
    # gated off -> run_due no-op
    assert asyncio.run(dunning.run_due()) == {"enabled": False}
    # recovered close
    assert dunning.mark_recovered("c123") is True
    st = dunning.stats()
    assert st["recovered"] == 1 and st["open"] == 0
    # missing client_id -> graceful
    bad = asyncio.run(dunning.on_payment_failed(""))
    assert bad["ok"] is False


def test_dunning_run_due_touches(tmp_path, monkeypatch):
    from app.billing import dunning

    monkeypatch.setattr(dunning, "_CASES", str(tmp_path / "cases.jsonl"))
    monkeypatch.setattr(dunning, "_RUNS", str(tmp_path / "runs.jsonl"))
    monkeypatch.setenv("DUNNING_ENGINE", "1")

    asyncio.run(dunning.on_payment_failed("c9", amount=2499))
    # backdate case 8 din -> day-3 + day-7 touches due (day-0 already done)
    rows = dunning._read(dunning._CASES)
    from datetime import datetime, timedelta, timezone

    rows[0]["created_at"] = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    dunning._write_all(dunning._CASES, rows)
    out = asyncio.run(dunning.run_due())
    assert out["enabled"] is True
    assert (
        out["touches"] >= 2
    )  # reminder + urgent (email send fail ho sakta — draft phir bhi recorded)
    runs = dunning._read(dunning._RUNS)
    keys = {r["touch"] for r in runs}
    assert {"failed_now", "reminder", "urgent"} <= keys


# ----------------------------- client_health ----------------------------- #
def test_client_health_score_bands():
    from app.platform import client_health

    good = client_health.score_client(
        {"payment_status": "active", "leads_30d": 5, "pack_age_days": 2, "status": "active"}
    )
    assert good["band"] == "green" and good["score"] >= 70

    risky = client_health.score_client(
        {"payment_status": "past_due", "leads_30d": 0, "pack_age_days": None, "status": "active"}
    )
    assert risky["band"] == "red" and risky["reasons"]
    assert "save-call" in risky["action"] or "URGENT" in risky["action"]

    mid = client_health.score_client(
        {"payment_status": "active", "leads_30d": 0, "pack_age_days": 30, "status": "active"}
    )
    assert mid["band"] in ("yellow", "green")


def test_client_health_report_defensive():
    from app.platform import client_health

    # DB/clients na ho to bhi kabhi raise nahi — list lautata
    rep = asyncio.run(client_health.health_report())
    assert isinstance(rep, list)


# ----------------------------- lifecycle_nurture ----------------------------- #
def test_lifecycle_enroll_dedupe_and_messages(tmp_path, monkeypatch):
    from app.marketing import lifecycle_nurture as lc

    monkeypatch.setattr(lc, "_STORE", str(tmp_path / "lc.jsonl"))
    monkeypatch.setattr(lc, "_RUNS", str(tmp_path / "lc_runs.jsonl"))
    monkeypatch.delenv("LIFECYCLE_NURTURE", raising=False)

    r = lc.enroll("test@example.com", "Sharma Solar", "c1", "growth")
    assert r["ok"] is True and r["rec"]["step_idx"] == 0
    r2 = lc.enroll("TEST@example.com", "Dup", "c1")
    assert r2.get("dedupe") is True
    assert lc.enroll("bad-email", "X")["ok"] is False
    # gated off -> no-op
    assert asyncio.run(lc.run_due()) == {"enabled": False}
    # messages pure
    for step in lc.STEPS:
        m = lc.build_message(step["key"], "Sharma Solar")
        assert m["subject"] and "leadsgenai.in" in m["body"]


def test_lifecycle_run_due_advances(tmp_path, monkeypatch):
    from app.marketing import lifecycle_nurture as lc

    monkeypatch.setattr(lc, "_STORE", str(tmp_path / "lc.jsonl"))
    monkeypatch.setattr(lc, "_RUNS", str(tmp_path / "lc_runs.jsonl"))
    monkeypatch.setenv("LIFECYCLE_NURTURE", "1")

    lc.enroll("a@b.co", "Test Biz", "")  # no client_id -> paid-check False
    out = asyncio.run(lc.run_due())
    assert out["enabled"] is True and out["sent"] == 1  # day-0 welcome due
    rows = lc._read(lc._STORE)
    assert rows[0]["step_idx"] == 1
    st = lc.stats()
    assert st["active"] == 1 and st["total"] == 1


# ----------------------------- revenue_digest ----------------------------- #
def test_revenue_digest_compose_and_gate(tmp_path, monkeypatch):
    from app.platform import revenue_digest as rd

    subject, body = rd.compose(
        {
            "mrr": 8497,
            "subscriptions": {"active": 3, "trial": 2, "past_due": 1},
            "dunning": {"open": 1, "recovered": 2, "lapsed": 0},
            "lifecycle": {"active": 4, "converted": 1, "finished": 0},
            "hot_leads": 7,
            "health": {"clients": 5, "red": 1, "yellow": 2},
        },
        "2026-W24",
    )
    assert "8497" in subject and "2026-W24" in subject
    assert "Dunning" in body and "Nurture" in body
    # gated off -> maybe_run_weekly no-op
    monkeypatch.setattr(rd, "_LOG", str(tmp_path / "digest.jsonl"))
    monkeypatch.delenv("REVENUE_DIGEST", raising=False)
    assert asyncio.run(rd.maybe_run_weekly()) == {"enabled": False}
    # week dedupe helpers
    wk = rd._week_key()
    assert not rd._already_sent(wk)
    rd._mark_sent(wk)
    assert rd._already_sent(wk)


def test_revenue_digest_run_force_defensive(tmp_path, monkeypatch):
    from app.platform import revenue_digest as rd

    monkeypatch.setattr(rd, "_LOG", str(tmp_path / "digest.jsonl"))
    monkeypatch.delenv("NOTIFY_EMAIL", raising=False)
    out = asyncio.run(rd.run(force=True))
    # DB/email na ho to bhi structure sahi + kabhi raise nahi
    assert out.get("week") and out.get("sent") is False
    assert "subject" in out


# ----------------------------- imports/wiring ----------------------------- #
def test_growth_router_has_revenue_routes():
    from app.api.growth import router
    from app.utils.route_inspection import iter_effective_routes

    paths = {getattr(r, "path", "") for r in iter_effective_routes(router.routes)}
    for p in (
        "/growth/revenue/dunning/run",
        "/growth/revenue/health/clients",
        "/growth/revenue/lifecycle/run",
        "/growth/revenue/digest/run",
    ):
        assert p in paths, f"route missing: {p}"
