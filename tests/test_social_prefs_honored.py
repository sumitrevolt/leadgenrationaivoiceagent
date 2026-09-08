"""Social Setup Wizard prefs honored by the daily draft-content loop.

These are draft/approval preferences only. They do not enable auto-posting or
bulk sending; SOCIAL_ENGINE remains separately gated. Runtime honor is behind
SOCIAL_PREFS_HONOR=1 (default OFF).
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest


@pytest.fixture()
def ac(tmp_path, monkeypatch):
    from app.marketing import auto_content
    from app.social_engine import client_config

    monkeypatch.setattr(auto_content, "_QUEUE_DIR", lambda: str(tmp_path / "content_queue"))
    monkeypatch.setattr(auto_content, "AUTO_SEED_SELF", False)
    monkeypatch.setattr(client_config, "_PATH", str(tmp_path / "social_config.jsonl"))
    monkeypatch.delenv("CONTENT_APPROVAL_AUTO", raising=False)
    monkeypatch.delenv("SOCIAL_PREFS_HONOR", raising=False)
    return auto_content


def _fake_store(clients):
    class FakeStore:
        def list_clients(self, status=None, product=None):
            return list(clients)

    return FakeStore()


def _valid_item(client_id: str) -> dict:
    return {
        "id": f"{client_id}-item",
        "client_id": client_id,
        "date": "2026-07-07",
        "type": "post",
        "title": "Daily draft",
        "caption": "Aaj ka special offer ready hai, details ke liye message karein.",
        "status": "draft",
    }


def test_cadence_due_truth_table(ac):
    mon = date(2026, 7, 6)
    tue = date(2026, 7, 7)
    wed = date(2026, 7, 8)
    fri = date(2026, 7, 10)
    sun = date(2026, 7, 12)

    assert ac._cadence_due("off", mon) is False
    assert ac._cadence_due("off", sun) is False
    assert ac._cadence_due("weekly", mon) is True
    assert ac._cadence_due("weekly", tue) is False
    assert ac._cadence_due("3x_week", mon) is True
    assert ac._cadence_due("3x_week", wed) is True
    assert ac._cadence_due("3x_week", fri) is True
    assert ac._cadence_due("3x_week", tue) is False
    assert ac._cadence_due("daily", sun) is True
    assert ac._cadence_due("", tue) is True
    assert ac._cadence_due("garbage", tue) is True


def test_daily_run_skips_cadence_off_but_keeps_unconfigured(ac, monkeypatch):
    from app.social_engine import client_config

    monkeypatch.setenv("SOCIAL_PREFS_HONOR", "1")
    clients = [
        {
            "id": "cli_off",
            "business_name": "Off",
            "niche": "salon",
            "plan": "starter",
            "status": "active",
        },
        {
            "id": "cli_plain",
            "business_name": "Plain",
            "niche": "salon",
            "plan": "starter",
            "status": "active",
        },
    ]
    monkeypatch.setattr(ac, "clients_store", _fake_store(clients))
    client_config.save("cli_off", cadence="off")

    processed: list[str] = []

    async def fake_generate(client, day=None):
        processed.append(str(client.get("id")))
        return [_valid_item(str(client.get("id")))]

    monkeypatch.setattr(ac, "generate_for_client", fake_generate)

    result = asyncio.run(ac.run_daily_content())
    assert "cli_off" not in processed
    assert "cli_plain" in processed
    assert result["clients"] == 1


def test_channels_stamped_on_items_when_configured(ac, monkeypatch):
    from app.social_engine import client_config

    monkeypatch.setenv("SOCIAL_PREFS_HONOR", "1")
    monkeypatch.setattr(ac, "post_generator", None)
    monkeypatch.setattr(ac, "posters", None)
    monkeypatch.setattr(ac, "festivals", None)
    client_config.save("cli_ch", channels=["instagram", "whatsapp"])

    items = asyncio.run(
        ac.generate_for_client(
            {"id": "cli_ch", "business_name": "Ch", "niche": "salon"}, day=date(2026, 7, 6)
        )
    )
    assert items
    assert all(item.get("channels") == ["instagram", "whatsapp"] for item in items)

    plain = asyncio.run(
        ac.generate_for_client(
            {"id": "cli_plain", "business_name": "Plain", "niche": "salon"}, day=date(2026, 7, 6)
        )
    )
    assert plain
    assert all("channels" not in item for item in plain)


def test_review_mode_submits_to_approval_queue(ac, monkeypatch):
    from app.marketing import content_approval
    from app.social_engine import client_config

    monkeypatch.setenv("SOCIAL_PREFS_HONOR", "1")
    clients = [
        {
            "id": "cli_rev",
            "business_name": "Rev",
            "niche": "salon",
            "plan": "starter",
            "status": "active",
        }
    ]
    monkeypatch.setattr(ac, "clients_store", _fake_store(clients))
    client_config.save("cli_rev", cadence="daily", approval_mode="review")

    async def fake_generate(client, day=None):
        return [_valid_item(str(client.get("id")))]

    submitted: list[str] = []
    monkeypatch.setattr(ac, "generate_for_client", fake_generate)
    monkeypatch.setattr(
        content_approval, "submit", lambda cid, content: submitted.append(cid) or {"ok": True}
    )

    result = asyncio.run(ac.run_daily_content())
    assert result["clients"] == 1
    assert submitted == ["cli_rev"]


def test_default_off_ignores_prefs(ac, monkeypatch):
    from app.social_engine import client_config

    clients = [
        {
            "id": "cli_off",
            "business_name": "Off",
            "niche": "salon",
            "plan": "starter",
            "status": "active",
        }
    ]
    monkeypatch.setattr(ac, "clients_store", _fake_store(clients))
    client_config.save("cli_off", cadence="off")

    processed: list[str] = []

    async def fake_generate(client, day=None):
        processed.append(str(client.get("id")))
        return [_valid_item(str(client.get("id")))]

    monkeypatch.setattr(ac, "generate_for_client", fake_generate)

    asyncio.run(ac.run_daily_content())
    assert processed == ["cli_off"]


def test_kill_switch_ignores_prefs(ac, monkeypatch):
    from app.social_engine import client_config

    clients = [
        {
            "id": "cli_off",
            "business_name": "Off",
            "niche": "salon",
            "plan": "starter",
            "status": "active",
        }
    ]
    monkeypatch.setattr(ac, "clients_store", _fake_store(clients))
    client_config.save("cli_off", cadence="off")
    monkeypatch.setenv("SOCIAL_PREFS_HONOR", "0")

    processed: list[str] = []

    async def fake_generate(client, day=None):
        processed.append(str(client.get("id")))
        return [_valid_item(str(client.get("id")))]

    monkeypatch.setattr(ac, "generate_for_client", fake_generate)

    asyncio.run(ac.run_daily_content())
    assert processed == ["cli_off"]
