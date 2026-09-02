"""50 simulated Day-1 onboardings — fake tenants, never Jiya, never web process."""

from __future__ import annotations

from app.tasks import staff_jobs


def test_fifty_fake_onboards_echo_client_id_and_never_raise(monkeypatch):
    async def _fake_auto_onboard(cid: str, send_welcome: bool = True):
        return {"ok": True}

    import asyncio

    import app.marketing.onboarding as onboarding

    monkeypatch.setattr(onboarding, "auto_onboard", _fake_auto_onboard)
    monkeypatch.setattr(
        staff_jobs,
        "_run_async",
        lambda coro: asyncio.run(coro) if asyncio.iscoroutine(coro) else coro,
    )

    ids = [f"sim-onboard-{i:03d}" for i in range(50)]
    assert all("jiya" not in cid.lower() for cid in ids)

    results = [staff_jobs.onboard_client.run(cid, send_welcome=False) for cid in ids]
    assert len(results) == 50
    assert all(r.get("ok") is True for r in results)
    assert [r.get("client_id") for r in results] == ids


def test_onboard_client_failure_is_recorded_not_raised(monkeypatch):
    async def _boom(cid: str, send_welcome: bool = True):
        raise RuntimeError("simulated scrape fail")

    import asyncio

    import app.marketing.onboarding as onboarding

    monkeypatch.setattr(onboarding, "auto_onboard", _boom)
    monkeypatch.setattr(
        staff_jobs,
        "_run_async",
        lambda coro: asyncio.run(coro) if asyncio.iscoroutine(coro) else coro,
    )
    out = staff_jobs.onboard_client.run("sim-onboard-fail", send_welcome=False)
    assert out["ok"] is False
    assert out["client_id"] == "sim-onboard-fail"
    assert "simulated scrape fail" in (out.get("error") or "")
