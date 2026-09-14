"""§5: ``app/tasks/whatsapp_automation.py`` must send through the guarded boundary.

REGRESSION THIS LOCKS DOWN (2026-09-14)
---------------------------------------
``send_template_message`` built its OWN ``graph.facebook.com/{v}/{phone_id}/messages``
payload and POSTed it with httpx. That made this module the one automated WhatsApp
sender in the repo that never called
``app.integrations.whatsapp.send_permitted`` — so a send here bypassed the canary
allowlist, the opt-out ledger AND the Owner-OS kill switch, and it was invisible to the
2026-07-31 egress ratchet because that ratchet only scanned for WAHA ``/api/sendText``.

The module is NOT dead code: it is dispatched live from
``app/tasks/staff_jobs.py::whatsapp_automation`` (beat ``staff-whatsapp-automation-hourly``)
and ``app/platform/team_scheduler.py::_run_job_inner``.

Also pinned here: ``emergency_stop()`` must never write ``.env`` (it used to ``sed -i``
the hard-off flag, which a running process cannot even observe).

NO live HTTP anywhere: httpx is faked and every request is recorded.
"""

from __future__ import annotations

import importlib
import inspect

import pytest

mod = importlib.import_module("app.tasks.whatsapp_automation")
from app.integrations import whatsapp_selfhost as wahost  # noqa: E402

LISTED = "919876543210"
UNLISTED = "918888888888"


# --------------------------------------------------------------------------- #
# Recording fake httpx — no POST without it being visible
# --------------------------------------------------------------------------- #
class _Resp:
    def __init__(self, payload, status=200, content=b"{}"):
        self._json = payload
        self.status_code = status
        self.content = content
        self.text = ""

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("err", request=None, response=self)


