"""Contract tests — telephony readiness ``run_checks()`` outbound-probe integration.

2026-09-05 fix under test: ``run_checks`` previously hardcoded ``outbound_ok = True``
(the false-green blind spot where the caller-ID was configured but NOT owned by the
Vobiz account — prod failure "The from number 911171366938 is not owned by this
account"). Now the probe is consulted when armed; when unarmed it is weight=0 and
honestly reported as skipped, so the readiness score never claims verified
ownership that was never checked.
"""

from unittest.mock import AsyncMock, patch

from app.telephony import telephony_readiness as tr


def test_probe_hardcoded_true_is_gone():
    """The old false-green (`outbound_ok = True`) must not be present."""
    src = __import__("app.telephony.telephony_readiness", fromlist=["*"]).__dict__
    import inspect

    source = inspect.getsource(tr.run_checks)
    assert "outbound_ok = True" not in source
    assert "outbound_ok" not in source or "probe_result.get" in source


def test_probe_unarmed_is_weight_zero_and_honest():
    """VOBIZ_VERIFY_CALLER_ID_OUTBOUND unset -> probe weight 0, reported skipped, not scored."""
    res = tr.run_checks()
    probe = res["checks"].get("outbound_probe")
    assert probe is not None
    assert probe["weight"] == 0
    assert "skipped" in probe["why"].lower()
    # Skipped probe must not appear in missing (would drag the score for an unarmed check)
    assert "outbound_probe" not in res["missing"]


def test_probe_failure_reduces_score_when_armed(monkeypatch):
    """Armed probe failing (caller-ID not owned) must drag the readiness score."""
    monkeypatch.setenv("VOBIZ_VERIFY_CALLER_ID_OUTBOUND", "1")
    monkeypatch.setenv("VOBIZ_CALLER_ID", "+911171366938")

    fake = AsyncMock()
    fake.create_call.return_value = {
        "status": "failed",
        "error": "The from number 911171366938 is not owned by this account",
    }
    with patch("app.telephony.vobiz_handler.VobizClient", return_value=fake):
        res = tr.run_checks()
    probe = res["checks"]["outbound_probe"]
    assert probe["ok"] is False
    assert probe["weight"] == 20
    assert "outbound_probe" in res["missing"]


def test_probe_success_when_armed_and_owned(monkeypatch):
    """Armed probe succeeding (caller-ID owned) keeps the score high."""
    monkeypatch.setenv("VOBIZ_VERIFY_CALLER_ID_OUTBOUND", "1")
    monkeypatch.setenv("VOBIZ_CALLER_ID", "+911171366938")

    fake = AsyncMock()
    fake.create_call.return_value = {"status": "success", "call_id": "c1"}
    with patch("app.telephony.vobiz_handler.VobizClient", return_value=fake):
        res = tr.run_checks()
    probe = res["checks"]["outbound_probe"]
    assert probe["ok"] is True
    assert probe["weight"] == 20
    assert "outbound_probe" not in res["missing"]


def test_probe_exception_is_fail_closed_when_armed(monkeypatch):
    """Armed probe raising (API down) must not silently pass the ownership gate."""
    monkeypatch.setenv("VOBIZ_VERIFY_CALLER_ID_OUTBOUND", "1")
    with patch(
        "app.telephony.telephony_readiness_probe.verify_outbound_connectivity",
        side_effect=Exception("api down"),
    ):
        res = tr.run_checks()
    probe = res["checks"]["outbound_probe"]
    assert probe["ok"] is False
    assert "outbound_probe" in res["missing"]