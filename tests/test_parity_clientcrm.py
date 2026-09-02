"""Tests for Agent-C client-facing batch (customer_crm / product_catalog /
mini-site catalog section / payment_links).

Offline + isolated: koi network/DB/keys nahi. Stores tmp_path pe monkeypatch.
Async functions asyncio.run() se (pytest-asyncio ki zaroorat nahi).
"""

import asyncio


# --------------------------------------------------------------------------- #
# customer_crm — import alias mapping + occasions
# --------------------------------------------------------------------------- #
def test_customer_crm_import_alias_mapping(tmp_path, monkeypatch):
    from app.marketing import crm_lite, customer_crm

    monkeypatch.setattr(crm_lite, "_CRM_DIR", str(tmp_path / "crm"))

    res = customer_crm.import_rows(
        "client_x",
        rows=[
            {
                "Full Name": "Ramesh Kumar",
                "Mobile Number": "+91 98765 43210",
                "DOB": "1990-06-10",
                "Tags": "vip, regular",
            },
            {"Name": "Sita", "Phone": "08459012607", "Anniversary": "12/25"},
            {"Name": "NoPhone Guy"},  # phone nahi => drop
        ],
    )
    assert res["ok"] is True
    assert res["added"] == 2 and res["with_phone"] == 2

    rows = customer_crm.list_customers("client_x")
    assert len(rows) == 2
    by_name = {r["name"]: r for r in rows}
    assert by_name["Ramesh Kumar"]["phone"] == "9876543210"
    assert by_name["Ramesh Kumar"]["birthday"] == "06-10"
    assert "vip" in by_name["Ramesh Kumar"]["tags"]
    assert by_name["Sita"]["anniversary"] == "12-25"

    # tag filter
    assert len(customer_crm.list_customers("client_x", tag="vip")) == 1


def test_customer_crm_csv_import_and_dedupe(tmp_path, monkeypatch):
    from app.marketing import crm_lite, customer_crm

    monkeypatch.setattr(crm_lite, "_CRM_DIR", str(tmp_path / "crm"))

    csv_text = "Name,Mobile,Birthday\nAmit,9123456780,06-15\nAmit Dup,+919123456780,06-16\n"
    res = customer_crm.import_rows("c1", csv_text=csv_text)
    assert res["ok"] is True
    assert res["added"] == 1 and res["skipped"] == 1  # phone dedupe

    # empty input = graceful error dict (no raise)
    bad = customer_crm.import_rows("c1")
    assert bad["ok"] is False and "error" in bad


def test_todays_occasions(tmp_path, monkeypatch):
    from app.marketing import crm_lite, customer_crm

    monkeypatch.setattr(crm_lite, "_CRM_DIR", str(tmp_path / "crm"))
    monkeypatch.setattr(customer_crm, "_today_mmdd", lambda: "06-10")

    customer_crm.add_customer("c2", "Birthday Boy", "9000000001", birthday="06-10")
    customer_crm.add_customer("c2", "Anniv Couple", "9000000002", anniversary="06-10")
    customer_crm.add_customer("c2", "Nobody", "9000000003", birthday="01-01")

    occ = customer_crm.todays_occasions("c2")
    assert len(occ) == 2
    kinds = {o["occasion"] for o in occ}
    assert kinds == {"birthday", "anniversary"}


# --------------------------------------------------------------------------- #
# customer_crm — run_wishes drafts (ban-safe, NEVER auto-send)
# --------------------------------------------------------------------------- #
def test_run_wishes_creates_drafts_and_dedupes(tmp_path, monkeypatch):
    from app.marketing import customer_crm

    monkeypatch.setattr(customer_crm, "_DRAFTS_PATH", str(tmp_path / "wish_drafts.jsonl"))
    monkeypatch.setattr(customer_crm, "_today_mmdd", lambda: "06-10")

    async def _no_llm(*a, **k):
        return ""  # force template fallback (offline)

    monkeypatch.setattr(customer_crm, "_llm_wish", _no_llm)
    monkeypatch.setattr(
        customer_crm,
        "all_clients_todays_occasions",
        lambda: [
            {
                "client_id": "c9",
                "business_name": "Sharma Sweets",
                "niche": "sweet_shop",
                "occasions": [
                    {"name": "Pooja", "phone": "9876501234", "occasion": "birthday", "tags": []}
                ],
            }
        ],
    )

    res = asyncio.run(customer_crm.run_wishes())
    assert res["ok"] is True and res["drafts_created"] == 1
    d = res["drafts"][0]
    assert d["status"] == "draft"  # kabhi auto-send nahi
    assert "Sharma Sweets" in d["caption"] and "Pooja" in d["caption"]
    assert d["wa_link"].startswith("https://wa.me/919876501234?text=")
    assert isinstance(d["image_url"], str)

    # same day dobara run => dedupe, 0 naye drafts
    res2 = asyncio.run(customer_crm.run_wishes())
    assert res2["ok"] is True and res2["drafts_created"] == 0

    drafts = customer_crm.list_wish_drafts(date="06-10")
    assert len(drafts) == 1


