"""Smoke test for hot_queue_owner_pack module.

ADR-OWNER-1: ensures the new build_owner_pack engine is importable + idempotent
+ safe when reply_agent.hot_queue() returns empty (no flakes) and never raises.
"""
import asyncio
import os
import sys
import tempfile

import pytest

# Allow running from repo root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_module_imports():
    from app.platform import hot_queue_owner_pack

    assert hasattr(hot_queue_owner_pack, "build_owner_pack")
    assert callable(hot_queue_owner_pack.build_owner_pack)
    assert hasattr(hot_queue_owner_pack, "_push_ntfy")


def test_build_owner_pack_empty_rows_is_ok(tmp_path, monkeypatch):
    """Empty hot_queue must still return ok + write empty CSV (not crash)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    from app.platform import hot_queue_owner_pack, reply_agent

    def fake_empty(limit=200, scope="boss"):
        return []

    monkeypatch.setattr(reply_agent, "hot_queue", fake_empty)

    r = asyncio.run(hot_queue_owner_pack.build_owner_pack(limit=200, push_ntfy=False))
    assert r.get("ok") is True, r
    assert r.get("rows") == 0
    assert os.path.exists(r.get("csv"))


def test_build_owner_pack_with_rows_writes_csv_and_md(tmp_path, monkeypatch):
    """3 fake rows → 3 CSV lines + a non-empty MD file."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    from app.platform import hot_queue_owner_pack, reply_agent

    sample = [
        {
            "hq_id": "x1",
            "channel": "calling_flagged",
            "intent": "interested",
            "from": "a@x.com",
            "phone": "+919999999999",
            "business_name": "AFM SOLAR",
            "niche": "solar_residential",
            "city": "Pune",
            "text": "interested",
            "draft": "Namaste",
            "wa_link": "https://wa.me/919999999999?text=Namaste",
            "owner_action": "reply_or_call_then_done",
            "sla_state": "n/a",
            "at": "2026-08-27T00:00:00+00:00",
            "prospect_id": "p1",
        },
        {
            "hq_id": "x2",
            "channel": "calling_flagged",
            "intent": "interested",
            "from": "b@x.com",
            "phone": "+919888888888",
            "business_name": "SAVEMAX",
            "niche": "solar_residential",
            "city": "Mumbai",
            "text": "interested",
            "draft": "Hello",
            "wa_link": "https://wa.me/919888888888?text=Hello",
            "owner_action": "reply_or_call_then_done",
            "sla_state": "n/a",
            "at": "2026-08-26T00:00:00+00:00",
            "prospect_id": "p2",
        },
        {
            "hq_id": "x3",
            "channel": "calling_flagged",
            "intent": "interested",
            "from": "c@x.com",
            "phone": "",
            "business_name": "GLOBAL",
            "niche": "real_estate",
            "city": "Nagpur",
            "text": "interested",
            "draft": "",
            "wa_link": "",
            "owner_action": "reply_or_call_then_done",
            "sla_state": "n/a",
            "at": "2026-08-25T00:00:00+00:00",
            "prospect_id": "p3",
        },
    ]

    def fake_rows(limit=200, scope="boss"):
        return sample

    monkeypatch.setattr(reply_agent, "hot_queue", fake_rows)

    r = asyncio.run(hot_queue_owner_pack.build_owner_pack(limit=200, push_ntfy=False))
    assert r.get("ok") is True
    assert r.get("rows") == 3
    csv_path = r.get("csv")
    md_path = r.get("md")
    assert os.path.exists(csv_path)
    assert os.path.exists(md_path)
    # CSV should have 3 data rows + 1 header
    with open(csv_path, encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 4
    # First data row must have wa_link + phone parsed
    assert "wa.me/919999999999" in lines[1]
    assert "919999999999" in lines[1]


def _row(hq_id, phone, wa_link=None, name="BIZ"):
    return {
        "hq_id": hq_id,
        "channel": "calling_flagged",
        "intent": "interested",
        "from": f"{hq_id}@x.com",
        "phone": phone,
        "business_name": name,
        "niche": "solar_residential",
        "city": "Pune",
        "text": "interested",
        "draft": "",
        "wa_link": wa_link or "",
        "owner_action": "reply_or_call_then_done",
        "sla_state": "n/a",
        "at": "2026-08-27T00:00:00+00:00",
        "prospect_id": hq_id,
    }


def test_existing_customer_phone_is_excluded_from_pack(tmp_path, monkeypatch):
    """A row whose phone belongs to a paying customer must never reach the pack."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    from app.platform import hot_queue_owner_pack, reply_agent

    rows = [
        _row("p1", "+919876543210", name="JIYA-CUSTOMER"),   # Jiya Makeover
        _row("p2", "919888888888", name="REAL-PROSPECT"),
        _row("p3", "9876543210", name="SAME-CUSTOMER-BARE"),  # same number, bare form
    ]
    monkeypatch.setattr(reply_agent, "hot_queue", lambda limit=200, scope="boss": rows)
    monkeypatch.setattr(
        hot_queue_owner_pack,
        "_existing_customer_phones",
        lambda: ({"9876543210"}, True),
    )

    r = asyncio.run(hot_queue_owner_pack.build_owner_pack(limit=200, push_ntfy=False))
    assert r.get("ok") is True
    assert r.get("rows") == 1, r
    assert r.get("excluded_existing_customers") == 2, r
    assert r.get("customer_suppression") == "active"

    with open(r["csv"], encoding="utf-8") as f:
        body = f.read()
    assert "9876543210" not in body          # excluded in both +91 and bare form
    assert "919888888888" in body            # the real prospect survives


def test_suppression_matches_wa_link_only_row(tmp_path, monkeypatch):
    """A row with no `phone` but a customer wa.me link must also be excluded."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    from app.platform import hot_queue_owner_pack, reply_agent

    rows = [_row("p1", "", wa_link="https://wa.me/919876543210?text=hi")]
    monkeypatch.setattr(reply_agent, "hot_queue", lambda limit=200, scope="boss": rows)
    monkeypatch.setattr(
        hot_queue_owner_pack,
        "_existing_customer_phones",
        lambda: ({"9876543210"}, True),
    )

    r = asyncio.run(hot_queue_owner_pack.build_owner_pack(limit=200, push_ntfy=False))
    assert r.get("rows") == 0, r
    assert r.get("excluded_existing_customers") == 1, r


def test_unverified_suppression_is_reported_not_silent(tmp_path, monkeypatch):
    """Unreadable client store must surface `unverified`, never pretend it is clean."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    from app.platform import hot_queue_owner_pack, reply_agent

    rows = [_row("p1", "919888888888")]
    monkeypatch.setattr(reply_agent, "hot_queue", lambda limit=200, scope="boss": rows)
    monkeypatch.setattr(
        hot_queue_owner_pack, "_existing_customer_phones", lambda: (set(), False)
    )

    r = asyncio.run(hot_queue_owner_pack.build_owner_pack(limit=200, push_ntfy=False))
    assert r.get("customer_suppression") == "unverified", r
    assert r.get("rows") == 1, r  # fail-visible: rows pass through, state is flagged
    with open(r["md"], encoding="utf-8") as f:
        assert "UNVERIFIED" in f.read()


def test_suppression_lookup_never_raises(tmp_path, monkeypatch):
    """A exploding suppression lookup must not take the daily pack down with it."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    from app.platform import hot_queue_owner_pack, reply_agent

    monkeypatch.setattr(
        reply_agent, "hot_queue", lambda limit=200, scope="boss": [_row("p1", "919888888888")]
    )

    def boom():
        raise RuntimeError("store locked")

    monkeypatch.setattr(hot_queue_owner_pack, "_existing_customer_phones", boom)

    r = asyncio.run(hot_queue_owner_pack.build_owner_pack(limit=200, push_ntfy=False))
    assert r.get("ok") is True, r
    assert r.get("customer_suppression") == "unverified", r
    assert r.get("rows") == 1, r


def test_last10_normalisation():
    from app.platform import hot_queue_owner_pack

    assert hot_queue_owner_pack._last10("+919876543210") == "9876543210"
    assert hot_queue_owner_pack._last10("919876543210") == "9876543210"
    assert hot_queue_owner_pack._last10("+91 98765-43210") == "9876543210"
    assert hot_queue_owner_pack._last10("") == ""
    assert hot_queue_owner_pack._last10("12345") == ""  # too short to be a phone


def test_build_owner_pack_never_raises_on_hot_queue_error(tmp_path, monkeypatch):
    """If reply_agent.hot_queue() raises, build_owner_pack returns ok:False, never crashes."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    from app.platform import hot_queue_owner_pack, reply_agent

    def boom(*a, **kw):
        raise RuntimeError("redis down")

    monkeypatch.setattr(reply_agent, "hot_queue", boom)

    r = asyncio.run(hot_queue_owner_pack.build_owner_pack(limit=200, push_ntfy=False))
    assert r.get("ok") is False
    assert "hot_queue_unavailable" in r.get("error", "")


# --------------------------------------------------------------------------- #
# check_gates() — owner-gated admin compliance adapter (2026-09-05)
# --------------------------------------------------------------------------- #
class _StubVL:
    """In-process stub of ``app.telephony.voice_launch`` exposing only the
    three primitives ``check_gates`` calls. We attach this directly to the
    real module via monkeypatch.setattr so the lazy ``from app.telephony
    import voice_launch`` inside ``check_gates`` keeps working."""

    def __init__(self):
        self.kill_engaged = False
        self.rec_ok = True
        self.rec_reason = ""
        self.campaign_on = True


class _StubDT:
    """Stub of ``datetime`` module. ``check_gates`` calls ``datetime.now().hour``,
    so we need .now() to return an object with .hour."""

    def __init__(self, hour_value: int):
        self._hour = hour_value

    def now(self):
        class _T:
            hour = self._hour
        return _T()


@pytest.fixture
def stubbed_env(monkeypatch):
    """Wire a clean environment for check_gates() tests:
    kill disengaged, recording ok, campaign enabled, hour=14 (inside TRAI window).
    Individual tests can override fields."""
    from app.telephony import voice_launch

    stub = _StubVL()
    monkeypatch.setattr(voice_launch, "admin_kill_engaged", lambda: stub.kill_engaged)
    monkeypatch.setattr(
        voice_launch,
        "recording_gate_ok",
        lambda: (stub.rec_ok, stub.rec_reason),
    )
    monkeypatch.setattr(voice_launch, "campaign_enabled", lambda: stub.campaign_on)

    import app.platform.hot_queue_owner_pack as _mod
    monkeypatch.setattr(_mod, "datetime", _StubDT(hour_value=14))

    monkeypatch.delenv("EMERGENCY_STOP", raising=False)
    monkeypatch.delenv("WHATSAPP_AUTO_SEND", raising=False)
    return stub


class TestCheckGatesAdapter:
    """Verify the upgraded check_gates() composes real primitives, never invents
    new compliance gates, and never silently passes when primitives fail.

    Contract: returns dict[str, str] where value is either literal "pass" or a
    reason string. ``admin_api._gate_check`` 403s on any non-"pass" value, so
    the adapter must FAIL-CLOSED.
    """

    def test_returns_dict_with_only_str_values(self, stubbed_env):
        """Every value must be a str (never bool/int) — admin_api string-compares."""
        from app.platform import hot_queue_owner_pack

        out = hot_queue_owner_pack.check_gates()
        assert isinstance(out, dict)
        assert out, "check_gates() must return at least one gate"
        for k, v in out.items():
            assert isinstance(k, str)
            assert isinstance(v, str), f"gate {k!r} returned non-str {v!r}"
            # Admin string-compares to "pass" — anything else opens the gate.
            # False-y values like "" or None would silently pass; the adapter
            # explicitly forbids that.
            assert v != "", f"gate {k!r} has empty value"

    def test_kill_fence_block_when_engaged(self, stubbed_env):
        """admin_kill_engaged=True → gate NOT 'pass'."""
        from app.platform import hot_queue_owner_pack

        stubbed_env.kill_engaged = True
        out = hot_queue_owner_pack.check_gates()
        assert out.get("kill_fence") != "pass"
        assert "admin_kill" in out["kill_fence"].lower()

    def test_kill_fence_pass_when_disengaged(self, stubbed_env):
        """admin_kill_engaged=False → gate == 'pass'."""
        from app.platform import hot_queue_owner_pack

        out = hot_queue_owner_pack.check_gates()
        assert out["kill_fence"] == "pass"

    def test_recording_gate_block(self, stubbed_env):
        """recording_gate_ok returns (False, reason) → gate NOT pass."""
        from app.platform import hot_queue_owner_pack

        stubbed_env.rec_ok = False
        stubbed_env.rec_reason = "no_storage"
        out = hot_queue_owner_pack.check_gates()
        assert out["recording_ok"] != "pass"
        assert "recording" in out["recording_ok"]
        assert "no_storage" in out["recording_ok"]

    def test_campaign_disabled_blocks(self, stubbed_env):
        """campaign_enabled=False → gate NOT pass."""
        from app.platform import hot_queue_owner_pack

        stubbed_env.campaign_on = False
        out = hot_queue_owner_pack.check_gates()
        assert out["campaign_on"] != "pass"
        assert "disabled" in out["campaign_on"]

    def test_voice_window_outside_block(self, stubbed_env, monkeypatch):
        """TRAI window: hour 22 → gate NOT pass."""
        from app.platform import hot_queue_owner_pack
        import app.platform.hot_queue_owner_pack as _mod

        monkeypatch.setattr(_mod, "datetime", _StubDT(hour_value=22))
        out = hot_queue_owner_pack.check_gates()
        assert out["voice_window"] != "pass"
        assert "22" in out["voice_window"]

    def test_voice_window_inside_pass(self, stubbed_env):
        """hour=14 → voice_window == 'pass' (already set in fixture)."""
        from app.platform import hot_queue_owner_pack

        out = hot_queue_owner_pack.check_gates()
        assert out["voice_window"] == "pass"

    def test_emergency_stop_blocks(self, stubbed_env, monkeypatch):
        """EMERGENCY_STOP=1 → gate added with non-pass value."""
        from app.platform import hot_queue_owner_pack

        monkeypatch.setenv("EMERGENCY_STOP", "1")
        out = hot_queue_owner_pack.check_gates()
        assert out.get("emergency_stop") != "pass"

