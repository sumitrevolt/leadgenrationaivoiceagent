"""Unit tests for ``scripts/waha_watchdog.py`` — the false negative that hid for weeks.

REGRESSION THIS LOCKS DOWN (2026-09-14)
---------------------------------------
The watchdog lived ONLY on the VPS (untracked, so invisible to review and CI), and the
host port in it had drifted from the one the checked-in compose publishes
(``deploy/compose/docker-compose.waha.yml`` => ``127.0.0.1:3111:3000``; the VPS copy said
3002). Every poll therefore wrote::

    {"waha_status": "UNKNOWN", "raw": {"error": "Connection refused"}}

into ``data/wa_health_check.json``. Two different situations produced that same record:

* the WAHA service is **unreachable** (wrong port / dead container), and
* WAHA answered but the **session is logged out** (``SCAN_QR_CODE`` / ``UNPAIRED``).

The second one is the one an operator must act on within minutes (scan the QR) and it
looked exactly like the first. These tests fake the HTTP layer and pin both states apart,
plus the env-configurability that removed the hardcoded host/port/paths.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import urllib.error

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "waha_watchdog.py"


def _load_module():
    """Load scripts/waha_watchdog.py by path (scripts/ is not an importable package)."""
    spec = importlib.util.spec_from_file_location("waha_watchdog_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wd = _load_module()


# --------------------------------------------------------------------------- #
# Fake HTTP layer — stands in for urllib.request.urlopen
# --------------------------------------------------------------------------- #
class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._body = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeHTTP:
    """Records ``(method, url)`` for every call so "no restart POST" is provable."""

    def __init__(
        self, payload: dict | None = None, exc: Exception | None = None, status: int = 200
    ):
        self.payload = payload if payload is not None else {}
        self.exc = exc
        self.status = status
        self.calls: list[tuple[str, str]] = []

    def __call__(self, req, timeout=None):
        self.calls.append((req.get_method(), req.full_url))
        if self.exc is not None:
            raise self.exc
        return _FakeResponse(self.payload, self.status)

    @property
    def posts(self) -> list[str]:
        return [u for m, u in self.calls if m == "POST"]


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Every test reads/writes its OWN paths — never /opt/leadgen, never the real .env."""
    monkeypatch.setenv("WAHA_WATCHDOG_HEALTH_FILE", str(tmp_path / "wa_health_check.json"))
    monkeypatch.setenv("WAHA_WATCHDOG_LOG_FILE", str(tmp_path / "waha_watchdog.log"))
    monkeypatch.setenv("WAHA_WATCHDOG_ENV_FILE", str(tmp_path / ".env"))
    for k in ("WAHA_WATCHDOG_URL", "WAHA_WATCHDOG_SESSION", "WAHA_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    return tmp_path


# --------------------------------------------------------------------------- #
# (a) reachable + SCAN_QR_CODE must be "logged out", NOT an error
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("status", ["SCAN_QR_CODE", "UNPAIRED", "NOT_CREATED"])
def test_logged_out_session_is_reported_as_logged_out(monkeypatch, status):
    http = _FakeHTTP({"status": status})
    monkeypatch.setattr(wd.urllib.request, "urlopen", http)

    rec = wd.check_once()

    assert rec["reachable"] is True
    assert rec["session_status"] == status
    assert rec["state"] == "logged_out"
    assert rec["actionable"] == "owner_scan_qr"
    assert rec["raw"] == {"status": status}, "the WAHA answer must be kept verbatim"
    # It answered — the watchdog must NOT try to restart a session that needs a scan.
    assert http.posts == []


# --------------------------------------------------------------------------- #
# (b) unreachable service must be "unreachable", NOT "logged out"/UNKNOWN
# --------------------------------------------------------------------------- #
def test_unreachable_service_is_reported_as_unreachable(monkeypatch):
    refused = urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))
    http = _FakeHTTP(exc=refused)
    monkeypatch.setattr(wd.urllib.request, "urlopen", http)

    rec = wd.check_once()

    assert rec["reachable"] is False
    assert rec["state"] == "unreachable"
    assert rec["actionable"] == "check_waha_service"
    assert rec["session_status"] is None
    # The legacy key must not say "UNKNOWN" — that is the exact record that hid the bug.
    assert rec["waha_status"] == "UNREACHABLE"
    assert "Connection refused" in rec["raw"]["error"]
    assert http.posts == []


