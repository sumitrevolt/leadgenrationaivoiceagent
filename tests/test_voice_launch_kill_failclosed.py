"""Fail-closed contract for the voice-launch admin kill switch.

RED BY DESIGN. The reader currently swallows every failure
(`except Exception: return False`), so a missing, unreadable or malformed
kill file DISENGAGES the kill — the opposite of what an emergency switch
must do. These tests describe the required contract; the implementation
lands in a separate bounded batch.

Locked contract (proved from source, see AdminKillStatus spec):
  ENV VOICE_LAUNCH_KILL is the FINAL override; the file is a FALLBACK.
  Writer emits exactly {"kill": <bool>} and nothing else.
  Every file-layer failure must yield engaged=True with a safe reason.

No real phone number, provider credential, network call or queue job.
"""

from __future__ import annotations

import json
import os

import pytest

from app.telephony import voice_launch as vl

TRUE_TOKENS = ("1", "true", "yes", "on", " TRUE ", "On")
FALSE_TOKENS = ("0", "false", "no", "off", " FALSE ", "Off")

# Payloads the authorized writer can actually produce.
VALID_PAYLOADS = ('{"kill": true}', '{"kill": false}')

# Everything else is INVALID_SCHEMA. Integers must never pass as booleans.
INVALID_PAYLOADS = (
    "{}",
    '{"kill": 1}',
    '{"kill": 0}',
    '{"kill": "true"}',
    '{"kill": "false"}',
    "[]",
    "null",
    '"off"',
)


@pytest.fixture
def kill_file(tmp_path, monkeypatch):
    """Point the kill authority at a temp file and clear the ENV override."""
    p = tmp_path / "voice_launch_kill.json"
    monkeypatch.setenv("VOICE_LAUNCH_KILL_FILE", str(p))
    monkeypatch.delenv("VOICE_LAUNCH_KILL", raising=False)
    return p


def _status():
    """The structured API this batch requires. Absent today -> red."""
    fn = getattr(vl, "admin_kill_status", None)
    assert fn is not None, "admin_kill_status() is not implemented yet"
    return fn()


# --------------------------------------------------------- file-layer failures


def test_missing_file_engages_kill(kill_file):
    assert not kill_file.exists()
    st = _status()
    assert st.engaged is True
    assert st.reason == "MISSING"
    assert vl.admin_kill_engaged() is True


def test_unreadable_file_engages_kill(kill_file, monkeypatch):
    kill_file.write_text('{"kill": false}', encoding="utf-8")

    def _boom(*a, **k):
        raise PermissionError("denied")

    # monkeypatch, not chmod: Windows permission bits do not model this.
    monkeypatch.setattr(type(kill_file), "read_text", _boom, raising=False)
    st = _status()
    assert st.engaged is True
    assert st.reason == "UNREADABLE"


def test_malformed_json_engages_kill(kill_file):
    kill_file.write_text('{"kill": tru', encoding="utf-8")
    st = _status()
    assert st.engaged is True
    assert st.reason == "MALFORMED"


@pytest.mark.parametrize("payload", INVALID_PAYLOADS)
def test_invalid_schema_engages_kill(kill_file, payload):
    """Includes {"kill": 1} / {"kill": 0} — integers are not safety booleans."""
    kill_file.write_text(payload, encoding="utf-8")
    st = _status()
    assert st.engaged is True, f"{payload} was accepted"
    assert st.reason == "INVALID_SCHEMA"


@pytest.mark.parametrize("payload", VALID_PAYLOADS)
def test_valid_writer_payloads_are_accepted(kill_file, payload):
    """The strict reader must not reject what the authorized writer emits."""
    kill_file.write_text(payload, encoding="utf-8")
    st = _status()
    assert st.engaged is json.loads(payload)["kill"]
    assert st.source == "FILE"
    assert st.reason in ("FILE_ENGAGED", "FILE_DISENGAGED")


def test_writer_output_round_trips_through_strict_reader(kill_file):
    for on in (True, False):
        assert vl.set_kill(on) is True
        assert _status().engaged is on


# ------------------------------------------------------------ path validation


def test_relative_production_path_engages_kill(monkeypatch, kill_file):
    monkeypatch.setenv("VOICE_LAUNCH_KILL_FILE", "data/voice_launch_kill.json")
    monkeypatch.setenv("APP_ENV", "production")
    st = _status()
    assert st.engaged is True
    assert st.reason in ("INVALID_PATH", "OUTSIDE_RUNTIME_ROOT")


def test_checkout_local_production_path_engages_kill(monkeypatch, kill_file):
    from app.platform import runtime_data as rd

    inside = rd._repo_root() / "data" / "voice_launch_kill.json"
    monkeypatch.setenv("VOICE_LAUNCH_KILL_FILE", str(inside))
    monkeypatch.setenv("APP_ENV", "production")
    st = _status()
    assert st.engaged is True
    assert st.reason == "OUTSIDE_RUNTIME_ROOT"


