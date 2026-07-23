"""Unit tests for crm_lite.py — customer store, dedupe & wishes generation."""

import pytest

from app.marketing import crm_lite


def test_digits10_normalization():
    assert crm_lite._digits10("+919876543210") == "9876543210"
    assert crm_lite._digits10("09876543210") == "9876543210"
    assert crm_lite._digits10("9876543210") == "9876543210"
    assert crm_lite._digits10("12345") == ""  # incomplete


def test_mmdd_normalization():
    assert crm_lite._mmdd("1995-06-15") == "06-15"
    assert crm_lite._mmdd("06-15") == "06-15"
    assert crm_lite._mmdd("invalid") == ""


def test_add_and_list_customers(tmp_path, monkeypatch):
    monkeypatch.setattr(crm_lite, "_CRM_DIR", str(tmp_path))
    client_id = "test_client_001"

    rows = [
        {"name": "Rahul Sharma", "phone": "+919876543210", "tags": ["vip", "salon"]},
        {"name": "Priya Patel", "phone": "09876543211", "tags": ["general"]},
        {"name": "Duplicate Rahul", "phone": "9876543210", "tags": ["duplicate"]},
    ]

    res = crm_lite.add_customers(client_id, rows)
    assert res["added"] == 2
    assert res["skipped"] == 1

    all_cust = crm_lite.list_customers(client_id)
    assert len(all_cust) == 2

    vip_cust = crm_lite.list_customers(client_id, tag="vip")
    assert len(vip_cust) == 1
    assert vip_cust[0]["name"] == "Rahul Sharma"


@pytest.mark.asyncio
async def test_todays_wishes(tmp_path, monkeypatch):
    monkeypatch.setattr(crm_lite, "_CRM_DIR", str(tmp_path))
    client_id = "test_wishes_client"
    today_str = crm_lite._today_mmdd()

    rows = [
        {"name": "Amit Kumar", "phone": "9876543212", "birthday": f"1990-{today_str}"},
        {"name": "Sita V", "phone": "9876543213", "anniversary": f"2018-{today_str}"},
    ]

    crm_lite.add_customers(client_id, rows)
    out = await crm_lite.todays_wishes(client_id, business_name="Apex Salon")
    assert out["count"] == 2
    wishes = out["wishes"]
    assert len(wishes) == 2
    assert any(w["occasion"] == "birthday" and "Amit Kumar" in w["message"] for w in wishes)
    assert any(w["occasion"] == "anniversary" and "Sita V" in w["message"] for w in wishes)
