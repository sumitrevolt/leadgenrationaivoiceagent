"""WhatsApp onboarding-interview: clients without a website get a business-info
request via WhatsApp right after onboarding; the reply becomes the KB source
instead of a website scrape.

Pins the contract:
- `auto_onboard` sets `awaiting_kb_interview=True` only when the website-KB-seed
  step found nothing (kb_chunks == 0) — clients WITH a seeded website are not
  bothered with the question.
- `try_capture_onboarding_reply` matches the inbound WhatsApp sender to the
  awaiting client by phone (last-10-digit match, formatting-agnostic), feeds the
  reply into that client's KB namespace, and clears the flag — idempotent (a
  second reply / unrelated sender is not mis-attributed).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


@pytest.mark.asyncio
async def test_auto_onboard_sets_awaiting_flag_when_no_website(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.marketing import auto_content, clients_store, onboarding

    monkeypatch.setattr(auto_content, "_QUEUE_DIR", lambda: str(tmp_path / "queue"))
    clients_store._CLIENTS_FILE = lambda: str(tmp_path / "clients.jsonl")

    client = clients_store.add_client(
        business_name="No Website Biz", niche="general", phone="9812345678"
    )
    cid = client["id"]

    async def _no_kb(cid: str, website: str) -> dict:
        return {"kb_chunks": 0}

    async def _no_pack(client: dict) -> dict:
        return {}

    async def _no_wa(client: dict, kb_seeded: bool) -> dict:
        return {"sent": False}

    monkeypatch.setattr(onboarding, "_seed_kb_from_website", _no_kb)
    monkeypatch.setattr(onboarding, "_first_content_pack", _no_pack)
    monkeypatch.setattr(onboarding, "_send_welcome_whatsapp", _no_wa)

    report = await onboarding.auto_onboard(cid)
    assert report.get("ok") is True

    after = clients_store.get_client(cid)
    assert after.get("awaiting_kb_interview") is True


@pytest.mark.asyncio
async def test_auto_onboard_skips_flag_when_website_seeded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.marketing import auto_content, clients_store, onboarding

    monkeypatch.setattr(auto_content, "_QUEUE_DIR", lambda: str(tmp_path / "queue"))
    clients_store._CLIENTS_FILE = lambda: str(tmp_path / "clients.jsonl")

    client = clients_store.add_client(
        business_name="Has Website Biz", niche="general", phone="9812345679"
    )
    cid = client["id"]

    async def _has_kb(cid: str, website: str) -> dict:
        return {"kb_chunks": 5}

    async def _no_pack(client: dict) -> dict:
        return {}

    async def _no_wa(client: dict, kb_seeded: bool) -> dict:
        return {"sent": True}

    monkeypatch.setattr(onboarding, "_seed_kb_from_website", _has_kb)
    monkeypatch.setattr(onboarding, "_first_content_pack", _no_pack)
    monkeypatch.setattr(onboarding, "_send_welcome_whatsapp", _no_wa)

    report = await onboarding.auto_onboard(cid)
    assert report.get("ok") is True

    after = clients_store.get_client(cid)
    assert not after.get("awaiting_kb_interview")


@pytest.mark.asyncio
async def test_try_capture_onboarding_reply_matches_by_phone_and_clears_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.marketing import clients_store, onboarding

    clients_store._CLIENTS_FILE = lambda: str(tmp_path / "clients.jsonl")

    client = clients_store.add_client(
        business_name="Pending Interview Biz", niche="general", phone="9812345680"
    )
    cid = client["id"]
    clients_store.update_client(cid, awaiting_kb_interview=True)

    kb_calls: list[dict[str, Any]] = []

    class _FakeKB:
        def add_documents(self, docs, source="", namespace=""):
            kb_calls.append({"docs": docs, "source": source, "namespace": namespace})
            return len(docs)

    monkeypatch.setattr("app.voice_agent.knowledge_base.get_knowledge_base", lambda: _FakeKB())

    # WhatsApp sender formats numbers with a country code / spaces — must still match.
    handled = await onboarding.try_capture_onboarding_reply(
        "+91 98123 45680", "Hum salon services dete hain, Nagpur me, USP: best price"
    )
    assert handled is True
    assert len(kb_calls) == 1
    assert kb_calls[0]["source"] == "whatsapp:onboarding_interview"

    after = clients_store.get_client(cid)
    assert not after.get("awaiting_kb_interview")


@pytest.mark.asyncio
async def test_try_capture_onboarding_reply_ignores_unknown_sender(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.marketing import clients_store, onboarding

    clients_store._CLIENTS_FILE = lambda: str(tmp_path / "clients.jsonl")
    client = clients_store.add_client(
        business_name="Someone Else Biz", niche="general", phone="9812345681"
    )
    clients_store.update_client(client["id"], awaiting_kb_interview=True)

    handled = await onboarding.try_capture_onboarding_reply(
        "+91 90000 00000", "random unrelated message"
    )
    assert handled is False

    # Flag untouched — a stray message from a different number must not clear it.
    after = clients_store.get_client(client["id"])
    assert after.get("awaiting_kb_interview") is True


@pytest.mark.asyncio
async def test_try_capture_onboarding_reply_ignores_client_not_awaiting(
    tmp_path: Path,
) -> None:
    from app.marketing import clients_store, onboarding

    clients_store._CLIENTS_FILE = lambda: str(tmp_path / "clients.jsonl")
    clients_store.add_client(
        business_name="Already Seeded Biz", niche="general", phone="9812345682"
    )
    # no awaiting_kb_interview set -> this reply should not be captured as interview data
    handled = await onboarding.try_capture_onboarding_reply(
        "9812345682", "just chatting, not an interview answer"
    )
    assert handled is False
