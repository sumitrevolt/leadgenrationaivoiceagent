"""Pure-python tests for DKIM presence + DMARC policy-strength checks in the
deliverability monitor. No real DNS — _txt_lookup is monkeypatched.
"""

from __future__ import annotations

import app.platform.deliverability_monitor as dm


def _patch_txt(monkeypatch, mapping: dict[str, list[str]]):
    """Monkeypatch _txt_lookup with a name->records map (default empty)."""
    monkeypatch.setattr(dm, "_txt_lookup", lambda name: mapping.get(name, []))


def test_dmarc_policy_parse():
    assert dm._dmarc_policy(["v=DMARC1; p=reject; rua=mailto:x@y.in"]) == "reject"
    assert dm._dmarc_policy(["v=DMARC1; p=quarantine"]) == "quarantine"
    assert dm._dmarc_policy(["v=DMARC1; p=none"]) == "none"
    assert dm._dmarc_policy(["not a dmarc record"]) == ""
    assert dm._dmarc_policy([]) == ""


def test_dmarc_policy_with_spaces():
    # tolerate "p = reject" style spacing via lower+strip on tag
    assert dm._dmarc_policy(["v=dmarc1;p=quarantine;adkim=s"]) == "quarantine"


def test_dkim_selectors_env_override(monkeypatch):
    monkeypatch.setenv("DKIM_SELECTOR", "foo, bar ;baz")
    assert dm._dkim_selectors() == ["foo", "bar", "baz"]


def test_dkim_selectors_default(monkeypatch):
    monkeypatch.delenv("DKIM_SELECTOR", raising=False)
    sels = dm._dkim_selectors()
    assert "hostingermail" in sels
    assert "default" in sels


def test_check_dkim_found(monkeypatch):
    monkeypatch.delenv("DKIM_SELECTOR", raising=False)
    _patch_txt(
        monkeypatch,
        {
            "default._domainkey.example.com": ["v=DKIM1; k=rsa; p=MIGfMA0..."],
        },
    )
    out = dm.check_dkim("example.com")
    assert out["dkim_ok"] is True
    assert out["dkim_selector"] == "default"


def test_check_dkim_missing(monkeypatch):
    monkeypatch.delenv("DKIM_SELECTOR", raising=False)
    _patch_txt(monkeypatch, {})  # nothing resolves
    out = dm.check_dkim("example.com")
    assert out["dkim_ok"] is False
    assert out["dkim_selector"] == ""
    assert out["dkim_tried"]  # selectors were attempted


def test_check_dkim_custom_selector(monkeypatch):
    monkeypatch.setenv("DKIM_SELECTOR", "mysel")
    _patch_txt(
        monkeypatch,
        {
            "mysel._domainkey.example.com": ["v=DKIM1; p=abc"],
        },
    )
    out = dm.check_dkim("example.com")
    assert out["dkim_ok"] is True
    assert out["dkim_selector"] == "mysel"
    assert out["dkim_tried"] == ["mysel"]


def test_check_records_full_strong(monkeypatch):
    monkeypatch.delenv("DKIM_SELECTOR", raising=False)
    _patch_txt(
        monkeypatch,
        {
            "example.com": ["v=spf1 include:_spf.hostinger.com ~all"],
            "_dmarc.example.com": ["v=DMARC1; p=reject"],
            "hostingermail._domainkey.example.com": ["v=DKIM1; p=xyz"],
        },
    )
    out = dm.check_records("example.com")
    assert out["spf_ok"] is True
    assert out["dmarc_ok"] is True
    assert out["dmarc_policy"] == "reject"
    assert out["dmarc_strong"] is True
    assert out["dkim_ok"] is True


def test_check_records_weak_dmarc(monkeypatch):
    monkeypatch.delenv("DKIM_SELECTOR", raising=False)
    _patch_txt(
        monkeypatch,
        {
            "example.com": ["v=spf1 ~all"],
            "_dmarc.example.com": ["v=DMARC1; p=none"],
        },
    )
    out = dm.check_records("example.com")
    assert out["dmarc_ok"] is True
    assert out["dmarc_policy"] == "none"
    assert out["dmarc_strong"] is False
    assert out["dkim_ok"] is False


def test_check_records_all_missing(monkeypatch):
    monkeypatch.delenv("DKIM_SELECTOR", raising=False)
    _patch_txt(monkeypatch, {})
    out = dm.check_records("example.com")
    assert out["spf_ok"] is False
    assert out["dmarc_ok"] is False
    assert out["dmarc_strong"] is False
    assert out["dkim_ok"] is False


