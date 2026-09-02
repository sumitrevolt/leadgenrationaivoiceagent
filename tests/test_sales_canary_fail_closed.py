"""Canary must be STRUCTURALLY incapable of a live send.

The `/api/sales-autopilot/run-canary` docstring promises "Never sends live". Before
this suite that promise held only while `policy.dry_run` happened to be True: the
tick branch passed no dry-run flag, so a live-configured policy silently turned the
canary into a real sender. These tests pin the promise to code, not config.

The load-bearing assertion everywhere is the same: the provider function is
monkeypatched to a bomb that fails the test if it is ever awaited.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.platform.sales_autopilot import scheduler as _scheduler
from app.platform.sales_autopilot import send as _send


class ProviderCalled(AssertionError):
    """Raised by the bomb — a live provider call escaped the dry-run boundary."""


@pytest.fixture
def provider_bomb(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Replace the WhatsApp provider with something that must never be awaited."""
    calls = {"n": 0}

    async def _bomb(*a: Any, **k: Any) -> dict[str, Any]:
        calls["n"] += 1
        raise ProviderCalled(f"provider invoked with {a!r} {k!r}")

    monkeypatch.setattr(_send, "_provider_send_whatsapp", _bomb)
    return calls


# --------------------------------------------------------------------------
# 7. Unknown / malformed mode fails CLOSED.
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value,expected",
    [
        (None, False),
        (False, False),
        (True, True),
        ("false", True),  # malformed string -> simulate, NOT live
        ("", True),
        (0, True),
        (1, True),
        (object(), True),
    ],
)
def test_forced_dry_run_coercion_fails_closed(value: Any, expected: bool) -> None:
    assert _send._coerce_forced_dry_run(value) is expected


def test_only_explicit_false_or_none_allows_live() -> None:
    """The permissive set must stay exactly {None, False} — nothing may be added."""
    allows_live = [
        v
        for v in [None, False, True, "false", "no", 0, 1, [], {}, object()]
        if _send._coerce_forced_dry_run(v) is False
    ]
    assert allows_live == [None, False]


# --------------------------------------------------------------------------
# 3 + 4. A live-enabled stored policy is still overridden at the canary boundary.
# --------------------------------------------------------------------------
class _LivePolicy:
    """A policy configured for LIVE sending — the dangerous case."""

    enabled = True
    dry_run = False

    def channel_enabled(self, channel: str) -> bool:
        return True

    def kill(self, _stage: str) -> bool:
        return False

    def canary_batch(self) -> int:
        return 1

    def get(self, key: str, default: Any = None) -> Any:
        return {"provider_timeout_s": 20}.get(key, default)


