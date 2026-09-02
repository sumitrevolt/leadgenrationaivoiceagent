"""Accountant-safe invoice void/correction contracts (2026-07-18 billing containment).

Background: prod `data/invoices.jsonl` me 12 synthetic invoices (INV/2026-27/0002..0013)
ghus gaye — VPS pe targeted pytest run ne real store me likh diya (tests `upi_payments._STORE`
patch karte the par `gst_invoice._STORE` nahi). Rule-46 sequential numbering ki wajah se
DELETE forbidden — correction = append-only VOID marker jo original record ko preserve
karta hai, number consumed hi rehta hai, aur reporting/dedupe voided ko exclude karti hai.
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture()
def inv(monkeypatch, tmp_path):
    """gst_invoice with an isolated store (module-attr patch, prod file untouched)."""
    from app.billing import gst_invoice as mod

    monkeypatch.setattr(mod, "_STORE", lambda: str(tmp_path / "invoices.jsonl"))
    monkeypatch.delenv("GST_GSTIN", raising=False)
    monkeypatch.delenv("AUTO_INVOICE", raising=False)
    return mod


def _mk(inv, cid="c1", plan="starter", amount=1999, ref=""):
    rec = inv.create_invoice(cid, plan, amount_inr=amount, payment_ref=ref)
    assert rec and rec.get("number")
    return rec


def test_void_marks_invoice_and_preserves_original_row(inv):
    rec = _mk(inv, ref="TXN1")
    out = inv.void_invoice(rec["number"], reason="synthetic test data", by="admin")
    assert out["ok"] is True
    assert out["number"] == rec["number"]
    # Original invoice line is still physically present (append-only, no rewrite).
    raw = open(inv._STORE(), encoding="utf-8").read()
    assert rec["number"] in raw
    lines = [json.loads(x) for x in raw.splitlines() if x.strip()]
    assert any(r.get("kind") == "void" and r.get("voids") == rec["number"] for r in lines)


def test_void_unknown_number_fails_soft(inv):
    out = inv.void_invoice("INV/2026-27/9999", reason="x")
    assert out.get("ok") is not True
    assert "not found" in str(out.get("error", ""))


def test_double_void_is_idempotent(inv):
    rec = _mk(inv)
    first = inv.void_invoice(rec["number"], reason="dup1")
    second = inv.void_invoice(rec["number"], reason="dup2")
    assert first["ok"] is True and second["ok"] is True
    assert second.get("deduped") is True
    # Only ONE void marker in the store.
    lines = [
        json.loads(x) for x in open(inv._STORE(), encoding="utf-8").read().splitlines() if x.strip()
    ]
    assert sum(1 for r in lines if r.get("kind") == "void") == 1


def test_list_invoices_annotates_voided_and_hides_markers(inv):
    a = _mk(inv, cid="keep")
    b = _mk(inv, cid="kill")
    inv.void_invoice(b["number"], reason="test junk")
    rows = inv.list_invoices(50)
    # Void markers themselves are NOT invoice rows.
    assert all(r.get("kind") != "void" for r in rows)
    by_num = {r["number"]: r for r in rows}
    assert by_num[a["number"]].get("voided") is not True
    assert by_num[b["number"]]["voided"] is True
    assert by_num[b["number"]]["void_reason"] == "test junk"


def test_get_by_number_carries_voided_flag(inv):
    rec = _mk(inv)
    inv.void_invoice(rec["number"], reason="r")
    got = inv.get_by_number(rec["number"])
    assert got["voided"] is True


def test_stats_excludes_voided_gross(inv):
    _mk(inv, cid="real", amount=1999)
    junk = _mk(inv, cid="junk", amount=5999)
    inv.void_invoice(junk["number"], reason="synthetic")
    s = inv.stats()
    assert s["fy_gross_inr"] == 1999.0
    assert s["fy_voided_count"] == 1
    assert s["fy_voided_gross_inr"] == 5999.0
    # Total invoice count remains honest (both numbers consumed).
    assert s["fy_count"] == 2


def test_numbering_continues_after_void_no_reuse(inv):
    a = _mk(inv)
    inv.void_invoice(a["number"], reason="x")
    b = _mk(inv, cid="c2")
    # Voided number is consumed — next invoice gets a NEW sequential number.
    assert b["number"] != a["number"]
    na = int(a["number"].rsplit("/", 1)[-1])
    nb = int(b["number"].rsplit("/", 1)[-1])
    assert nb == na + 1


@pytest.mark.asyncio
async def test_voided_payment_ref_can_be_reinvoiced(inv):
    """Dedupe must ignore voided invoices — a corrected reissue for the SAME
    payment_ref must not be blocked by the voided original."""
    rec = _mk(inv, cid="c1", ref="upi:c1:starter:2026-07")
    inv.void_invoice(rec["number"], reason="wrong amount")
    out = await inv.on_payment_success("c1", "starter", payment_ref="upi:c1:starter:2026-07")
    assert out.get("deduped") is not True
    assert out.get("number") and out["number"] != rec["number"]


def test_admin_void_route_wired(client, monkeypatch, tmp_path):
    """POST /api/growth/revenue/invoice-void — admin route exists and voids."""
    from app.billing import gst_invoice as mod

    monkeypatch.setattr(mod, "_STORE", lambda: str(tmp_path / "invoices.jsonl"))
    rec = mod.create_invoice("c9", "starter", amount_inr=1999)
    resp = client.post(
        "/api/growth/revenue/invoice-void",
        json={"number": rec["number"], "reason": "synthetic test data"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert mod.get_by_number(rec["number"])["voided"] is True


def test_admin_void_route_missing_number(client):
    resp = client.post("/api/growth/revenue/invoice-void", json={})
    assert resp.status_code == 200
    assert resp.json().get("ok") is False
