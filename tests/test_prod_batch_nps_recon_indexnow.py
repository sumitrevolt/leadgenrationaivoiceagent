"""Tests — prod-batch 2026-06-10: NPS collector, payment recon, IndexNow.
Project convention: sync + asyncio.run, tmp stores monkeypatch, no DB/network.
"""

from __future__ import annotations

import asyncio
import json


# ----------------------------- NPS ----------------------------- #
def test_nps_classify_and_compute():
    from app.platform import nps

    assert nps.classify(10) == "promoter" and nps.classify(9) == "promoter"
    assert nps.classify(8) == "passive" and nps.classify(7) == "passive"
    assert nps.classify(6) == "detractor" and nps.classify(0) == "detractor"
    out = nps.compute_nps([10, 9, 8, 3])  # 2 promoters, 1 passive, 1 detractor
    assert out["nps"] == 25 and out["total"] == 4
    assert nps.compute_nps([])["nps"] is None


def test_nps_submit_and_stats(tmp_path, monkeypatch):
    from app.platform import nps

    monkeypatch.setattr(nps, "_STORE", str(tmp_path / "nps.jsonl"))
    monkeypatch.delenv("NPS_ALERTS", raising=False)  # alert OFF = record-only
    r = asyncio.run(nps.submit(9, "badhiya service", "Ramesh", "+919812345678", "sharma-solar"))
    assert r["ok"] and r["bucket"] == "promoter" and r["suggest_review"]
    r2 = asyncio.run(nps.submit(2, "slow", client_slug="sharma-solar"))
    assert r2["ok"] and r2["bucket"] == "detractor" and not r2["suggest_review"]
    s = nps.stats("sharma-solar")
    assert s["total"] == 2 and s["promoters"] == 1 and s["detractors"] == 1 and s["nps"] == 0
    assert len(s["recent"]) == 2
    # score clamp
    r3 = asyncio.run(nps.submit(99))
    assert r3["ok"] and r3["bucket"] == "promoter"


# ------------------- Payment recon (deleted 2026-07-19) ------------------- #
# Razorpay gateway removed 2026-06-18; inert stub deleted 2026-07-19 (dead-code
# cleanup). Payments = manual UPI. Guard against reintroduction.
def test_recon_module_removed():
    import importlib

    import pytest

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.billing.payment_recon")


# ----------------------------- IndexNow ----------------------------- #
def test_indexnow_payload_and_sitemap_parse(tmp_path, monkeypatch):
    from app.marketing import indexnow as ix

    monkeypatch.setenv("INDEXNOW_KEY", "k" * 32)
    p = ix.build_payload(
        ["/blog/solar-pune", "https://leadsgenai.in/audit", "https://evil.com/x", ""]
    )
    assert p["host"] == "leadsgenai.in" and p["key"] == "k" * 32
    assert p["keyLocation"].endswith("/indexnow-key.txt")
    assert p["urlList"] == ["https://leadsgenai.in/blog/solar-pune", "https://leadsgenai.in/audit"]
    locs = ix.parse_sitemap_locs(
        "<urlset><url><loc>https://leadsgenai.in/</loc></url><url><loc> https://leadsgenai.in/blog/a </loc></url></urlset>"
    )
    assert locs == ["https://leadsgenai.in/", "https://leadsgenai.in/blog/a"]


def test_indexnow_gate_and_key_persist(tmp_path, monkeypatch):
    from app.marketing import indexnow as ix

    monkeypatch.delenv("INDEXNOW", raising=False)
    assert asyncio.run(ix.submit_sitemap_if_enabled())["skipped"] == "INDEXNOW off"
    # key auto-gen + persist (env unset)
    monkeypatch.delenv("INDEXNOW_KEY", raising=False)
    monkeypatch.setattr(ix, "_KEY_FILE", str(tmp_path / "key.txt"))
    k1 = ix.get_key()
    assert len(k1) == 32 and ix.get_key() == k1  # stable across calls


def test_indexnow_cursor_roundtrip(tmp_path, monkeypatch):
    from app.marketing import indexnow as ix

    monkeypatch.setattr(ix, "_CURSOR", str(tmp_path / "cur.json"))
    ix._save_seen({"abc", "def"})
    assert ix._load_seen() == {"abc", "def"}
    data = json.load(open(tmp_path / "cur.json", encoding="utf-8"))
    assert sorted(data["seen"]) == ["abc", "def"]
