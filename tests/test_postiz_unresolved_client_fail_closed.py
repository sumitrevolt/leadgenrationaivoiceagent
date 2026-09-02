"""An UNRESOLVED tenant must never inherit own-brand Postiz channels.

`video_ad_cycle._publish_one` used to resolve the tenant as
``clients_store.get_client(cid) or {}``. When that lookup missed — deleted
record, canonicalisation drift, corrupt ledger line — the publish path got an
EMPTY dict, and `postiz_publish._is_own_brand` reads any falsy client as
"own-brand / no client context" (postiz_publish.py:74). The customer's video
therefore fanned out to the corporate `POSTIZ_INTEGRATIONS` channels — the
exact 2026-07-17 contamination the docstring claims to prevent.

The empty-dict sentinel is legitimate AT THE POSTIZ BOUNDARY (own-brand
publishes call `publish_video({}, ...)`), so the refusal belongs at the only
layer that still knows the difference: the caller that owns the client id.
`_resolve_publish_client` returns `{}` for "no id at all" and `None` for
"real id, resolved to nothing", and `_publish_one` fails CLOSED on `None`.
"""

from __future__ import annotations

import pytest

from app.marketing import postiz_publish as pp
from app.marketing import video_ad_cycle as vac

# --- _resolve_publish_client: the seam that keeps the distinction --------


def test_missing_client_id_is_own_brand_context(monkeypatch):
    """No id on the record = genuine own-brand publish, not a failure."""
    assert vac._resolve_publish_client("") == {}
    assert vac._resolve_publish_client("   ") == {}


def test_real_id_that_resolves_to_nothing_is_none(monkeypatch):
    monkeypatch.setattr("app.marketing.clients_store.resolve_client", lambda c: None)
    monkeypatch.setattr("app.marketing.clients_store.get_client", lambda c: None)
    assert vac._resolve_publish_client("ghost-tenant") is None


def test_lookup_that_raises_is_none(monkeypatch):
    """An unverifiable tenant is not a licence to publish."""

    def boom(_c):
        raise RuntimeError("ledger unreadable")

    monkeypatch.setattr("app.marketing.clients_store.resolve_client", boom)
    monkeypatch.setattr("app.marketing.clients_store.get_client", boom)
    assert vac._resolve_publish_client("jiya-makeover") is None


def test_resolved_client_is_returned(monkeypatch):
    rec = {"id": "jiya-makeover", "niche": "salon"}
    monkeypatch.setattr("app.marketing.clients_store.resolve_client", lambda c: rec)
    assert vac._resolve_publish_client("jiya-makeover") == rec


# --- _publish_one refuses, and no provider is touched --------------------


@pytest.mark.asyncio
async def test_publish_one_refuses_unresolved_tenant(monkeypatch):
    calls = {"postiz": 0, "telegram": 0, "engine": 0}

    async def _spy_postiz(*a, **k):
        calls["postiz"] += 1
        return {"sent": True}

    async def _spy_tg(*a, **k):
        calls["telegram"] += 1
        return {"sent": True}

    monkeypatch.setattr(pp, "publish_video", _spy_postiz, raising=False)
    monkeypatch.setattr(pp, "enabled", lambda: True, raising=False)
    monkeypatch.setattr(vac, "_telegram_send_video", _spy_tg, raising=False)
    # Exercise the REAL resolution chain — the store misses, as in production.
    monkeypatch.setattr("app.marketing.clients_store.resolve_client", lambda c: None)
    monkeypatch.setattr("app.marketing.clients_store.get_client", lambda c: None)
    monkeypatch.setattr(
        "app.marketing.video_production.publish_gate.assert_can_publish",
        lambda rec: {"ok": True},
        raising=False,
    )

    out = await vac._publish_one(
        {
            "id": "va_1",
            "client_id": "ghost-tenant",
            "caption": "hi",
            "video_path": "",
            "status": "approved",
            "revision": 0,
            "approved_version": 0,
            "final_approved": True,
        }
    )

    assert out["any_sent"] is False
    assert out["channels"]["tenant"]["error"] == "unresolved_tenant"
    assert calls == {"postiz": 0, "telegram": 0, "engine": 0}


def test_own_brand_boundary_semantics_unchanged():
    """The Postiz boundary keeps treating an empty client as own-brand."""
    assert pp._is_own_brand({}) is True
    assert pp._is_own_brand(None) is True
    assert pp._is_own_brand({"id": "jiya-makeover", "niche": "salon"}) is False
