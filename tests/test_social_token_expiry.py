"""Loop-social-11 (2026-07-11): token expiry watcher.

Contract:
- `vault.put(..., expires_at="")` accepts optional ISO expiry. Empty for
  FB/IG/LI gets platform-default 60-day window auto-applied (`meta.token_expiry_source`).
- `is_expired(rec)` = True iff expires_at set and past.
- `is_expiring_soon(rec, days=7)` = True within window.
- `check_token_expiries()` emits `token_expired` ledger event per expired row,
  returns admin summary.
"""

from __future__ import annotations

import datetime
import os
import tempfile

import pytest


@pytest.fixture()
def viso(monkeypatch, tmp_path):
    from app.social_engine import vault as _vault

    monkeypatch.setattr(_vault, "_PATH", str(tmp_path / "tokens.jsonl"))
    monkeypatch.delenv("SOCIAL_TOKEN_KEY", raising=False)
    return _vault


def test_default_expiry_applied_for_facebook(viso):
    viso.put("cA", "facebook", "TOK", account_ref="page1")
    accts = viso.list_accounts("cA")
    assert len(accts) == 1
    assert (accts[0].get("meta") or {}).get("token_expiry_source") == "facebook_default"


def test_no_default_for_x_or_youtube(viso):
    viso.put("cA", "x", "TOK")
    accts = viso.list_accounts("cA")
    assert (accts[0].get("meta") or {}).get("token_expiry_source") is None


def test_is_expired_true_for_past(viso):
    past = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    viso.put("cA", "facebook", "TOK", account_ref="pg", expires_at=past)
    rows = viso._read()
    rec = next(r for r in rows if r.get("platform") == "facebook")
    assert viso.is_expired(rec) is True


def test_is_expiring_soon(viso):
    soon = (datetime.datetime.utcnow() + datetime.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S")
    viso.put("cA", "facebook", "TOK", expires_at=soon)
    rec = next(r for r in viso._read() if r.get("platform") == "facebook")
    assert viso.is_expiring_soon(rec, days=7) is True
    assert viso.is_expired(rec) is False


def test_check_token_expiries_emits_ledger_event(viso, monkeypatch):
    past = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    viso.put("cA", "facebook", "TOK", account_ref="pg", expires_at=past)

    from app.marketing import delivery_ledger

    captured: list[tuple] = []
    monkeypatch.setattr(
        delivery_ledger,
        "log_event",
        lambda cid, ev, detail="", **kw: captured.append((cid, ev, detail)),
    )

    out = viso.check_token_expiries(days=7)
    assert out["expired_count"] == 1
    assert any(cid == "cA" and ev == "token_expired" for cid, ev, _ in captured)


def test_unknown_expiry_is_never_expired(viso):
    viso.put("cA", "x", "TOK")
    rec = next(r for r in viso._read() if r.get("platform") == "x")
    assert viso.is_expired(rec) is False
