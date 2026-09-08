"""Day-1 value fix: onboarding MUST populate the customer-visible content queue.

Before this fix `auto_onboard` only wrote an HTML pack (data/client_packs/*.html)
which the customer portal never reads — `portal_content` reads ONLY from
`auto_content.list_queue` (data/content_queue/<cid>.jsonl). So a freshly-activated
customer logged in to an EMPTY queue until the 07:00 daily sweep ran.

These tests pin the contract:
- `seed_client_content` generates + appends today's items (idempotent via date+type dedupe)
- `auto_onboard` calls it so `list_queue` is non-empty right after onboarding
Network/LLM are monkeypatched out — this tests the WIRING (the actual bug), not generation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


def _fake_item(client_id: str = "c1") -> dict[str, Any]:
    return {
        "id": "itm-1",
        "client_id": client_id,
        "date": "2026-06-28",
        "type": "post",
        "title": "Welcome Post",
        "caption": "Aaj ka post ready hai!",
        "hashtags": ["#local"],
        "status": "draft",
        "created_at": "2026-06-28T00:00:00Z",
    }


def _stub_packet_deps(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    from app.marketing import content_approval, delivery_ledger, whatsapp_pack

    async def _fake_pack(**kw: Any) -> dict:
        return {"broadcast": ["Namaste! Special offer - abhi reply karein."]}

    submitted: list[dict] = []
    monkeypatch.setattr(whatsapp_pack, "broadcast_pack", _fake_pack)
    monkeypatch.setattr(
        content_approval,
        "submit",
        lambda cid, content: submitted.append({"cid": cid, "content": content}) or {"ok": True},
    )
    monkeypatch.setattr(delivery_ledger, "log_event", lambda *a, **k: True)
    try:
        from app.voice_agent import free_ai

        async def _fake_chat(*a: Any, **kw: Any):
            return "Title: Referral\nSuggestion: dosto ko batao", None

        monkeypatch.setattr(free_ai, "chat", _fake_chat)
    except Exception:
        pass
    return submitted


def _disable_extended_packs(monkeypatch: pytest.MonkeyPatch, auto_content: Any) -> None:
    """Keep this Day-1 queue contract scoped to its three primary items."""

    async def _none(_client: dict[str, Any]) -> int:
        return 0

    monkeypatch.setattr(auto_content, "generate_gbp_pack", _none)
    monkeypatch.setattr(auto_content, "generate_review_reply_pack", _none)
    monkeypatch.setattr(auto_content, "generate_poster_pack", _none)


@pytest.mark.asyncio
async def test_seed_client_content_appends_to_queue(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.marketing import auto_content

    monkeypatch.setattr(auto_content, "_QUEUE_DIR", lambda: str(tmp_path / "queue"))
    _disable_extended_packs(monkeypatch, auto_content)
    submitted = _stub_packet_deps(monkeypatch)

    async def _gen(client: dict, day: Any = None) -> list[dict]:
        return [_fake_item(str(client.get("id", "c1")))]

    monkeypatch.setattr(auto_content, "generate_for_client", _gen)

    added = await auto_content.seed_client_content({"id": "c1", "business_name": "Sharma Solar"})
    assert added == 3

    # portal_content reads exactly this list_queue
    q = auto_content.list_queue("c1", limit=20)
    assert len(q) == 3
    assert {it["type"] for it in q} == {"post", "whatsapp", "campaign"}
    assert len(submitted) >= 3


@pytest.mark.asyncio
async def test_seed_client_content_is_idempotent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """date+type dedupe → re-run (or daily job) does NOT double the queue."""
    from app.marketing import auto_content

    monkeypatch.setattr(auto_content, "_QUEUE_DIR", lambda: str(tmp_path / "queue"))
    _disable_extended_packs(monkeypatch, auto_content)
    _stub_packet_deps(monkeypatch)

    async def _gen(client: dict, day: Any = None) -> list[dict]:
        return [_fake_item(str(client.get("id", "c1")))]

    monkeypatch.setattr(auto_content, "generate_for_client", _gen)

    client = {"id": "c1", "business_name": "Sharma Solar"}
    first = await auto_content.seed_client_content(client)
    second = await auto_content.seed_client_content(client)
    assert first == 3
    assert second == 0  # same date+type → deduped, not re-added
    assert len(auto_content.list_queue("c1", limit=20)) == 3


@pytest.mark.asyncio
async def test_auto_onboard_populates_content_queue(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The actual fix: after onboarding, the customer's queue is non-empty."""
    from app.marketing import auto_content, clients_store, onboarding

    monkeypatch.setattr(auto_content, "_QUEUE_DIR", lambda: str(tmp_path / "queue"))
    _disable_extended_packs(monkeypatch, auto_content)
    _stub_packet_deps(monkeypatch)

    fake_client = {"id": "c9", "business_name": "Verma Tiffin", "niche": "tiffin", "phone": "9"}
    monkeypatch.setattr(clients_store, "get_client", lambda cid: fake_client)
    monkeypatch.setattr(clients_store, "update_client", lambda *a, **k: None)

    # Heavy/network steps stubbed — we only assert the queue wiring.
    async def _no_kb(cid: str, website: str) -> dict:
        return {"kb_chunks": 0}

    async def _no_pack(client: dict) -> dict:
        return {}

    async def _gen(client: dict, day: Any = None) -> list[dict]:
        return [_fake_item(str(client.get("id", "c9")))]

    monkeypatch.setattr(onboarding, "_seed_kb_from_website", _no_kb)
    monkeypatch.setattr(onboarding, "_first_content_pack", _no_pack)
    monkeypatch.setattr(auto_content, "generate_for_client", _gen)

    report = await onboarding.auto_onboard("c9")
    assert report.get("ok") is True
    assert report["steps"]["content_queue"] == 3

    # The customer portal would now see this content (was empty before the fix)
    assert len(auto_content.list_queue("c9", limit=20)) == 3
