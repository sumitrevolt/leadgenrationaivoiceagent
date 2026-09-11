"""
P0 compliance regression tests — Tata SmartFlo must gate on the REAL call_type.

WHY THIS FILE EXISTS
--------------------
`TataSmartfloClient.place_call` used to HARDCODE ``call_type="transactional"``
into both pre-dial gates (dial_gate + ComplianceGate). Transactional =
consented = exempt from DND / DLT-140 / caller-id checks, so a *cold*
promotional call placed through SmartFlo skipped every TRAI/TCCCPR check that
Vobiz applied correctly — a ₹10L-penalty hole introduced by the provider swap.

These tests pin the fix: the real ``call_type`` reaches both gates, and the
Gates are never weakened. They also pin the payload hygiene fixes (Vobiz-only
``answer_url`` dropped, ``CallbackData`` folded into ``custom_identifier``).

No network, no env mutation: every boundary is mocked.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_IMPORT_OK = False
_IMPORT_ERR = ""

try:
    from app.telephony.compliance import CallType
    from app.telephony.tata_smartflo_handler import TataSmartfloClient

    _IMPORT_OK = True
except ImportError as _exc:  # pragma: no cover - import guard only
    _IMPORT_ERR = str(_exc)

pytestmark = pytest.mark.skipif(
    not _IMPORT_OK, reason=f"handler not importable: {_IMPORT_ERR!r}"
)

TEST_NUMBER = "+919876543210"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------
def _ok_response() -> MagicMock:
    """Fake httpx response: HTTP 200 + SmartFlo 'queued' body."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "success": True,
        "message": "Originate successfully queued",
        "ref_id": "ref-test-001",
    }
    resp.text = '{"success": true}'
    return resp


def _decision(allowed: bool, reasons: list[str] | None = None) -> SimpleNamespace:
    """Minimal stand-in for ``ComplianceDecision``."""
    return SimpleNamespace(
        allowed=allowed,
        reasons=reasons or ([] if allowed else ["on_dnd_registry"]),
    )


@pytest.fixture
def client() -> TataSmartfloClient:
    """Configured (but non-networking) SmartFlo client."""
    c = TataSmartfloClient()
    # Credentials come from env/settings; force them so available() is True.
    c.api_token = "unit-test-token"
    c.api_key = "unit-test-key"
    c.did = "918012345678"
    return c


@pytest.fixture(autouse=True)
def _kill_switch_off():
    """Admin kill switch must never be the reason a test passes/fails."""
    with patch(
        "app.telephony.voice_launch.admin_kill_engaged", return_value=False
    ):
        yield