# ------------------------------------------------------- environment override


@pytest.mark.parametrize("tok", TRUE_TOKENS)
def test_env_true_overrides_file_false(kill_file, monkeypatch, tok):
    kill_file.write_text('{"kill": false}', encoding="utf-8")
    monkeypatch.setenv("VOICE_LAUNCH_KILL", tok)
    st = _status()
    assert st.engaged is True
    assert st.source == "ENV"
    assert st.reason == "ENV_ENGAGED"


@pytest.mark.parametrize("tok", FALSE_TOKENS)
def test_env_false_overrides_file_true(kill_file, monkeypatch, tok):
    """Candidate A: ENV is final, the file is only a fallback.

    This disengages THIS layer only — every other gate still applies, so the
    test deliberately does not assert that a call proceeds.
    """
    kill_file.write_text('{"kill": true}', encoding="utf-8")
    monkeypatch.setenv("VOICE_LAUNCH_KILL", tok)
    st = _status()
    assert st.engaged is False
    assert st.source == "ENV"
    assert st.reason == "ENV_DISENGAGED"


@pytest.mark.parametrize("tok", ("maybe", "kill", "2", "-", "yes please"))
def test_invalid_env_token_engages_kill(kill_file, monkeypatch, tok):
    """A non-empty unparseable token must NOT fall through to the file."""
    kill_file.write_text('{"kill": false}', encoding="utf-8")
    monkeypatch.setenv("VOICE_LAUNCH_KILL", tok)
    st = _status()
    assert st.engaged is True
    assert st.reason == "INVALID_ENV_VALUE"


@pytest.mark.parametrize("tok", ("", "   "))
def test_blank_env_falls_back_to_file(kill_file, monkeypatch, tok):
    kill_file.write_text('{"kill": true}', encoding="utf-8")
    monkeypatch.setenv("VOICE_LAUNCH_KILL", tok)
    st = _status()
    assert st.source == "FILE"
    assert st.engaged is True


def test_status_never_leaks_raw_values(kill_file, monkeypatch):
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "super-secret-token")
    blob = repr(_status())
    assert "super-secret-token" not in blob
    assert str(kill_file) not in blob


# ------------------------------------------------------- read-only consumers


def test_status_object_is_never_used_as_a_boolean(kill_file):
    """`bool(AdminKillStatus(engaged=False, ...))` is truthy — a real trap.

    owner_os.py wraps the call in bool(), so returning the object there would
    report "engaged" forever. Engagement must come from `.engaged`.
    """
    kill_file.write_text('{"kill": false}', encoding="utf-8")
    st = _status()
    assert st.engaged is False
    assert bool(st) is True, "dataclass is truthy — callers must use .engaged"


@pytest.mark.asyncio
async def test_launch_status_exposes_reason(kill_file):
    kill_file.write_text('{"kill": tru', encoding="utf-8")
    snap = await vl.launch_status()
    assert snap["admin_kill_engaged"] is True
    assert snap.get("admin_kill_source") == "FILE"
    assert snap.get("admin_kill_reason") == "MALFORMED"


# ------------------------------------------------ REAL execution-gate harness
#
# A loader-only assertion cannot show that no call is placed. These tests invoke
# the actual async task and let it run until it either refuses at the kill gate
# or crosses it. `error == "admin_kill_switch"` is the authoritative attribution
# (three later gates could also produce zero provider calls); the provider
# counter is collateral proof.