def _arm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drive send() all the way to the dry-run decision.

    Without this the first version of these tests passed VACUOUSLY: eligibility
    blocked the prospect, send() returned at step 1, and the provider-bomb
    assertion held for the wrong reason. Stubbing eligibility/build/validate
    keeps each test focused on the one thing it is pinning — the dry-run boundary.
    """
    monkeypatch.setattr(_send._elig, "evaluate", lambda *a, **k: {"decision": _send._elig.ELIGIBLE})
    monkeypatch.setattr(
        _send._messages,
        "build",
        lambda *a, **k: {
            "template_family": "initial",
            "template_version": "v1",
            "content_hash": "deadbeef",
            "body": "hello from the canary test",
        },
    )
    monkeypatch.setattr(
        _send._safety,
        "validate",
        lambda _e: {"status": _send._safety.AUTO_APPROVED, "reasons": []},
    )
    monkeypatch.setattr(_send._store, "attempt_exists", lambda _k: False)
    monkeypatch.setattr(_send._store, "record_attempt", lambda _r: None)
    monkeypatch.setattr(_send._store, "update_attempt_status", lambda *a, **k: None)
    monkeypatch.setattr(_send, "_advance_prospect", lambda *a, **k: None)


def _prospect() -> dict[str, Any]:
    return {
        "id": "p-canary-1",
        "phone": "919876543210",
        "status": "new",
        "consent_basis": "legitimate_interest",
        "business_name": "Canary Test Biz",
    }


def test_forced_dry_run_beats_live_policy(provider_bomb, monkeypatch) -> None:
    """force_dry_run=True must win over policy.dry_run=False."""
    _arm(monkeypatch)

    res = asyncio.run(
        _send.send(
            "p-canary-1",
            channel="whatsapp",
            pol=_LivePolicy(),
            prospect=_prospect(),
            force_dry_run=True,
        )
    )

    assert provider_bomb["n"] == 0, "provider was called despite force_dry_run=True"
    assert res["dry_run"] is True
    assert res["forced_dry_run"] is True
    assert res["outcome"] == _send.SIMULATED


def test_malformed_mode_also_beats_live_policy(provider_bomb, monkeypatch) -> None:
    """A malformed force_dry_run value must simulate, not send."""
    _arm(monkeypatch)

    res = asyncio.run(
        _send.send(
            "p-canary-1",
            channel="whatsapp",
            pol=_LivePolicy(),
            prospect=_prospect(),
            force_dry_run="false",  # malformed
        )
    )

    assert provider_bomb["n"] == 0
    assert res["dry_run"] is True
    assert res["outcome"] == _send.SIMULATED


# --------------------------------------------------------------------------
# 5. Normal (non-canary) execution is UNCHANGED — the guard must not over-block.
# --------------------------------------------------------------------------
def test_non_canary_live_path_still_reaches_provider(monkeypatch) -> None:
    """Without force_dry_run, a live policy must still be able to send.

    This is the anti-regression: a fix that made everything dry-run would pass
    every other test in this file while silently disabling the product.
    """
    seen: dict[str, Any] = {}

    async def _capture(contact: str, body: str, timeout_s: float) -> dict[str, Any]:
        seen["contact"] = contact
        return {"sent": True, "mode": "live"}

    monkeypatch.setattr(_send, "_provider_send_whatsapp", _capture)
    _arm(monkeypatch)

    res = asyncio.run(
        _send.send(
            "p-canary-1",
            channel="whatsapp",
            pol=_LivePolicy(),
            prospect=_prospect(),
        )
    )

    assert seen.get("contact") == "919876543210"
    assert res["outcome"] == _send.SENT
    assert res["dry_run"] is False
    assert res["forced_dry_run"] is False


# --------------------------------------------------------------------------
# 2 + 6. Tick canary never sends live, and records the mode in its artifact.
# --------------------------------------------------------------------------
def test_tick_canary_never_sends_live(provider_bomb, monkeypatch) -> None:
    """run_tick(force_dry_run=True) must simulate every send on the tick."""
    monkeypatch.setattr(_scheduler._policy_mod, "get_policy", lambda: _LivePolicy())
    monkeypatch.setattr(_scheduler, "_acquire_lock", lambda: "tok")
    monkeypatch.setattr(_scheduler, "_release_lock", lambda _t: None, raising=False)
    monkeypatch.setattr(_scheduler._store, "record_tick", lambda _r: None)
    monkeypatch.setattr(
        _scheduler,
        "_new_outreach_targets",
        lambda _pol, _batch: [{"prospect": _prospect(), "step": "initial", "channel": "whatsapp"}],
    )
    monkeypatch.setattr(_scheduler._followups, "due_followups", lambda *a, **k: [])
    _arm(monkeypatch)

    out = asyncio.run(_scheduler.run_tick(limit=1, force_dry_run=True))

    assert provider_bomb["n"] == 0, "tick canary reached the live provider"
    # 6. audit/result explicitly records canary mode
    assert out["forced_dry_run"] is True
    assert out["dry_run"] is True


def test_tick_default_is_not_forced(monkeypatch) -> None:
    """Default run_tick() must NOT force dry-run (scheduler behaviour unchanged)."""
    monkeypatch.setattr(_scheduler._policy_mod, "get_policy", lambda: _LivePolicy())
    monkeypatch.setattr(_scheduler, "_acquire_lock", lambda: "tok")
    monkeypatch.setattr(_scheduler, "_release_lock", lambda _t: None, raising=False)
    monkeypatch.setattr(_scheduler._store, "record_tick", lambda _r: None)
    monkeypatch.setattr(_scheduler, "_new_outreach_targets", lambda _pol, _batch: [])
    monkeypatch.setattr(_scheduler._followups, "due_followups", lambda *a, **k: [])

    out = asyncio.run(_scheduler.run_tick(limit=1))

    assert out["forced_dry_run"] is False
    assert out["dry_run"] is False


# --------------------------------------------------------------------------
# 1. Prospect-specific canary path (regression guard on existing behaviour).
# --------------------------------------------------------------------------
def test_single_prospect_canary_never_sends_live(provider_bomb, monkeypatch) -> None:
    _arm(monkeypatch)

    res = asyncio.run(
        _send.send(
            "p-canary-1",
            channel="whatsapp",
            pol=_LivePolicy(),
            prospect=_prospect(),
            force_dry_run=True,
        )
    )
    assert provider_bomb["n"] == 0
    assert res["outcome"] == _send.SIMULATED


# --------------------------------------------------------------------------
# 8. Admin authorization is still required on the canary endpoint.
# --------------------------------------------------------------------------
def test_run_canary_still_requires_admin() -> None:
    from app.api import sales_autopilot_admin as mod

    deps = mod.run_canary.__defaults__ or ()
    assert any(getattr(d, "dependency", None) is not None for d in deps), (
        "run_canary lost its Depends(require_admin) guard"
    )
