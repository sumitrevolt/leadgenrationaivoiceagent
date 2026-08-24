"""ADR-065 deeper logs: customer-scoped jobs (client_report, content) now write
per-client AutomationLog rows (client_id set + output_summary), so the admin
Automation Runs "customer" filter is meaningful instead of always-blank.
"""

import pytest


@pytest.mark.asyncio
async def test_run_monthly_logs_per_client(monkeypatch):
    from app.marketing import client_report

    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients",
        lambda *a, **k: [{"id": "c1"}, {"id": "c2"}],
        raising=False,
    )

    async def _fake_build(cid, send=None):
        return {"ok": True, "emailed": False, "path": f"data/client_reports/{cid}.html"}

    monkeypatch.setattr(client_report, "build_report", _fake_build)

    calls = []
    monkeypatch.setattr(
        "app.platform.automation_log_service.log_event",
        lambda **kw: calls.append(kw) or "logid",
    )

    r = await client_report.run_monthly(send=False)
    assert r["ok"] is True
    logged = {c["client_id"]: c for c in calls}
    assert set(logged) == {"c1", "c2"}
    assert logged["c1"]["job_type"] == "client_report"
    assert logged["c1"]["status"] == "success"
    assert "c1.html" in logged["c1"]["output_summary"]  # report path = proof


@pytest.mark.asyncio
async def test_run_daily_content_logs_per_client(monkeypatch):
    from app.marketing import auto_content

    monkeypatch.setattr(auto_content, "AUTO_SEED_SELF", False, raising=False)
    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients",
        lambda *a, **k: [{"id": "c1", "business_name": "Biz"}],
        raising=False,
    )

    async def _fake_gen(client):
        return [{"type": "post"}, {"type": "post"}]

    monkeypatch.setattr(auto_content, "generate_for_client", _fake_gen)
    monkeypatch.setattr(auto_content, "_append_items", lambda cid, items: len(items), raising=False)
    monkeypatch.setattr(auto_content, "_social_prefs", lambda cid: {}, raising=False)

    calls = []
    monkeypatch.setattr(
        "app.platform.automation_log_service.log_event",
        lambda **kw: calls.append(kw) or "logid",
    )

    r = await auto_content.run_daily_content()
    assert r["clients"] >= 1
    content = [c for c in calls if c.get("job_type") == "content" and c.get("client_id") == "c1"]
    assert content, "no per-client content automation-log row written"
    assert content[0]["status"] == "success"
    assert "content items" in content[0]["output_summary"]