def _harness(monkeypatch):
    """Patch every boundary around the real kill gate and return the recorders.

    Two patch categories, deliberately kept apart: `vl.*` names are reached as
    module attributes, but VobizClient and start_stream_call are imported INSIDE
    _dial_vobiz_campaign, so they must be patched at their defining modules.
    """
    from app.telephony import voice_launch as vl

    events: list[str] = []
    states: list = []
    provider_calls: list = []
    counters = dict.fromkeys(
        (
            "client_created",
            "available",
            "kill",
            "recording",
            "circuit",
            "eligibility",
            "reservation",
            "provider",
        ),
        0,
    )

    class FakeVobizClient:
        def __init__(self, *a, **k):
            counters["client_created"] += 1
            events.append("vobiz_client_created")

        def available(self) -> bool:
            counters["available"] += 1
            events.append("vobiz_available")
            return True

    # Spy that still runs the REAL reader — mocking it True would hide the
    # fail-open behaviour this test exists to expose.
    original_kill = vl.admin_kill_engaged

    def kill_spy() -> bool:
        counters["kill"] += 1
        events.append("task_kill_evaluated")
        return original_kill()

    async def fake_set_campaign_state(state):
        states.append(state)
        events.append(f"campaign_state:{state}")

    def fake_recording_gate(*a, **k):
        counters["recording"] += 1
        events.append("recording_allowed")
        return True, "recording_not_required"

    async def fake_circuit_open(*a, **k):
        counters["circuit"] += 1
        events.append("circuit_closed")
        return False  # False == breaker NOT tripped

    async def fake_eligibility(*a, **k):
        counters["eligibility"] += 1
        events.append("eligibility_allowed")
        return vl.EligibilityResult(True)

    async def fake_reservation(*a, **k):
        counters["reservation"] += 1
        events.append("slot_reserved")
        return vl.SlotReservation(True, 0, 100)

    async def fake_start_stream_call(*a, **k):
        counters["provider"] += 1
        provider_calls.append((a, k))
        events.append("provider_called")
        return {"placed": False}  # keeps db=object() valid

    monkeypatch.setattr(vl, "campaign_enabled", lambda *a, **k: True)
    monkeypatch.setattr(vl, "admin_kill_engaged", kill_spy)
    monkeypatch.setattr(vl, "set_campaign_state", fake_set_campaign_state)
    monkeypatch.setattr(vl, "recording_gate_ok", fake_recording_gate)
    monkeypatch.setattr(vl, "circuit_open", fake_circuit_open)
    monkeypatch.setattr(vl, "is_lead_eligible_for_voice_call", fake_eligibility)
    monkeypatch.setattr(vl, "reserve_call_slot", fake_reservation)
    monkeypatch.setattr("app.telephony.vobiz_handler.VobizClient", FakeVobizClient, raising=False)
    monkeypatch.setattr(
        "app.api.telephony_vobiz.start_stream_call",
        fake_start_stream_call,
        raising=False,
    )
    return events, states, counters, provider_calls


async def _run_campaign(monkeypatch):
    from types import SimpleNamespace

    from app.tasks.calling import _dial_vobiz_campaign

    events, states, counters, provider_calls = _harness(monkeypatch)
    # p10 = re.sub(r"\D", "", (p.phone or "").strip())[-10:]  -> "0000000000"
    prospect = SimpleNamespace(id="test-prospect", phone="0000000000")
    result = await _dial_vobiz_campaign(
        object(),  # db — untouched while provider returns placed=False
        [prospect],
        False,  # dry_run MUST be False or the kill gate is skipped
        "promotional",
        "test-client",
        True,  # platform=True -> p.niche never read, client_id=None
    )
    return result, events, states, counters, provider_calls


def _diag(result, events, states, counters, provider_calls) -> str:
    return (
        f"\nresult={result}\nevents={events}\nstates={states}"
        f"\ncounters={counters}\nprovider_calls={provider_calls}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [None, '{"kill": tru', "{}", '{"kill": 1}'],
    ids=["missing", "malformed", "invalid_schema", "invalid_schema_int"],
)
async def test_real_gate_refuses_when_kill_authority_unavailable(kill_file, monkeypatch, payload):
    if payload is not None:
        kill_file.write_text(payload, encoding="utf-8")

    result, events, states, counters, provider_calls = await _run_campaign(monkeypatch)
    d = _diag(result, events, states, counters, provider_calls)

    # The task actually reached the kill decision (not stopped earlier).
    assert counters["client_created"] == 1, d
    assert counters["available"] == 1, d
    assert counters["kill"] == 1, d

    # Authoritative attribution: only the kill gate emits this error.
    assert result.get("error") == "admin_kill_switch", d
    assert result["ok"] == 0, d
    assert result["placed_ids"] == [], d
    assert "paused_by_admin" in str(result["state"]).lower(), d
    assert states == [vl.CampaignState.PAUSED_BY_ADMIN], d

    # Nothing past the kill gate may run.
    assert counters["recording"] == 0, d
    assert counters["circuit"] == 0, d
    assert counters["eligibility"] == 0, d
    assert counters["reservation"] == 0, d
    assert counters["provider"] == 0, d


@pytest.mark.asyncio
async def test_real_gate_refuses_on_invalid_env_token(kill_file, monkeypatch):
    """A non-empty unparseable token must engage, not fall through to the file."""
    kill_file.write_text('{"kill": false}', encoding="utf-8")
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "maybe")

    result, events, states, counters, provider_calls = await _run_campaign(monkeypatch)
    d = _diag(result, events, states, counters, provider_calls)

    assert counters["kill"] == 1, d
    assert result.get("error") == "admin_kill_switch", d
    assert states == [vl.CampaignState.PAUSED_BY_ADMIN], d
    assert counters["provider"] == 0, d


