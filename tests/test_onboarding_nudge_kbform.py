"""KB self-serve gap fixes (customer-delivery, 2026-07-05).

Two AUDIT-VERIFIED gaps closed:

(1) SPOF re-nudge — the WhatsApp business-info interview was sent EXACTLY ONCE at
    onboarding. If WA infra was down that day (exactly what happened to the real
    "jiya makeover" client — WAHA linked days later), the client stayed
    `awaiting_kb_interview=True` forever, silently. `_renudge_awaiting_interviews`
    re-sends the interview to active-awaiting clients, capped:
      - max 3 re-nudges per client (`_RENUDGE_MAX`)
      - min 24h apart (`_RENUDGE_MIN_HOURS`)
      - gated `KB_INTERVIEW_RENUDGE` (default ON — bug-fix of promised behaviour)
    Time is injected by monkeypatching `onboarding._now_utc`.

(2) Portal self-serve KB entry — `POST /api/customer/kb-info` lets a customer feed
    business info straight from the portal (not only via the one WhatsApp reply):
    writes to KB namespace `client:<id>` with source `portal:kb_info`, clears the
    awaiting flag. client_id comes from the JWT (`require_customer`) => a customer
    can only ever write its OWN namespace (IDOR-safe).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

# --------------------------------------------------------------------------- #
# Gap 1 — re-nudge sweep (24h gap + max-3 cap + flag gate)                     #
# --------------------------------------------------------------------------- #


def _patch_state_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app.marketing import onboarding

    monkeypatch.setattr(onboarding, "_NUDGE_STATE_FILE", str(tmp_path / "nudges.json"))


def _capture_sends(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace the WhatsApp send with an always-success recorder. Returns the log."""
    from app.marketing import onboarding

    sent: list[str] = []

    async def _fake_send(phone: str, msg: str) -> bool:
        sent.append(phone)
        return True

    monkeypatch.setattr(onboarding, "_send_whatsapp", _fake_send)
    return sent


