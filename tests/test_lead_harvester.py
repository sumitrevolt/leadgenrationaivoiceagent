"""Tests — lead harvester: gating, blocked-domains policy, validate/dedupe/persist,
source inertness bina keys, never-raise. Hermetic (no network/DB).
"""

from __future__ import annotations

import asyncio


def test_gating_and_source_status(monkeypatch):
    from app.platform import lead_harvester as lh

    monkeypatch.delenv("LEAD_HARVESTER", raising=False)
    assert lh.enabled() is False
    assert asyncio.run(lh.run_loop_sweep()) == {"enabled": False}

    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("DATA_GOV_IN_API_KEY", raising=False)
    st = lh.source_status()
    assert st["websearch"] is False and st["opendata"] is False
    assert any("justdial" in d for d in st["blocked_domains_policy"])


def test_blocked_domains_tos_policy():
    from app.platform import lead_harvester as lh

    # ToS-risky directories/socials KABHI fetch nahi
    for url in (
        "https://www.justdial.com/pune/x",
        "https://dir.indiamart.com/y",
        "https://linkedin.com/in/z",
        "https://facebook.com/p",
    ):
        assert lh._blocked(url) is True
    assert lh._blocked("https://sharmasolar.in/contact") is False


def test_gated_sources_inert_without_keys(monkeypatch):
    from app.platform import lead_harvester as lh

    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("DATA_GOV_IN_API_KEY", raising=False)
    ws = asyncio.run(lh._src_websearch("solar", "Pune", 5))
    od = asyncio.run(lh._src_opendata("solar", "Pune", 5))
    assert ws["leads"] == [] and "skipped" in ws
    assert od["leads"] == [] and "skipped" in od


def test_phone_email_validation(monkeypatch):
    from app.platform import lead_harvester as lh

    assert lh._valid_phone("098765 43210").endswith("9876543210")
    assert lh._valid_phone("+91-9876543210").startswith("+91")
    assert lh._valid_phone("12345") == ""
    # email verify stub (MX env-dependence hatao)
    from app.lead_scraper import email_verify

    monkeypatch.setattr(
        email_verify, "verify", lambda e, check_mx=True: {"ok": True, "email": e, "reason": ""}
    )
    assert asyncio.run(lh._valid_email("INFO@Sharma.in")) == "info@sharma.in"
    monkeypatch.setattr(
        email_verify,
        "verify",
        lambda e, check_mx=True: {"ok": False, "email": e, "reason": "no mx"},
    )
    assert asyncio.run(lh._valid_email("x@nope.invalid")) == ""
    assert asyncio.run(lh._valid_email("notanemail")) == ""


def test_email_verify_rejects_asset_and_placeholder_false_positives():
    from app.lead_scraper import email_verify

    bad = [
        "flags@2x.webp",
        "group-1000001686@2x.webp",
        "ecom-swiper@11.0.5.js",
        "info@domainname.com",
        "example@mysite.com",
        "john@company.com",
        "support@pw.lie",
        "id@r93.ful",
        "a5%@bfe0r.vl",
        "%20tkiblr1@taiyokagakuindia.com",
    ]
    for addr in bad:
        out = email_verify.verify(addr, check_mx=False)
        assert out["ok"] is False
        assert "placeholder" in out["reason"]

    assert email_verify.verify("admin@leadsgenai.in", check_mx=False)["ok"] is True
    assert email_verify.verify("sunny@leadsgenai.in", check_mx=False)["ok"] is True


def test_run_harvest_dedupe_and_persist(tmp_path, monkeypatch):
    from app.platform import lead_harvester as lh
    from app.platform import prospector

    # store -> tmp (DB mirror off)
    monkeypatch.setattr(prospector, "_PROSPECTS_FILE", lambda: str(tmp_path / "prospects.jsonl"))
    monkeypatch.setattr(prospector, "_persist_prospect_to_db", lambda rec: True)
    # seed existing prospect (dedupe target)
    prospector._append(
        {"id": "old1", "business_name": "Old Biz", "phone": "+919876543210", "email": "old@biz.in"}
    )

    async def fake_src(niche, city, limit):
        return {
            "source": "fake",
            "leads": [
                {
                    "business_name": "Old Biz",
                    "phone": "9876543210",
                    "email": "",
                    "website": "",
                    "source": "fake",
                },  # dup
                {
                    "business_name": "Naya Solar",
                    "phone": "9123456780",
                    "email": "",
                    "website": "https://nayasolar.in",
                    "source": "fake",
                },
            ],
        }

    monkeypatch.setattr(lh, "SOURCES", {"fake": fake_src})

    async def no_enrich(limit=8):
        return {"tried": 0, "found": 0}

    monkeypatch.setattr(lh, "enrich_missing_emails", no_enrich)
    monkeypatch.setattr(lh, "_RUNS", str(tmp_path / "runs.jsonl"))

    out = asyncio.run(lh.run_harvest("solar_residential", "Pune", 5, ["fake"]))
    assert out["ok"] is True
    assert out["new_leads"] == 1 and out["deduped"] == 1
    rows = prospector._read_all()
    naya = next(r for r in rows if r["business_name"] == "Naya Solar")
    assert naya["phone"] == "+919123456780"
    assert naya["source_query"] == "harvest:fake"
    assert naya["status"] == "ready"
    assert lh.recent_runs(5)[0]["new_leads"] == 1


def test_run_harvest_never_raises(monkeypatch):
    from app.platform import lead_harvester as lh

    async def boom(niche, city, limit):
        raise RuntimeError("source down")

    monkeypatch.setattr(lh, "SOURCES", {"boom": boom})

    async def no_enrich(limit=8):
        return {"tried": 0, "found": 0}

    monkeypatch.setattr(lh, "enrich_missing_emails", no_enrich)
    out = asyncio.run(lh.run_harvest("gym", "Mumbai", 3, ["boom"]))
    assert out["ok"] is True and out["new_leads"] == 0  # exception swallow, run complete