def test_run_wishes_flag_gate(monkeypatch):
    from app.marketing import customer_crm

    monkeypatch.delenv("CUSTOMER_WISHES", raising=False)
    res = asyncio.run(customer_crm.run_wishes_if_enabled())
    assert res["ok"] is True and res.get("skipped") is True

    monkeypatch.setenv("CUSTOMER_WISHES", "1")
    monkeypatch.setattr(customer_crm, "all_clients_todays_occasions", lambda: [])
    res2 = asyncio.run(customer_crm.run_wishes_if_enabled())
    assert res2["ok"] is True and res2.get("skipped") is None


def test_wish_templates_hinglish():
    from app.marketing import customer_crm

    bday = customer_crm._template_wish("Raju", "Gupta Electronics", "birthday")
    anniv = customer_crm._template_wish("Raju", "Gupta Electronics", "anniversary")
    assert "Janamdin" in bday and "Gupta Electronics" in bday
    assert "salgirah" in anniv


# --------------------------------------------------------------------------- #
# product_catalog — CRUD + safety
# --------------------------------------------------------------------------- #
def test_product_catalog_crud(tmp_path, monkeypatch):
    from app.marketing import product_catalog as pc

    monkeypatch.setattr(pc, "_CAT_DIR", str(tmp_path / "catalogs"))

    r1 = pc.add_product(
        "sharma-solar", "Solar Panel 5kW", price_inr="₹1,25,000".replace(",", ""), desc="Best panel"
    )
    assert r1["ok"] is True
    pid = r1["product"]["id"]
    assert r1["product"]["price_inr"] == 125000.0

    r2 = pc.add_product(
        "sharma-solar", "Inverter", price_inr=15000, photo_url="javascript:alert(1)"
    )
    assert r2["ok"] is True
    assert r2["product"]["photo_url"] == ""  # unsafe URL blocked

    items = pc.list_products("sharma-solar")
    assert len(items) == 2

    # update: out of stock
    up = pc.update_product("sharma-solar", pid, in_stock=False, price_inr=120000)
    assert up["ok"] is True
    in_stock_only = pc.list_products("sharma-solar", include_out_of_stock=False)
    assert len(in_stock_only) == 1 and in_stock_only[0]["name"] == "Inverter"

    # delete
    dl = pc.delete_product("sharma-solar", pid)
    assert dl["ok"] is True and dl["total"] == 1
    assert pc.delete_product("sharma-solar", "nahi-hai")["ok"] is False

    # validation: empty name / bad slug = error dict (no raise)
    assert pc.add_product("sharma-solar", "")["ok"] is False
    assert pc.add_product("", "X")["ok"] is False

    # fmt_price
    assert pc.fmt_price(249) == "₹249"
    assert pc.fmt_price(249.5) == "₹249.50"
    assert pc.fmt_price("garbage") == ""


# --------------------------------------------------------------------------- #
# mini_site — catalog section (empty = ZERO change)
# --------------------------------------------------------------------------- #
def test_minisite_catalog_section(tmp_path, monkeypatch):
    from app.marketing import mini_site
    from app.marketing import product_catalog as pc

    monkeypatch.setattr(pc, "_CAT_DIR", str(tmp_path / "catalogs"))

    client = {
        "id": "c1",
        "business_name": "Sharma Solar",
        "slug": "sharma-solar",
        "niche": "solar",
        "city": "Pune",
        "phone": "9876543210",
    }

    # catalog empty => section absent, page normal
    html_before = mini_site.render_site(client)
    assert "Hamare Products" not in html_before
    assert "Enquiry / Booking" in html_before  # existing sections intact

    pc.add_product("sharma-solar", "Solar Panel 5kW", price_inr=125000, desc="High efficiency")
    html_after = mini_site.render_site(client)
    assert "Hamare Products" in html_after
    assert "Solar Panel 5kW" in html_after
    assert "WhatsApp pe order karein" in html_after
    assert "wa.me/919876543210?text=" in html_after
    assert "order%20karna%20hai" in html_after  # prefilled order message
    # existing sections still intact
    for marker in ("Enquiry / Booking", "Customer Reviews", "Appointment Book Karein"):
        assert marker in html_after


# --------------------------------------------------------------------------- #
# payment_links — Razorpay removed 2026-06-18; stub deleted 2026-07-19
# --------------------------------------------------------------------------- #
def test_payment_links_module_removed():
    import importlib

    import pytest

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.billing.payment_links")
