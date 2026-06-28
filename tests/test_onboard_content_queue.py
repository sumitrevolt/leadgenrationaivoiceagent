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


@pytest.mark.asyncio
async def test_seed_client_content_appends_to_queue(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.marketing import auto_content

    monkeypatch.setattr(auto_content, "_QUEUE_DIR", str(tmp_path / "queue"))

    async def _gen(client: dict, day: Any = None) -> list[dict]:
        return [_fake_item(str(client.get("id", "c1")))]

    monkeypatch.setattr(auto_content, "generate_for_client", _gen)

    added = await auto_content.seed_client_content({"id": "c1", "business_name": "Sharma Solar"})
    assert added == 1

    # portal_content reads exactly this list_queue
    q = auto_content.list_queue("c1", limit=10)
    assert len(q) == 1
    assert q[0]["type"] == "post"


@pytest.mark.asyncio
async def test_seed_client_content_is_idempotent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """date+type dedupe → re-run (or daily job) does NOT double the queue."""
    from app.marketing import auto_content

    monkeypatch.setattr(auto_content, "_QUEUE_DIR", str(tmp_path / "queue"))

    async def _gen(client: dict, day: Any = None) -> list[dict]:
        return [_fake_item(str(client.get("id", "c1")))]

    monkeypatch.setattr(auto_content, "generate_for_client", _gen)

    client = {"id": "c1", "business_name": "Sharma Solar"}
    first = await auto_content.seed_client_content(client)
    second = await auto_content.seed_client_content(client)
    assert first == 1
    assert second == 0  # same date+type → deduped, not re-added
    assert len(auto_content.list_queue("c1", limit=10)) == 1


@pytest.mark.asyncio
async def test_auto_onboard_populates_content_queue(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The actual fix: after onboarding, the customer's queue is non-empty."""
    from app.marketing import auto_content, clients_store, onboarding

    monkeypatch.setattr(auto_content, "_QUEUE_DIR", str(tmp_path / "queue"))

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
    assert report["steps"]["content_queue"] == 1

    # The customer portal would now see this content (was empty before the fix)
    assert len(auto_content.list_queue("c9", limit=10)) == 1
