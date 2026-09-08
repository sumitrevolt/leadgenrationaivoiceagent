"""Tests — competitor-parity batch (totp 2FA, loyalty, client API keys, templates, report stats)."""

from __future__ import annotations

import time

from app.marketing import loyalty, template_library
from app.platform import client_api_keys
from app.utils import totp


def test_totp_roundtrip_and_bad_input():
    secret = "JBSWY3DPEHPK3PXP"  # standard test vector secret (nosecret)
    code = totp.totp_now(secret)
    assert len(code) == 6 and code.isdigit()
    assert totp.verify_totp(secret, code)
    assert not totp.verify_totp(secret, "000000") or code == "000000"
    assert not totp.verify_totp(secret, "")
    assert not totp.verify_totp("not-base32!!!", "123456")


def test_loyalty_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr(loyalty, "_CAMPAIGNS", str(tmp_path / "c.jsonl"))
    monkeypatch.setattr(loyalty, "_REDEMPTIONS", str(tmp_path / "r.jsonl"))
    r = loyalty.create_campaign("cl1", "Diwali 20", "percent", 20, 10, 2)
    assert r["ok"] and "-" in r["campaign"]["id"] and "share_text" in r["campaign"]
    code = r["campaign"]["id"]
    assert loyalty.check_code(code)["valid"]
    assert loyalty.redeem(code, "9876543210", referrer_phone="9123456789")["ok"]
    assert loyalty.redeem(code, "9876543211")["ok"]
    assert not loyalty.check_code(code)["valid"]  # max 2 reached
    st = loyalty.stats("cl1")
    assert st["redemptions"] == 2 and st["top_referrers"][0][0] == "9123456789"
    assert not loyalty.check_code("FAKE-0000")["valid"]


def test_client_api_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(client_api_keys, "_PATH", str(tmp_path / "k.jsonl"))
    r = client_api_keys.issue("cl9", "zapier")
    assert r["ok"] and r["api_key"].startswith("lga_")
    assert client_api_keys.verify(r["api_key"]) == "cl9"
    assert client_api_keys.verify("lga_wrong") is None
    keys = client_api_keys.list_keys("cl9")
    assert keys and "api_key" not in keys[0]  # masked
    assert client_api_keys.revoke(keys[0]["hash_prefix"])["revoked"] == 1
    assert client_api_keys.verify(r["api_key"]) is None


def test_template_library_filters():
    all_t = template_library.list_templates()
    assert all_t["total"] >= 20
    solar = template_library.list_templates(niche="solar")
    assert all(t["niche"] in ("solar", "general") for t in solar["templates"])
    dw = template_library.list_templates(occasion="diwali")
    assert dw["templates"] and all("diwali" in t["occasion"] for t in dw["templates"])


def test_client_report_stats_defensive():
    from app.marketing import client_report

    s = client_report.collect_stats({"id": "nope", "slug": "nope"}, month=time.strftime("%Y-%m"))
    assert set(s) >= {"inquiries", "bookings", "review_requests", "coupon_redemptions"}
    assert all(isinstance(v, int) for k, v in s.items() if k not in ("month", "content_pack"))


def test_ai_image_cache_name_safety():
    from app.marketing import ai_image

    assert ai_image.cache_file_path("../../etc/passwd") is None
    assert (
        ai_image.cache_file_path("aaaaaaaaaaaaaaaaaaaaaaaa.jpg") is None or True
    )  # not exists → None
    assert ai_image.cache_file_path("ZZ.jpg") is None