def test_run_check_problems_weak_dmarc_and_no_dkim(monkeypatch):
    import asyncio

    monkeypatch.delenv("DKIM_SELECTOR", raising=False)
    monkeypatch.setattr(
        dm, "check_blacklists", lambda ip="": {"ip": "", "listed_on": [], "checked": []}
    )
    monkeypatch.setattr(dm, "_enabled_alerts", lambda: False)
    monkeypatch.setattr(dm, "_LOG", "data/_test_deliverability_check.jsonl")
    _patch_txt(
        monkeypatch,
        {
            "leadsgenai.in": ["v=spf1 ~all"],
            "_dmarc.leadsgenai.in": ["v=DMARC1; p=none"],
        },
    )
    rec = asyncio.run(dm.run_check())
    probs = " | ".join(rec.get("problems", []))
    assert "DMARC policy weak" in probs
    assert "DKIM record missing" in probs
    assert "SPF" not in probs  # spf present


def test_recommend_fixes_spf_missing_gives_exact_record():
    rec = {
        "domain": "leadsgenai.in",
        "spf_ok": False,
        "dmarc_ok": True,
        "dmarc_strong": True,
        "dkim_ok": True,
        "blacklist": {},
    }
    out = dm.recommend_fixes(rec)
    assert len(out) == 1
    assert "SPF" in out[0]["issue"]
    assert out[0]["value"] == "v=spf1 include:_spf.hostinger.com ~all"
    assert "leadsgenai.in" in out[0]["where"]


def test_recommend_fixes_weak_dmarc_suggests_quarantine_not_reject():
    rec = {
        "domain": "leadsgenai.in",
        "spf_ok": True,
        "dmarc_ok": True,
        "dmarc_strong": False,
        "dmarc_policy": "none",
        "dkim_ok": True,
        "blacklist": {},
    }
    out = dm.recommend_fixes(rec)
    assert len(out) == 1
    assert "p=none" in out[0]["issue"]
    assert "p=quarantine" in out[0]["value"]
    assert "_dmarc.leadsgenai.in" in out[0]["where"]


def test_recommend_fixes_dkim_missing_points_to_provider_toggle_not_a_dns_value():
    rec = {
        "domain": "leadsgenai.in",
        "spf_ok": True,
        "dmarc_ok": True,
        "dmarc_strong": True,
        "dkim_ok": False,
        "blacklist": {},
    }
    out = dm.recommend_fixes(rec)
    assert len(out) == 1
    assert "DKIM" in out[0]["issue"]
    assert "Hostinger" in out[0]["how"]


def test_recommend_fixes_blacklist_gives_spamhaus_lookup_url():
    rec = {
        "domain": "leadsgenai.in",
        "spf_ok": True,
        "dmarc_ok": True,
        "dmarc_strong": True,
        "dkim_ok": True,
        "blacklist": {"listed_on": ["zen.spamhaus.org"], "ip": "1.2.3.4"},
    }
    out = dm.recommend_fixes(rec)
    assert len(out) == 1
    assert "zen.spamhaus.org" in out[0]["issue"]
    assert "1.2.3.4" in out[0]["value"]
    assert "spamhaus.org/lookup" in out[0]["value"]


def test_recommend_fixes_empty_when_everything_ok():
    rec = {
        "domain": "leadsgenai.in",
        "spf_ok": True,
        "dmarc_ok": True,
        "dmarc_strong": True,
        "dkim_ok": True,
        "blacklist": {"listed_on": []},
    }
    assert dm.recommend_fixes(rec) == []


def test_run_check_includes_recommendations_when_problems_found(monkeypatch):
    import asyncio

    monkeypatch.delenv("DKIM_SELECTOR", raising=False)
    monkeypatch.setattr(
        dm, "check_blacklists", lambda ip="": {"ip": "", "listed_on": [], "checked": []}
    )
    monkeypatch.setattr(dm, "_enabled_alerts", lambda: False)
    monkeypatch.setattr(dm, "_LOG", "data/_test_deliverability_check.jsonl")
    _patch_txt(
        monkeypatch,
        {
            "leadsgenai.in": ["v=spf1 ~all"],
            "_dmarc.leadsgenai.in": ["v=DMARC1; p=none"],
        },
    )
    rec = asyncio.run(dm.run_check())
    assert len(rec["recommendations"]) == 2  # weak DMARC + missing DKIM
    issues = {r["issue"] for r in rec["recommendations"]}
    assert any("DMARC" in i for i in issues)
    assert any("DKIM" in i for i in issues)


def test_run_check_no_problems_when_all_strong(monkeypatch):
    import asyncio

    monkeypatch.delenv("DKIM_SELECTOR", raising=False)
    monkeypatch.setattr(
        dm, "check_blacklists", lambda ip="": {"ip": "", "listed_on": [], "checked": []}
    )
    monkeypatch.setattr(dm, "_enabled_alerts", lambda: False)
    monkeypatch.setattr(dm, "_LOG", "data/_test_deliverability_check.jsonl")
    _patch_txt(
        monkeypatch,
        {
            "leadsgenai.in": ["v=spf1 ~all"],
            "_dmarc.leadsgenai.in": ["v=DMARC1; p=quarantine"],
            "hostingermail._domainkey.leadsgenai.in": ["v=DKIM1; p=abc"],
        },
    )
    rec = asyncio.run(dm.run_check())
    assert rec.get("problems") == []