@pytest.mark.asyncio
async def test_renudge_sends_once_then_respects_24h_gap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.marketing import clients_store, onboarding

    clients_store._CLIENTS_FILE = lambda: str(tmp_path / "clients.jsonl")
    _patch_state_file(monkeypatch, tmp_path)
    monkeypatch.setenv("KB_INTERVIEW_RENUDGE", "1")
    sent = _capture_sends(monkeypatch)

    c = clients_store.add_client(business_name="Stuck Biz", niche="general", phone="9800000001")
    clients_store.update_client(c["id"], awaiting_kb_interview=True)

    t0 = datetime(2026, 7, 5, 9, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(onboarding, "_now_utc", lambda: t0)

    r1 = await onboarding._renudge_awaiting_interviews()
    assert r1["renudged"] == 1
    assert len(sent) == 1

    # Same day, only a few hours later -> still inside the 24h window -> NO resend.
    monkeypatch.setattr(onboarding, "_now_utc", lambda: t0 + timedelta(hours=5))
    r2 = await onboarding._renudge_awaiting_interviews()
    assert r2["renudged"] == 0
    assert len(sent) == 1

    # Just past 24h -> allowed again.
    monkeypatch.setattr(onboarding, "_now_utc", lambda: t0 + timedelta(hours=24, minutes=1))
    r3 = await onboarding._renudge_awaiting_interviews()
    assert r3["renudged"] == 1
    assert len(sent) == 2


@pytest.mark.asyncio
async def test_renudge_caps_at_three_total(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app.marketing import clients_store, onboarding

    clients_store._CLIENTS_FILE = lambda: str(tmp_path / "clients.jsonl")
    _patch_state_file(monkeypatch, tmp_path)
    monkeypatch.setenv("KB_INTERVIEW_RENUDGE", "1")
    sent = _capture_sends(monkeypatch)

    c = clients_store.add_client(business_name="Stubborn Biz", niche="general", phone="9800000002")
    clients_store.update_client(c["id"], awaiting_kb_interview=True)

    base = datetime(2026, 7, 5, 9, 0, tzinfo=timezone.utc)
    # Advance 25h each round so the 24h gap never blocks — only the max-3 cap should.
    for i in range(6):
        monkeypatch.setattr(onboarding, "_now_utc", lambda i=i: base + timedelta(hours=25 * i))
        await onboarding._renudge_awaiting_interviews()

    assert len(sent) == onboarding._RENUDGE_MAX == 3

    # State reflects the cap; a further sweep is a no-op (capped counter).
    r = await onboarding._renudge_awaiting_interviews()
    assert r["renudged"] == 0
    assert r["capped"] == 1


@pytest.mark.asyncio
async def test_renudge_flag_off_is_inert(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app.marketing import clients_store, onboarding

    clients_store._CLIENTS_FILE = lambda: str(tmp_path / "clients.jsonl")
    _patch_state_file(monkeypatch, tmp_path)
    monkeypatch.setenv("KB_INTERVIEW_RENUDGE", "0")
    sent = _capture_sends(monkeypatch)

    c = clients_store.add_client(business_name="Off Biz", niche="general", phone="9800000003")
    clients_store.update_client(c["id"], awaiting_kb_interview=True)

    r = await onboarding._renudge_awaiting_interviews()
    assert r.get("skipped") == "KB_INTERVIEW_RENUDGE off"
    assert len(sent) == 0


@pytest.mark.asyncio
async def test_renudge_skips_clients_not_awaiting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.marketing import clients_store, onboarding

    clients_store._CLIENTS_FILE = lambda: str(tmp_path / "clients.jsonl")
    _patch_state_file(monkeypatch, tmp_path)
    monkeypatch.setenv("KB_INTERVIEW_RENUDGE", "1")
    sent = _capture_sends(monkeypatch)

    # awaiting flag NOT set -> must never be nudged.
    clients_store.add_client(business_name="Seeded Biz", niche="general", phone="9800000004")
    r = await onboarding._renudge_awaiting_interviews()
    assert r["renudged"] == 0
    assert len(sent) == 0


@pytest.mark.asyncio
async def test_capture_clears_renudge_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Once the interview is captured, the re-nudge record is dropped so a client
    who replies late doesn't leave stale counter state."""
    from app.marketing import clients_store, onboarding

    clients_store._CLIENTS_FILE = lambda: str(tmp_path / "clients.jsonl")
    _patch_state_file(monkeypatch, tmp_path)
    monkeypatch.setenv("KB_INTERVIEW_RENUDGE", "1")
    _capture_sends(monkeypatch)

    class _FakeKB:
        def add_documents(self, docs, source="", namespace=""):
            return len(docs)

    monkeypatch.setattr("app.voice_agent.knowledge_base.get_knowledge_base", lambda: _FakeKB())

    c = clients_store.add_client(business_name="Reply Biz", niche="general", phone="9800000005")
    clients_store.update_client(c["id"], awaiting_kb_interview=True)

    t0 = datetime(2026, 7, 5, 9, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(onboarding, "_now_utc", lambda: t0)
    await onboarding._renudge_awaiting_interviews()
    assert onboarding._load_nudge_state().get(c["id"])  # record exists

    # Now the client replies -> capture -> state cleared.
    await onboarding.try_capture_onboarding_reply(
        "9800000005", "Hum makeover services dete hain Nagpur me, USP: bridal expert"
    )
    assert c["id"] not in onboarding._load_nudge_state()


# --------------------------------------------------------------------------- #
# Gap 2 — portal self-serve KB route (namespace + flag clear + IDOR)          #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_kb_info_writes_client_namespace_and_clears_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.api import customer_dashboard as cd
    from app.marketing import clients_store

    clients_store._CLIENTS_FILE = lambda: str(tmp_path / "clients.jsonl")
    c = clients_store.add_client(
        business_name="Jiya Makeover", niche="beauty_makeover", phone="8712928847"
    )
    cid = c["id"]
    clients_store.update_client(cid, awaiting_kb_interview=True)

    kb_calls: list[dict[str, Any]] = []

    class _FakeKB:
        def add_documents(self, docs, source=None, namespace="default"):
            kb_calls.append({"docs": docs, "source": source, "namespace": namespace})
            return len(docs)

    monkeypatch.setattr("app.voice_agent.knowledge_base.get_knowledge_base", lambda: _FakeKB())

    body = cd.KbInfoIn(text="Bridal makeover + hair spa, Nagpur. USP: 10 saal ka experience.")
    # client_id injected as the resolved JWT sub (require_customer output).
    res = cd.customer_kb_info(body, client_id=cid)

    assert res["ok"] is True
    assert res["chunks_added"] == 1
    assert res["namespace"] == f"client:{cid}"
    assert len(kb_calls) == 1
    assert kb_calls[0]["namespace"] == f"client:{cid}"
    assert kb_calls[0]["source"] == "portal:kb_info"

    after = clients_store.get_client(cid)
    assert not after.get("awaiting_kb_interview")


@pytest.mark.asyncio
async def test_kb_info_is_idor_safe_writes_only_own_namespace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The route takes its client_id ONLY from require_customer (JWT sub). Even if
    another client's id existed, the authed customer's token can only produce its
    own id -> the KB write always targets the caller's own namespace, never a
    victim's. We assert the write namespace == the authed id, not the other id."""
    from app.api import customer_dashboard as cd
    from app.marketing import clients_store

    clients_store._CLIENTS_FILE = lambda: str(tmp_path / "clients.jsonl")
    me = clients_store.add_client(business_name="Me Biz", niche="general", phone="9800000010")
    victim = clients_store.add_client(
        business_name="Victim Biz", niche="general", phone="9800000011"
    )
    clients_store.update_client(victim["id"], awaiting_kb_interview=True)

    kb_calls: list[dict[str, Any]] = []

    class _FakeKB:
        def add_documents(self, docs, source=None, namespace="default"):
            kb_calls.append({"namespace": namespace})
            return len(docs)

    monkeypatch.setattr("app.voice_agent.knowledge_base.get_knowledge_base", lambda: _FakeKB())

    body = cd.KbInfoIn(text="Poaching victim ki KB likhne ki koshish (should not happen).")
    # Authenticated as `me` -> require_customer resolves my id, not victim's.
    cd.customer_kb_info(body, client_id=me["id"])

    assert kb_calls[0]["namespace"] == f"client:{me['id']}"
    assert kb_calls[0]["namespace"] != f"client:{victim['id']}"
    # Victim's awaiting flag untouched — I could not clear someone else's flag.
    assert clients_store.get_client(victim["id"]).get("awaiting_kb_interview") is True


@pytest.mark.asyncio
async def test_kb_info_rejects_too_short_text() -> None:
    """Model-level guard: <5 chars is rejected before any KB write (pydantic)."""
    import pydantic

    from app.api import customer_dashboard as cd

    with pytest.raises(pydantic.ValidationError):
        cd.KbInfoIn(text="hi")


@pytest.mark.asyncio
async def test_kb_info_route_registered_and_no_duplicate() -> None:
    """FastAPI first-route-wins guard: /api/customer/kb-info exists exactly once."""
    from app.api import customer_dashboard as cd

    matches = [
        r
        for r in cd.router.routes
        if getattr(r, "path", "") == "/api/customer/kb-info"
        and "POST" in getattr(r, "methods", set())
    ]
    assert len(matches) == 1