def test_http_error_is_auth_error_not_unreachable(monkeypatch):
    """A 401 means WAHA ANSWERED — chasing "service down" there is the same class of
    false negative this file exists to end."""

    class _Err(urllib.error.HTTPError):
        def __init__(self):
            super().__init__("http://waha/api/sessions/default", 401, "Unauthorized", {}, None)

    http = _FakeHTTP(exc=_Err())
    monkeypatch.setattr(wd.urllib.request, "urlopen", http)

    rec = wd.check_once()

    assert rec["state"] == "auth_error"
    assert rec["actionable"] == "check_waha_api_key"
    assert rec["waha_status"] == "AUTH_ERROR"


# --------------------------------------------------------------------------- #
# Health file + log are written where the CONFIG says, not at a hardcoded path
# --------------------------------------------------------------------------- #
def test_health_record_is_written_to_the_configured_path(monkeypatch, _isolate):
    http = _FakeHTTP({"status": "WORKING"})
    monkeypatch.setattr(wd.urllib.request, "urlopen", http)

    rec = wd.check_once()

    written = json.loads((_isolate / "wa_health_check.json").read_text(encoding="utf-8"))
    assert written == rec
    assert written["state"] == "working"
    assert (_isolate / "waha_watchdog.log").exists()


def test_base_url_and_session_are_env_configured(monkeypatch):
    monkeypatch.setenv("WAHA_WATCHDOG_URL", "http://waha-host:3999/")
    monkeypatch.setenv("WAHA_WATCHDOG_SESSION", "canary")
    http = _FakeHTTP({"status": "WORKING"})
    monkeypatch.setattr(wd.urllib.request, "urlopen", http)

    wd.check_once()

    assert http.calls == [("GET", "http://waha-host:3999/api/sessions/canary")]


def test_default_url_targets_the_published_host_port(monkeypatch):
    """The default must match what the checked-in WAHA compose publishes
    (``deploy/compose/docker-compose.waha.yml`` => ``127.0.0.1:3111:3000``). The untracked
    VPS copy had drifted to 3002 — a mismatch nobody could diff, which is the whole reason
    this file is tracked now."""
    assert wd.DEFAULT_WAHA_URL == "http://127.0.0.1:3111"
    # ...and the default is only a default: the port stays env-configurable.
    monkeypatch.setenv("WAHA_WATCHDOG_URL", "http://127.0.0.1:3002")
    assert wd.waha_url() == "http://127.0.0.1:3002"


# --------------------------------------------------------------------------- #
# FAILED/STOPPED still restarts; API key is read, never carried
# --------------------------------------------------------------------------- #
def test_failed_session_is_restarted(monkeypatch):
    http = _FakeHTTP({"status": "FAILED"})
    monkeypatch.setattr(wd.urllib.request, "urlopen", http)

    rec = wd.check_once()

    assert rec["state"] == "failed"
    assert rec["actionable"] == "watchdog_restart"
    assert rec["restart_ok"] is True
    assert http.posts == ["http://127.0.0.1:3111/api/sessions/default/restart"]


def test_failed_restart_is_flagged_actionable(monkeypatch):
    http = _FakeHTTP({"status": "STOPPED"})
    monkeypatch.setattr(wd.urllib.request, "urlopen", http)

    rec = wd.check_once(restart_fn=lambda: False)

    assert rec["state"] == "stopped"
    assert rec["restart_ok"] is False
    assert rec["actionable"] == "restart_failed"


def test_api_key_is_read_never_hardcoded(monkeypatch, _isolate):
    """No fallback key exists. Env wins over .env; a missing .env yields "" — never a
    literal, because a hardcoded key in a tracked script is a leaked key."""
    assert wd.api_key() == ""  # env unset + no .env file at the configured path

    (_isolate / ".env").write_text("WAHA_API_KEY=from-env-file\n", encoding="utf-8")
    assert wd.api_key() == "from-env-file"

    monkeypatch.setenv("WAHA_API_KEY", "from-process-env")
    assert wd.api_key() == "from-process-env"


def test_env_file_reader_handles_export_prefix(monkeypatch, _isolate):
    (_isolate / ".env").write_text('export WAHA_API_KEY="quoted-key"\n', encoding="utf-8")
    assert wd.api_key() == "quoted-key"
