"""clients_store delete_client + dedupe_clients (admin cleanup) — pure-python."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.marketing import clients_store as cs


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cs, "_CLIENTS_FILE", lambda: str(tmp_path / "marketing_clients.jsonl"))


def test_delete_client_removes_one():
    a = cs.add_client("Acme", "gym", phone="9990001111")
    cs.add_client("Beta", "spa", phone="9990002222")
    assert len(cs.list_clients()) == 2
    assert cs.delete_client(a["id"]) is True
    rows = cs.list_clients()
    assert len(rows) == 1 and rows[0]["business_name"] == "Beta"
    # idempotent / unknown id
    assert cs.delete_client(a["id"]) is False
    assert cs.delete_client("") is False


def test_dedupe_by_phone_keeps_newest():
    # add_client dedupes on creation by phone, so write raw dupes directly.
    cs._append(
        {
            "id": "1",
            "business_name": "Dup",
            "phone": "9876543210",
            "created_at": "2026-06-16T00:00:00+00:00",
        }
    )
    cs._append(
        {
            "id": "2",
            "business_name": "Dup",
            "phone": "9876543210",
            "created_at": "2026-06-18T00:00:00+00:00",
        }
    )
    cs._append(
        {
            "id": "3",
            "business_name": "Other",
            "phone": "9876500000",
            "created_at": "2026-06-17T00:00:00+00:00",
        }
    )
    res = cs.dedupe_clients()
    assert res["removed"] == 1 and res["kept"] == 2
    ids = {r["id"] for r in cs.list_clients()}
    assert ids == {"2", "3"}  # newest of the phone-dup kept


def test_dedupe_distinct_phones_untouched():
    # 3 same-business but DIFFERENT phones = NOT dupes (e.g. the Sharma Solar trio)
    cs._append(
        {
            "id": "a",
            "business_name": "Sharma Solar",
            "phone": "9876543210",
            "created_at": "2026-06-16T01:00:00+00:00",
        }
    )
    cs._append(
        {
            "id": "b",
            "business_name": "Sharma Solar",
            "phone": "9876543211",
            "created_at": "2026-06-16T02:00:00+00:00",
        }
    )
    cs._append(
        {
            "id": "c",
            "business_name": "Sharma Solar",
            "phone": "9876543299",
            "created_at": "2026-06-16T03:00:00+00:00",
        }
    )
    res = cs.dedupe_clients()
    assert (
        res["removed"] == 0 and res["kept"] == 3
    )  # distinct phones → kept (use delete for test data)


def test_dedupe_empty_safe():
    assert cs.dedupe_clients() == {"removed": 0, "kept": 0}
