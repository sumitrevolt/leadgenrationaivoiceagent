"""Tests — Apollo-inspired batch (prospect search/lists/import, email finder,
cadence step stats). Tmp stores, no network (MX/site calls test me nahi chalte
— pure parts hi)."""

from __future__ import annotations

import asyncio


def test_email_finder_candidates_pure():
    from app.platform import email_finder as ef

    c = ef.candidates("https://www.sharmasolar.in/about", "Ramesh Sharma")
    assert "ramesh@sharmasolar.in" == c[0]
    assert "info@sharmasolar.in" in c
    # free-mail domain -> koi pattern-guess nahi
    assert ef.candidates("gmail.com") == []
    assert ef.candidates("") == []
    assert ef._domain_of("HTTP://WWW.Abc.Co.In/x?y=1".lower()) == "abc.co.in"


def test_email_finder_find_defensive():
    from app.platform import email_finder as ef

    out = asyncio.run(ef.find(""))
    assert out["ok"] is False and out["emails"] == []


def test_email_finder_ssrf_guard_blocks_internal():
    """SSRF guard: a domain-shaped input resolving to a private/loopback/link-local
    IP must be refused BEFORE any HTTP fetch (returns [], no request)."""
    from app.platform import email_finder as ef

    # these pass _domain_of (have a dot) but resolve to non-public IPs
    for host in ("127.0.0.1", "169.254.169.254", "10.0.0.1", "192.168.1.1"):
        assert asyncio.run(ef._site_emails(host)) == []


def test_import_rows_mapping_dedupe(tmp_path, monkeypatch):
    from app.platform import prospect_lists as pl
    from app.platform import prospector

    monkeypatch.setattr(prospector, "_PROSPECTS_FILE", lambda: str(tmp_path / "p.jsonl"))
    rows = [
        {
            "Company": "Sharma Solar",
            "Email": "ramesh@sharmasolar.in",
            "Phone": "+91 98765 43210",
            "City": "Pune",
            "Industry": "solar",
            "Title": "Owner",
        },
        {"Company": "Dup Solar", "Email": "RAMESH@sharmasolar.in"},  # email dup
        {"Name": "Bina Company Wala"},  # name-only -> business_name fallback
        {"foo": "bar"},  # kuch nahi -> skip
    ]
    res = pl.import_rows(rows, "apollo_import")
    assert res["ok"] is True and res["added"] == 2 and res["skipped"] == 2
    stored = prospector.list_prospects(limit=10)
    rec = next(r for r in stored if r["business_name"] == "Sharma Solar")
    assert rec["phone"] == "9876543210" and rec["email"] == "ramesh@sharmasolar.in"
    assert rec["source"] == "apollo_import" and rec["title"] == "Owner"


def test_import_csv_text(tmp_path, monkeypatch):
    from app.platform import prospect_lists as pl
    from app.platform import prospector

    monkeypatch.setattr(prospector, "_PROSPECTS_FILE", lambda: str(tmp_path / "p.jsonl"))
    csv_text = "Company,Email,City\nGym X,owner@gymx.in,Nashik\n"
    res = pl.import_csv_text(csv_text)
    assert res["added"] == 1


def test_search_filters_and_lists(tmp_path, monkeypatch):
    from app.platform import prospect_lists as pl
    from app.platform import prospector

    monkeypatch.setattr(prospector, "_PROSPECTS_FILE", lambda: str(tmp_path / "p.jsonl"))
    monkeypatch.setattr(pl, "_LISTS", str(tmp_path / "lists.jsonl"))
    pl.import_rows(
        [
            {"Company": "Solar A", "Email": "a@solara.in", "City": "Pune", "Industry": "solar"},
            {
                "Company": "Gym B",
                "Phone": "9000000001",
                "City": "Nashik",
                "Industry": "gym_fitness",
            },
        ]
    )
    # niche filter
    assert len(pl.search(niche="solar")) == 1
    # has_email filter
    assert len(pl.search(has_email=True)) == 1
    assert pl.search(has_email=True)[0]["business_name"] == "Solar A"
    # text search
    assert len(pl.search(q="nashik")) == 1
    # score sorted + score field present
    res = pl.search()
    assert all("score" in r for r in res)
    # saved list from filters
    out = pl.create_list("solar-pune", filters={"niche": "solar"})
    assert out["ok"] is True and out["count"] == 1
    lists = pl.get_lists()
    assert lists[0]["name"] == "solar-pune" and lists[0]["count"] == 1
    # enroll to cadence (cadence store bhi tmp)
    from app.marketing import cadence

    monkeypatch.setattr(cadence, "_LEADS", lambda: str(tmp_path / "cl.jsonl"))
    monkeypatch.setattr(cadence, "_RUNS", lambda: str(tmp_path / "cr.jsonl"))
    enr = pl.enroll_list_to_cadence(lists[0]["id"])
    assert enr["ok"] is True and enr["enrolled"] == 1
    # missing list graceful
    assert pl.enroll_list_to_cadence("nahi-hai")["ok"] is False


def test_cadence_step_stats(tmp_path, monkeypatch):
    from app.marketing import cadence

    monkeypatch.setattr(cadence, "_LEADS", lambda: str(tmp_path / "l.jsonl"))
    monkeypatch.setattr(cadence, "_RUNS", lambda: str(tmp_path / "r.jsonl"))
    cadence._append(cadence._RUNS(), {"channel": "email", "action": "intro"})
    cadence._append(cadence._RUNS(), {"channel": "email", "action": "intro"})
    cadence._append(cadence._RUNS(), {"channel": "sms", "action": "reminder"})
    st = cadence.stats()
    assert st["step_touches"]["email:intro"] == 2
    assert st["step_touches"]["sms:reminder"] == 1


def test_apollo_routes_registered():
    from app.api.growth import router
    from app.utils.route_inspection import iter_effective_routes

    paths = {getattr(r, "path", "") for r in iter_effective_routes(router.routes)}
    for p in (
        "/growth/prospects/search",
        "/growth/prospects/lists",
        "/growth/prospects/import",
        "/growth/prospects/find-email",
        "/growth/prospects/lists/{list_id}/enroll-cadence",
    ):
        assert p in paths, f"route missing: {p}"
