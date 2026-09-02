"""Contract for day-1 delivery seed (Product-1 delivery-gap fix, 2026-07-06).

A new customer was landing on an EMPTY portal: `auto_onboard` (website→KB seed +
first content pack + customer-visible content queue + niche snapshot) had no
signup/onboard caller — it only ran via the AUTO_ONBOARD-gated hourly sweep. Now
signup + admin-onboard enqueue `onboard_client` to the worker. Two guards:
  1. `auto_onboard(send_welcome=False)` skips its welcome (so /signup, which sends
     its own, doesn't double-message the customer).
  2. the `onboard_client` Celery task forwards send_welcome to auto_onboard.
"""


async def test_auto_onboard_send_welcome_false_skips_welcome(monkeypatch):
    from app.marketing import onboarding

    calls = {"welcome": 0}

    async def _kb(cid, site):
        return {"kb_chunks": 0}

    async def _pack(client):
        return {}

    async def _welcome(client, kb_seeded):
        calls["welcome"] += 1
        return {"sent": True}

    monkeypatch.setattr(onboarding, "_seed_kb_from_website", _kb)
    monkeypatch.setattr(onboarding, "_first_content_pack", _pack)
    monkeypatch.setattr(onboarding, "_send_welcome_whatsapp", _welcome)
    monkeypatch.setattr(onboarding, "_log", lambda *a, **k: None)

    import app.marketing.clients_store as cs

    monkeypatch.setattr(
        cs, "get_client", lambda cid: {"id": cid, "business_name": "Jiya Makeover", "website": ""}
    )
    monkeypatch.setattr(cs, "update_client", lambda *a, **k: None, raising=False)

    import app.marketing.auto_content as ac

    async def _seed(client):
        return 0

    monkeypatch.setattr(ac, "seed_client_content", _seed, raising=False)

    from app.platform import client_snapshots

    monkeypatch.setattr(
        client_snapshots, "apply_niche_to_client", lambda cid: {"ok": True}, raising=False
    )

    r_off = await onboarding.auto_onboard("c1", send_welcome=False)
    assert calls["welcome"] == 0
    assert r_off["steps"]["welcome_whatsapp"] == {"skipped": "caller_sends_own_welcome"}

    r_on = await onboarding.auto_onboard("c1", send_welcome=True)
    assert calls["welcome"] == 1  # welcome sent when not suppressed


def test_onboard_client_task_forwards_send_welcome(monkeypatch):
    from app.marketing import onboarding
    from app.tasks import staff_jobs

    seen = {}

    async def _spy(cid, send_welcome=True):
        seen["cid"] = cid
        seen["send_welcome"] = send_welcome
        return {"ok": True, "client_id": cid}

    monkeypatch.setattr(onboarding, "auto_onboard", _spy)

    res = staff_jobs.onboard_client.apply(args=["c9", False]).get()
    assert res == {"ok": True, "client_id": "c9"}
    assert seen == {"cid": "c9", "send_welcome": False}


def test_onboard_client_task_never_raises(monkeypatch):
    from app.marketing import onboarding
    from app.tasks import staff_jobs

    async def _boom(cid, send_welcome=True):
        raise RuntimeError("scrape blew up")

    monkeypatch.setattr(onboarding, "auto_onboard", _boom)
    res = staff_jobs.onboard_client.apply(args=["c7", True]).get()
    assert res["ok"] is False and res["client_id"] == "c7"  # contained, not raised


async def test_auto_onboard_skips_when_already_setup(monkeypatch):
    # Admin onboard is re-callable (password reset) — a re-run of an already-setup
    # client must NOT re-scrape/regenerate or re-send a welcome to an existing customer.
    from app.marketing import onboarding

    calls = {"welcome": 0, "kb": 0}

    async def _kb(cid, site):
        calls["kb"] += 1
        return {"kb_chunks": 0}

    async def _welcome(client, kb_seeded):
        calls["welcome"] += 1
        return {"sent": True}

    monkeypatch.setattr(onboarding, "_seed_kb_from_website", _kb)
    monkeypatch.setattr(onboarding, "_send_welcome_whatsapp", _welcome)

    import app.marketing.clients_store as cs

    monkeypatch.setattr(
        cs, "get_client", lambda cid: {"id": cid, "business_name": "Jiya", "setup_done": True}
    )

    r = await onboarding.auto_onboard("c1", send_welcome=True)
    assert r.get("skipped") == "already_setup"
    assert calls == {"welcome": 0, "kb": 0}  # early-return: no heavy re-run, no re-welcome