class _Recorder:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **k):
        self.calls.append(("GET", url))
        return _Resp(
            {"numberExists": True, "chatId": f"{LISTED}@c.us"},
            content=b'{"numberExists":true}',
        )

    async def post(self, url, **k):
        self.calls.append(("POST", url))
        return _Resp({"id": "wamid.REGRESSION"})

    @property
    def posts(self) -> list[str]:
        return [u for m, u in self.calls if m == "POST"]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Neutralise env/settings/store so the GATE is what decides, not ambient state."""
    for k in (
        "WHATSAPP_AUTO_SEND",
        "WHATSAPP_AUTO_SEND_HARD_OFF",
        "WHATSAPP_AUTO_SEND_DAILY_CAP",
        "WHATSAPP_AUTO_SEND_BATCH",
        "WHATSAPP_SEND_ALLOWLIST",
        "WAHA_BASE_URL",
        "WAHA_API_KEY",
        "WAHA_SESSION",
        "WHATSAPP_PROVIDER",
        "WHATSAPP_BUSINESS_NUMBER",
        "WHATSAPP_ENFORCE_BUSINESS_NUMBER",
    ):
        monkeypatch.delenv(k, raising=False)
    from app.config import settings

    monkeypatch.setattr(settings, "waha_base_url", "", raising=False)
    monkeypatch.setattr(settings, "whatsapp_provider", "cloud", raising=False)
    monkeypatch.setattr(settings, "whatsapp_business_number", "", raising=False)
    wahost._LINKED_CACHE["digits"] = None
    wahost._LINKED_CACHE["at"] = 0.0

    from app.marketing import wa_campaign_runner
    from app.platform import owner_os
    from app.telephony import consent_ledger

    monkeypatch.setattr(owner_os, "kill_engaged", lambda _name: False)
    monkeypatch.setattr(consent_ledger, "is_suppressed", lambda _p: False)
    monkeypatch.setattr(wa_campaign_runner, "is_suppressed", lambda _p: False)
    yield


def _arm(monkeypatch, allowlist: str = LISTED) -> _Recorder:
    """Reachable fake WAHA stack, auto-send ON, canary allowlist fixed by the caller."""
    rec = _Recorder()
    monkeypatch.setattr(wahost.httpx, "AsyncClient", rec)
    monkeypatch.setenv("WAHA_BASE_URL", "http://waha:3000")
    monkeypatch.setenv("WHATSAPP_PROVIDER", "waha")
    monkeypatch.setenv("WHATSAPP_ENFORCE_BUSINESS_NUMBER", "0")
    monkeypatch.setenv("WHATSAPP_AUTO_SEND", "1")
    monkeypatch.setenv("WHATSAPP_SEND_ALLOWLIST", allowlist)
    return rec


def _send(phone: str) -> dict:
    return mod._run_async(mod.send_template_message(phone, "lead_followup_v1", ["Ramesh"]))


# --------------------------------------------------------------------------- #
# The bypass itself
# --------------------------------------------------------------------------- #
def test_non_allowlisted_recipient_is_refused(monkeypatch):
    rec = _arm(monkeypatch, allowlist=LISTED)

    res = _send(UNLISTED)

    assert res["sent"] is False
    assert res["reason"] == "recipient_not_allowlisted"
    assert rec.calls == [], "a refused send must not reach the network at all"


def test_opted_out_recipient_is_refused(monkeypatch):
    from app.telephony import consent_ledger

    rec = _arm(monkeypatch, allowlist=f"{LISTED},{UNLISTED}")
    monkeypatch.setattr(consent_ledger, "is_suppressed", lambda _p: True)

    res = _send(UNLISTED)

    assert res["sent"] is False
    assert res["reason"] == "opted_out"
    assert rec.calls == []


def test_allowlisted_recipient_sends_through_the_boundary(monkeypatch):
    """The gate must not be so tight that a permitted send stops working."""
    rec = _arm(monkeypatch, allowlist=LISTED)

    res = _send(LISTED)

    assert res["sent"] is True
    assert any("/api/sendText" in u for u in rec.posts), rec.calls


def test_flag_off_blocks_before_any_network_call(monkeypatch):
    rec = _arm(monkeypatch, allowlist=LISTED)
    monkeypatch.setenv("WHATSAPP_AUTO_SEND", "0")

    res = _send(LISTED)

    assert res["sent"] is False
    assert rec.calls == []


def test_hard_off_env_blocks_even_with_flag_on(monkeypatch):
    rec = _arm(monkeypatch, allowlist=LISTED)
    monkeypatch.setenv("WHATSAPP_AUTO_SEND_HARD_OFF", "1")

    res = _send(LISTED)

    assert res["sent"] is False
    assert rec.calls == []


# --------------------------------------------------------------------------- #
# Structural ratchets — the bypass must not be reintroducible
# --------------------------------------------------------------------------- #
def _code_only(node) -> str:
    """Unparsed source with DOCSTRINGS removed — these checks are about executable code,
    and the docstrings here deliberately quote the old ``graph.facebook.com`` URL and the
    old ``sed .env`` command as history."""
    import ast

    for sub in ast.walk(node):
        if isinstance(sub, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (
                sub.body
                and isinstance(sub.body[0], ast.Expr)
                and isinstance(sub.body[0].value, ast.Constant)
                and isinstance(sub.body[0].value.value, str)
            ):
                sub.body = sub.body[1:]
    return ast.unparse(node)


def test_module_builds_no_provider_url_of_its_own():
    """Source-level: no Meta Graph endpoint and no httpx client in this module. The only
    allowed egress is via get_whatsapp_sender()."""
    import ast

    code = _code_only(ast.parse(inspect.getsource(mod)))

    assert "graph.facebook.com" not in code, "module must not address a provider directly"
    assert "httpx" not in code, "module must not own an HTTP client"


def test_emergency_stop_never_writes_env_file():
    """Application code must not write `.env`: it is the credential store (§5 secrets),
    it is read at container-create time (so a running process cannot observe the edit),
    and the old relative-path `sed -i` no-opped into a swallowed capture_output."""
    import ast
    import textwrap

    code = _code_only(ast.parse(textwrap.dedent(inspect.getsource(mod.emergency_stop))))

    assert "sed" not in code
    assert ".env" not in code
    assert "subprocess" not in code


# --------------------------------------------------------------------------- #
# emergency_stop() — runtime mechanism, real operational effect
# --------------------------------------------------------------------------- #
def test_emergency_stop_engages_owner_kill_and_blocks_the_next_send(monkeypatch):
    from app.platform import owner_os

    state = {"engaged": False, "calls": []}

    def _set_kill(key, engaged, by="", reason=""):
        state["calls"].append((key, engaged))
        state["engaged"] = bool(engaged)
        return {"ok": True, "key": key, "engaged": bool(engaged)}

    monkeypatch.setattr(owner_os, "set_kill_switch", _set_kill)
    monkeypatch.setattr(owner_os, "kill_engaged", lambda name: state["engaged"])

    rec = _arm(monkeypatch, allowlist=LISTED)  # everything else armed to SEND

    out = mod.emergency_stop(by="test", reason="regression")

    assert state["calls"] == [("owner_whatsapp_outbound", True)]
    assert out.get("ok") is True
    assert mod.whatsapp_enabled() is False
    res = _send(LISTED)
    assert res["sent"] is False
    assert rec.calls == [], "an engaged emergency stop must stop the very next send"


def test_emergency_stop_reports_failure_instead_of_silent_success(monkeypatch):
    from app.platform import owner_os

    def _boom(*a, **k):
        raise RuntimeError("owner store down")

    monkeypatch.setattr(owner_os, "set_kill_switch", _boom)

    out = mod.emergency_stop()

    assert out["ok"] is False
    assert "owner store down" in out["error"]