@pytest.fixture(autouse=True)
def mock_post():
    """Patch the outbound HTTP POST. Yields the mock so tests can assert on it."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as m:
        m.return_value = _ok_response()
        yield m


def _payload(mock_post: AsyncMock) -> dict:
    """Extract the JSON body of the (single) outbound POST."""
    assert mock_post.call_count == 1, "expected exactly one outbound POST"
    return mock_post.call_args.kwargs["json"]


def _dial_gate(allowed: bool = True, reason: str = "ok"):
    """Patch context for ``app.telephony.dial_gate.check``."""
    return patch(
        "app.telephony.dial_gate.check", return_value=(allowed, reason)
    )


def _compliance_gate(decision=None, raises: Exception | None = None):
    """Patch context for the ComplianceGate factory used by the handler.

    Returns ``(patch_ctx, recorder)`` — ``recorder.calls`` holds every
    ``(phone, call_type)`` the gate was invoked with.
    """
    recorder = SimpleNamespace(calls=[])

    async def _check(phone, ct):
        recorder.calls.append((phone, ct))
        if raises is not None:
            raise raises
        return decision if decision is not None else _decision(True)

    fake_gate = SimpleNamespace(check=AsyncMock(side_effect=_check))
    ctx = patch("app.telephony.compliance.get_compliance_gate", return_value=fake_gate)
    return ctx, recorder


# ---------------------------------------------------------------------------
# 1) dial_gate receives the REAL call_type
# ---------------------------------------------------------------------------
async def test_promotional_call_type_reaches_dial_gate(client, mock_post):
    """place_call(call_type='promotional') must pass 'promotional' to dial_gate."""
    ctx, _ = _compliance_gate()
    with _dial_gate(True, "ok") as dial, ctx:
        result = await client.place_call(to=TEST_NUMBER, call_type="promotional")

    assert result["status_code"] == 200
    # Second positional arg is the call_type — formerly hardcoded "transactional".
    assert dial.call_args[0][0] == TEST_NUMBER
    assert dial.call_args[0][1] == "promotional"


# ---------------------------------------------------------------------------
# 2) ComplianceGate receives CallType.PROMOTIONAL
# ---------------------------------------------------------------------------
async def test_promotional_call_type_reaches_compliance_gate(client, mock_post):
    ctx, recorder = _compliance_gate()
    with _dial_gate(True, "ok"), ctx:
        await client.place_call(to=TEST_NUMBER, call_type="promotional")

    assert len(recorder.calls) == 1
    phone, ct = recorder.calls[0]
    assert phone == TEST_NUMBER
    assert ct == CallType.PROMOTIONAL
    assert ct.value == "promotional"


# ---------------------------------------------------------------------------
# 3) Blocked promotional call => status_code 0 + NO HTTP dial
# ---------------------------------------------------------------------------
async def test_blocked_promotional_call_never_dials(client, mock_post):
    ctx, _ = _compliance_gate(_decision(False, ["on_dnd_registry", "dlt_not_approved"]))
    with _dial_gate(True, "ok"), ctx:
        result = await client.place_call(to=TEST_NUMBER, call_type="promotional")

    assert result["status_code"] == 0
    assert "compliance_blocked" in (result.get("body") or {}).get("error", "")
    assert "on_dnd_registry" in result["body"]["error"]
    mock_post.assert_not_called()


async def test_blocked_by_dial_gate_never_dials(client, mock_post):
    ctx, _ = _compliance_gate()
    with _dial_gate(False, "not in test-mode allowlist"), ctx:
        result = await client.place_call(to=TEST_NUMBER, call_type="promotional")

    assert result["status_code"] == 0
    assert "compliance_blocked" in result["body"]["error"]
    mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# 4) transactional still resolves to CallType.TRANSACTIONAL
# ---------------------------------------------------------------------------
async def test_transactional_call_type_resolves_to_transactional(client, mock_post):
    ctx, recorder = _compliance_gate()
    with _dial_gate(True, "ok") as dial, ctx:
        await client.place_call(to=TEST_NUMBER, call_type="transactional")

    assert dial.call_args[0][1] == "transactional"
    assert recorder.calls[0][1] == CallType.TRANSACTIONAL


# ---------------------------------------------------------------------------
# 5) skip_compliance=True skips BOTH gates (HTTP IS made)
# ---------------------------------------------------------------------------
async def test_skip_compliance_skips_both_gates(client, mock_post):
    ctx, recorder = _compliance_gate()
    with _dial_gate(True, "ok") as dial, ctx:
        result = await client.place_call(
            to=TEST_NUMBER, call_type="promotional", skip_compliance=True
        )

    assert result["status_code"] == 200
    dial.assert_not_called()
    assert recorder.calls == []
    assert mock_post.call_count == 1


# ---------------------------------------------------------------------------
# 6) enforce_compliance=False skips BOTH gates (HTTP IS made)
# ---------------------------------------------------------------------------
async def test_enforce_compliance_false_skips_both_gates(client, mock_post):
    ctx, recorder = _compliance_gate()
    with _dial_gate(True, "ok") as dial, ctx:
        result = await client.place_call(
            to=TEST_NUMBER, call_type="promotional", enforce_compliance=False
        )

    assert result["status_code"] == 200
    dial.assert_not_called()
    assert recorder.calls == []
    assert mock_post.call_count == 1


# ---------------------------------------------------------------------------
# 7) Payload hygiene — no Vobiz-only junk, CallbackData preserved as call_id
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "bypass",
    [
        {"skip_compliance": True},
        {"enforce_compliance": False},
    ],
)
async def test_payload_has_no_vobiz_only_fields(client, mock_post, bypass):
    """The exact CallManager call shape (call_manager.py:395) must be sanitised."""
    ctx, _ = _compliance_gate()
    with _dial_gate(True, "ok"), ctx:
        await client.place_call(
            to=TEST_NUMBER,
            answer_url="https://api.leadsgenai.in/voice/answer",
            call_type=str("promotional"),
            CallbackData="call-abc-123",
            **bypass,
        )

    payload = _payload(mock_post)

    # Vobiz-only / internal fields must NOT leak into the SmartFlo C2C body.
    for forbidden in ("call_type", "answer_url", "skip_compliance", "CallbackData"):
        assert forbidden not in payload, f"{forbidden} leaked into SmartFlo payload"

    # ...but the correlation id must survive, inside custom_identifier.
    assert payload["custom_identifier"]["call_id"] == "call-abc-123"

    # SmartFlo's own contract is untouched.
    assert payload["customer_number"] == "9876543210"
    assert payload["api_key"] == "unit-test-key"
    assert payload["async"] == 1
    assert payload["caller_id"] == "918012345678"


async def test_callback_data_lowercase_param_also_merged(client, mock_post):
    """The documented ``callback_data`` spelling works identically."""
    with _dial_gate(True, "ok"), _compliance_gate()[0]:
        await client.place_call(
            to=TEST_NUMBER, callback_data="call-xyz-789", skip_compliance=True
        )

    assert _payload(mock_post)["custom_identifier"]["call_id"] == "call-xyz-789"


async def test_callback_data_survives_custom_identifier_truncation(client, mock_post):
    """call_id must be inserted BEFORE the 10-key truncation, not after it."""
    many = {f"k{i}": f"v{i}" for i in range(10)}
    with _dial_gate(True, "ok"), _compliance_gate()[0]:
        await client.place_call(
            to=TEST_NUMBER,
            custom_identifier=many,
            CallbackData="call-survive-1",
            skip_compliance=True,
        )

    custom = _payload(mock_post)["custom_identifier"]
    assert len(custom) == 10  # truncation still enforced
    assert custom["call_id"] == "call-survive-1"


async def test_caller_supplied_call_id_wins(client, mock_post):
    """setdefault semantics: an explicit call_id (telephony_service.py:226) wins."""
    with _dial_gate(True, "ok"), _compliance_gate()[0]:
        await client.place_call(
            to=TEST_NUMBER,
            custom_identifier={"source": "leadgen", "call_id": "theirs"},
            CallbackData="mine",
            skip_compliance=True,
        )

    custom = _payload(mock_post)["custom_identifier"]
    assert custom["call_id"] == "theirs"
    assert custom["source"] == "leadgen"


# ---------------------------------------------------------------------------
# 8) Back-compat: no call_type => transactional (today's behaviour)
# ---------------------------------------------------------------------------
async def test_default_call_type_is_transactional(client, mock_post):
    ctx, recorder = _compliance_gate()
    with _dial_gate(True, "ok") as dial, ctx:
        result = await client.place_call(to=TEST_NUMBER)

    assert result["status_code"] == 200
    assert dial.call_args[0][1] == "transactional"
    assert recorder.calls[0][1] == CallType.TRANSACTIONAL


async def test_unknown_call_type_falls_back_to_transactional(client, mock_post):
    """Parity with vobiz_handler.py:111 — unknown value => TRANSACTIONAL."""
    ctx, recorder = _compliance_gate()
    with _dial_gate(True, "ok"), ctx:
        await client.place_call(to=TEST_NUMBER, call_type="marketing")

    assert recorder.calls[0][1] == CallType.TRANSACTIONAL


# ---------------------------------------------------------------------------
# 9) FAIL-CLOSED: a gate exception blocks EVERY call type (no Vobiz laxness)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("call_type", ["promotional", "transactional"])
async def test_compliance_gate_error_blocks_every_call_type(
    client, mock_post, call_type
):
    """Vobiz only blocks on promo here; SmartFlo keeps strict fail-closed."""
    ctx, _ = _compliance_gate(raises=RuntimeError("gate exploded"))
    with _dial_gate(True, "ok"), ctx:
        result = await client.place_call(to=TEST_NUMBER, call_type=call_type)

    assert result["status_code"] == 0
    assert result["body"]["error"].startswith("compliance_blocked")
    mock_post.assert_not_called()


@pytest.mark.parametrize("call_type", ["promotional", "transactional"])
async def test_dial_gate_error_blocks_every_call_type(client, mock_post, call_type):
    ctx, _ = _compliance_gate()
    with patch(
        "app.telephony.dial_gate.check", side_effect=RuntimeError("dial_gate exploded")
    ), ctx:
        result = await client.place_call(to=TEST_NUMBER, call_type=call_type)

    assert result["status_code"] == 0
    assert "compliance_blocked" in result["body"]["error"]
    mock_post.assert_not_called()


async def test_unconfigured_client_does_not_dial(client, mock_post):
    """Credentials missing => no HTTP, even with gates bypassed."""
    client.api_key = ""
    with _dial_gate(True, "ok") as dial, _compliance_gate()[0]:
        result = await client.place_call(to=TEST_NUMBER, skip_compliance=True)

    assert result["status_code"] == 0
    dial.assert_not_called()  # skip_compliance bypasses the gates entirely
    mock_post.assert_not_called()
