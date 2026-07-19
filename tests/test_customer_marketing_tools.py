"""Phase-1 self-serve marketing tool endpoints (council 2026-06-26).

Calls the route functions directly with a dummy client_id (auth = shared
require_customer dep, tested elsewhere). Verifies the customer-scoped GBP audit,
creatives gallery and monthly report reuse the admin generators and stay
best-effort / never-500.
"""

import asyncio

import app.api.customer_dashboard as cd


def test_routes_registered_no_dupes():
    paths = [r.path for r in cd.router.routes]
    for p in (
        "/api/customer/gbp/questions",
        "/api/customer/gbp/score",
        "/api/customer/gbp/council-suggest",
        "/api/customer/creatives",
        "/api/customer/report",
    ):
        assert p in paths, f"{p} not registered"
        assert paths.count(p) == 1, f"{p} duplicated (FastAPI first-route-wins shadow)"


def test_gbp_questions_and_score_roundtrip(tmp_path, monkeypatch):
    # isolate persistence dir so the test never touches real data/
    monkeypatch.setattr(cd, "_GBP_DIR", str(tmp_path / "gbp"))
    cid = "__test_gbp__"

    q = cd.customer_gbp_questions(client_id=cid)
    assert q["total"] == len(q["questions"]) > 0
    assert q["last"] is None  # nothing saved yet

    answers = {str(item["id"]): 0 for item in q["questions"]}
    res = cd.customer_gbp_score(answers=answers, client_id=cid)
    assert 0 <= res["score"] <= 100
    assert res["grade"]
    assert "top_fixes" in res and "at" in res

    # latest result persists per-client and comes back on next questions call
    q2 = cd.customer_gbp_questions(client_id=cid)
    assert q2["last"] is not None
    assert q2["last"]["score"] == res["score"]


def test_creatives_shape():
    out = cd.customer_creatives(client_id="__test_creatives__")
    assert "festivals" in out and isinstance(out["festivals"], list)
    assert "posts" in out and isinstance(out["posts"], list)
    assert "poster_count" in out


def test_monthly_report_builds():
    out = asyncio.run(cd.customer_monthly_report(month="", client_id="__test_report__"))
    assert out.get("month")
    assert "stats" in out
