from __future__ import annotations

import asyncio
import json
import os

from app.marketing import client_report, clients_store, delivery_ledger

MONTH = "2026-07"
OTHER = "2026-06"


def _redirect(monkeypatch, tmp_path):
    monkeypatch.setattr(delivery_ledger, "_LEDGER_DIR", lambda: str(tmp_path / "delivery_ledger"))
    monkeypatch.setattr(
        delivery_ledger, "_CONTENT_QUEUE_DIR", lambda: str(tmp_path / "content_queue")
    )
    monkeypatch.setattr(
        clients_store, "_CLIENTS_FILE", lambda: str(tmp_path / "marketing_clients.jsonl")
    )
    monkeypatch.setattr(client_report, "_OUT_DIR", str(tmp_path / "client_reports"))


def _seed_events(cid: str, events: list[tuple[str, str]]):
    path = delivery_ledger._ledger_path(cid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for at, event in events:
            f.write(json.dumps({"at": at, "client_id": cid, "event": event}) + "\n")


def _seed_client(cid: str, **fields):
    rec = {
        "id": cid,
        "business_name": fields.pop("business_name", "Test Biz"),
        "slug": cid,
        **fields,
    }
    path = clients_store._CLIENTS_FILE()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def test_collect_delivery_counts_and_filters_month(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    _seed_events(
        "c1",
        [
            (f"{MONTH}-02T09:00:00+00:00", "post_draft_created"),
            (f"{MONTH}-03T09:00:00+00:00", "post_approved"),
            (f"{MONTH}-04T09:00:00+00:00", "post_published"),
            (f"{MONTH}-05T09:00:00+00:00", "post_failed"),
            (f"{MONTH}-06T09:00:00+00:00", "lead_captured"),
            (f"{MONTH}-07T09:00:00+00:00", "followup_sent"),
            (f"{OTHER}-07T09:00:00+00:00", "post_published"),
            (f"{MONTH}-08T09:00:00+00:00", "weekly_report_generated"),
        ],
    )

    d = client_report.collect_delivery("c1", MONTH)
    assert d["posts_created"] == 1
    assert d["posts_approved"] == 1
    assert d["posts_published"] == 1
    assert d["posts_failed"] == 1
    assert d["leads_captured"] == 1
    assert d["followups_sent"] == 1
    assert "1 naye posts bane" in d["summary_hi"]


def test_next_actions_rules():
    d = {"posts_created": 5, "posts_approved": 2, "posts_failed": 1}
    actions = client_report._next_actions(d, {"socials": {}})
    assert any("theek kar rahi" in a for a in actions)
    assert any(a.startswith("3 post approval") for a in actions)
    assert any("profile link" in a for a in actions)

    good = {"posts_created": 4, "posts_approved": 4, "posts_published": 4, "posts_failed": 0}
    assert client_report._next_actions(good, {"socials": {"instagram": "@x"}})[0].startswith(
        "Sab set"
    )


def test_build_report_adds_delivery_section_and_keeps_event(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    _seed_client("cbuild", business_name="Jiya Makeover", socials={"instagram": "@jiya"})
    _seed_events(
        "cbuild",
        [
            (f"{MONTH}-02T09:00:00+00:00", "post_draft_created"),
            (f"{MONTH}-05T09:00:00+00:00", "post_published"),
            (f"{MONTH}-07T09:00:00+00:00", "lead_captured"),
        ],
    )
    logged = []
    monkeypatch.setattr(
        delivery_ledger,
        "log_event",
        lambda cid, event, **kw: logged.append((cid, event, kw)) or True,
    )

    result = asyncio.run(client_report.build_report("cbuild", month=MONTH))
    assert result["ok"] is True
    assert set(result) >= {"ok", "path", "stats", "delivery", "next_actions_hi", "emailed"}
    assert result["delivery"]["posts_published"] == 1
    assert result["delivery"]["leads_captured"] == 1
    assert isinstance(result["next_actions_hi"], list)
    html = open(result["path"], encoding="utf-8").read()
    assert "AI team ne is mahine kya kiya" in html
    assert "Agle steps" in html
    assert (
        "cbuild",
        "weekly_report_generated",
        {"detail": MONTH, "key": f"report:cbuild:{MONTH}"},
    ) in logged


def test_build_report_delivery_failure_keeps_ok_true(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    _seed_client("csafe", socials={"instagram": "@x"})

    def _boom(*args, **kwargs):
        raise RuntimeError("ledger down")

    monkeypatch.setattr(delivery_ledger, "timeline", _boom)
    result = asyncio.run(client_report.build_report("csafe", month=MONTH))
    assert result["ok"] is True
    assert result["delivery"]["posts_created"] == 0
    assert result["delivery"]["summary_hi"]