# ------------------------------------------------------------ atomic writer
#
# set_kill() wrote straight into the destination with p.write_text(). An
# interrupted write leaves truncated JSON, and truncated JSON is exactly the
# state the strict reader now calls MALFORMED — safe, but it means a crash
# mid-flip silently destroys an operator's kill state. The write must land
# atomically: same-directory temp, fsync, os.replace.


def _kill_dir_entries(p):
    return sorted(x.name for x in p.parent.iterdir())


def test_writer_emits_exact_schema(kill_file):
    assert vl.set_kill(True) is True
    assert json.loads(kill_file.read_text(encoding="utf-8")) == {"kill": True}
    assert vl.set_kill(False) is True
    assert json.loads(kill_file.read_text(encoding="utf-8")) == {"kill": False}


def test_writer_output_is_read_back_by_the_strict_reader(kill_file):
    for on in (True, False):
        assert vl.set_kill(on) is True
        st = _status()
        assert st.engaged is on
        assert st.source == "FILE"


def test_writer_replaces_an_existing_valid_file(kill_file):
    kill_file.write_text('{"kill": true}', encoding="utf-8")
    assert vl.set_kill(False) is True
    assert _status().engaged is False


def test_writer_leaves_no_temp_artifact_on_success(kill_file):
    assert vl.set_kill(True) is True
    leftovers = [n for n in _kill_dir_entries(kill_file) if n != kill_file.name]
    assert leftovers == [], leftovers


def test_temp_file_is_created_in_the_target_directory(kill_file, monkeypatch):
    """A temp on another filesystem makes os.replace non-atomic (or fail)."""
    seen: list = []
    real_replace = os.replace

    def spy_replace(src, dst, *a, **k):
        seen.append((str(src), str(dst)))
        return real_replace(src, dst, *a, **k)

    monkeypatch.setattr(vl.os, "replace", spy_replace, raising=False)
    assert vl.set_kill(True) is True
    assert seen, "os.replace was never called — the write is not atomic"
    src, dst = seen[-1]
    assert os.path.dirname(src) == os.path.dirname(dst)
    assert dst == str(kill_file)


def test_write_failure_preserves_the_previous_file(kill_file, monkeypatch):
    """A failed serialise/write must never damage the state already on disk."""
    kill_file.write_text('{"kill": true}', encoding="utf-8")

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(vl.json, "dumps", boom, raising=False)
    assert vl.set_kill(False) is False
    assert json.loads(kill_file.read_text(encoding="utf-8")) == {"kill": True}
    assert _status().engaged is True


def test_replace_failure_preserves_the_previous_file(kill_file, monkeypatch):
    kill_file.write_text('{"kill": true}', encoding="utf-8")

    def boom(*a, **k):
        raise OSError("replace failed")

    monkeypatch.setattr(vl.os, "replace", boom, raising=False)
    assert vl.set_kill(False) is False
    # Durable authority untouched, and no half-written temp may be authoritative.
    assert json.loads(kill_file.read_text(encoding="utf-8")) == {"kill": True}
    assert _status().engaged is True


def test_failed_replace_does_not_leave_a_temp_behind(kill_file, monkeypatch):
    kill_file.write_text('{"kill": true}', encoding="utf-8")
    monkeypatch.setattr(
        vl.os,
        "replace",
        lambda *a, **k: (_ for _ in ()).throw(OSError("x")),
        raising=False,
    )
    vl.set_kill(False)
    leftovers = [n for n in _kill_dir_entries(kill_file) if n != kill_file.name]
    assert leftovers == [], leftovers


def test_target_is_never_partially_visible(kill_file, monkeypatch):
    """Between calls the destination must always parse as a valid payload."""
    kill_file.write_text('{"kill": true}', encoding="utf-8")
    observed: list = []
    real_replace = os.replace

    def watch(src, dst, *a, **k):
        # Just before the swap the destination must still be the OLD valid doc.
        observed.append(json.loads(open(dst, encoding="utf-8").read()))
        return real_replace(src, dst, *a, **k)

    monkeypatch.setattr(vl.os, "replace", watch, raising=False)
    assert vl.set_kill(False) is True
    assert observed == [{"kill": True}], observed
    assert json.loads(kill_file.read_text(encoding="utf-8")) == {"kill": False}


def test_invalid_production_path_performs_zero_mutation(tmp_path, monkeypatch):
    """Production must validate BEFORE touching the filesystem."""
    from app.platform import runtime_data as rd

    inside = rd._repo_root() / "data" / "vl_kill_probe.json"
    monkeypatch.setenv("VOICE_LAUNCH_KILL_FILE", str(inside))
    monkeypatch.setenv("APP_ENV", "production")
    before = inside.exists()
    assert vl.set_kill(True) is False
    assert inside.exists() is before, "production write escaped into the checkout"
