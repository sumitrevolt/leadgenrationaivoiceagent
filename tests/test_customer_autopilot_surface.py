"""Contract for the customer autopilot surface (Product-1 GAP-1 fix, 2026-07-06).

The hands-free drafts (owner-brief / nps / stale-nudge / evergreen) were written to
data/autopilot_*.jsonl with NO require_customer route reading them — invisible to
the buyer. `drafts_for_client` is the customer-facing read; it MUST isolate by
client (client_id OR slug), honour the date window, and never leak another tenant.
"""

import json


def test_drafts_for_client_filters_and_isolates(monkeypatch, tmp_path):
    from app.platform import customer_autopilot as cap

    monkeypatch.setattr(cap, "_DATA_DIR", str(tmp_path))
    today = cap._today()
    (tmp_path / "autopilot_brief.jsonl").write_text(
        json.dumps(
            {
                "date": today,
                "kind": "owner_brief",
                "client_id": "A",
                "brief": "Aaj ka brief A",
                "status": "ready",
                "created_at": today + "T10:00:00",
            }
        )
        + "\n"
        + json.dumps(
            {
                "date": today,
                "kind": "owner_brief",
                "client_id": "B",
                "brief": "brief B (secret)",
                "status": "ready",
                "created_at": today + "T10:00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "autopilot_nps.jsonl").write_text(
        json.dumps(
            {
                "date": today,
                "kind": "nps_survey",
                "slug": "jiya",
                "message": "feedback dena?",
                "wa_link": "wa://x",
                "status": "draft",
                "created_at": today + "T11:00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    drafts = cap.drafts_for_client("A", slug="jiya")
    kinds = {d["kind"] for d in drafts}
    assert kinds == {"owner_brief", "nps_survey"}  # A's brief (by id) + jiya's nps (by slug)
    blob = " ".join(d["text"] for d in drafts)
    assert "brief B (secret)" not in blob  # tenant B's draft NOT leaked
    assert drafts[0]["kind"] == "nps_survey"  # newest-first (11:00 > 10:00)
    nps = next(d for d in drafts if d["kind"] == "nps_survey")
    assert nps["wa_link"] == "wa://x"  # 1-click-send link surfaced
    assert "survey" in nps["title"].lower()  # friendly label applied


def test_drafts_for_client_date_cutoff(monkeypatch, tmp_path):
    from app.platform import customer_autopilot as cap

    monkeypatch.setattr(cap, "_DATA_DIR", str(tmp_path))
    (tmp_path / "autopilot_brief.jsonl").write_text(
        json.dumps(
            {
                "date": "2020-01-01",
                "kind": "owner_brief",
                "client_id": "A",
                "brief": "old",
                "created_at": "2020-01-01T10:00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert cap.drafts_for_client("A", days=14) == []  # older than cutoff dropped


def test_drafts_for_client_empty_without_identity():
    from app.platform import customer_autopilot as cap

    assert (
        cap.drafts_for_client("", slug="") == []
    )  # no id + no slug => nothing (never mass-return)


def test_autopilot_route_mounted_and_requires_customer():
    # Route is registered AND gated (anon must not get a 2xx — same invariant as RBAC tests).
    from starlette.testclient import TestClient

    from app.main import app

    r = TestClient(app).get("/api/customer/autopilot")
    assert r.status_code not in (200, 201, 202, 203, 204)  # require_customer blocks anon
