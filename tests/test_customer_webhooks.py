"""customer_webhooks — CRUD, SSRF defense, HMAC sign, retries, ownership.

A paid feature gets a paid level of test discipline. The bars:
- A customer MUST NOT be able to register a URL pointing at our infra.
- A customer MUST NOT be able to read / delete another customer's webhook.
- HMAC signature MUST verify with the registered secret.
- Delivery retries MUST follow the schedule; failures MUST be logged.
- emit() MUST short-circuit when CUSTOMER_WEBHOOKS unset.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

import pytest

from app.platform import customer_webhooks as cw


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cw, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(cw, "_REG_PATH", tmp_path / "registrations.jsonl")
    monkeypatch.setattr(cw, "_DEL_PATH", tmp_path / "deliveries.jsonl")
    monkeypatch.setenv("CUSTOMER_WEBHOOKS", "1")
    # Tests use http://example.com (a globally-routable host). Resolution
    # might still fall on a non-private IP — we keep DENY_PRIVATE on so
    # the SSRF path is actually exercised.
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "1")


# --------------------------------------------------------------------------- #
# Register validation
# --------------------------------------------------------------------------- #
def test_register_rejects_internal_hostnames() -> None:
    """SSRF defense: docker-network names MUST be refused (C4 lesson)."""
    out = cw.register("client_a", "http://leadgen_db:5432/hook", ["lead.qualified"])
    assert out["ok"] is False
    assert "internal" in out["error"].lower()


def test_register_rejects_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    out = cw.register("client_a", "http://127.0.0.1/hook", ["lead.qualified"])
    assert out["ok"] is False
    # Either internal hostname OR private-ip path triggers reject
    assert "private" in out["error"].lower() or "internal" in out["error"].lower()


def test_register_rejects_non_http_scheme() -> None:
    out = cw.register("client_a", "ftp://example.com/hook", ["lead.qualified"])
    assert out["ok"] is False
    assert "scheme" in out["error"].lower()


def test_register_rejects_unknown_event() -> None:
    monkeypatch_off_ssrf(["lead.notathing"])
    out = cw.register("client_a", "https://example.com/hook", ["lead.notathing"])
    assert out["ok"] is False
    assert "unknown event" in out["error"].lower()


def test_register_requires_at_least_one_event(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "0")
    out = cw.register("client_a", "https://example.com/hook", [])
    assert out["ok"] is False


def monkeypatch_off_ssrf(_dummy: Any = None) -> None:
    """Stub used by tests that need register() to succeed without DNS."""
    import os

    os.environ["CUSTOMER_WEBHOOK_DENY_PRIVATE"] = "0"


def test_register_returns_secret_only_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "0")
    out = cw.register("client_a", "https://example.com/hook", ["lead.qualified"])
    assert out["ok"] is True
    assert out["secret"].startswith("whsec_")
    # Subsequent list redacts
    items = cw.list_for("client_a")
    assert len(items) == 1
    assert "secret" not in items[0]
    assert "secret_preview" in items[0]
    assert "..." in items[0]["secret_preview"]


# --------------------------------------------------------------------------- #
# Ownership / IDOR
# --------------------------------------------------------------------------- #
def test_list_for_filters_by_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "0")
    cw.register("client_a", "https://example.com/a", ["lead.qualified"])
    cw.register("client_b", "https://example.com/b", ["lead.qualified"])
    assert len(cw.list_for("client_a")) == 1
    assert len(cw.list_for("client_b")) == 1


def test_remove_requires_ownership(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "0")
    out = cw.register("client_a", "https://example.com/a", ["lead.qualified"])
    wh_id = out["id"]
    # Wrong owner -> False
    assert cw.remove(wh_id, "client_b") is False
    # Right owner -> True
    assert cw.remove(wh_id, "client_a") is True


def test_get_one_refuses_cross_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "0")
    out = cw.register("client_a", "https://example.com/a", ["lead.qualified"])
    assert cw.get_one(out["id"], "client_a") is not None
    assert cw.get_one(out["id"], "client_b") is None


# --------------------------------------------------------------------------- #
# HMAC signature
# --------------------------------------------------------------------------- #
def test_signature_matches_known_pattern() -> None:
    body = b'{"a":1}'
    sig = cw._sign(body, "topsecret")
    expected = hmac.new(b"topsecret", body, hashlib.sha256).hexdigest()
    assert sig == f"sha256={expected}"


# --------------------------------------------------------------------------- #
# Delivery
# --------------------------------------------------------------------------- #
def _async_test(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def test_delivery_records_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "0")
    out = cw.register("client_a", "https://example.com/hook", ["lead.qualified"])

    # Fake httpx client
    class _Resp:
        status_code = 200

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, content, headers):  # noqa: ANN001
            # Verify the request shape the customer will receive
            assert headers["X-LeadGen-Event"] == "lead.qualified"
            assert headers["X-LeadGen-Signature"].startswith("sha256=")
            assert "X-LeadGen-Delivery" in headers
            return _Resp()

    import httpx as _httpx

    monkeypatch.setattr(_httpx, "AsyncClient", lambda *a, **kw: _Client())

    result = await cw._deliver_one(out, "lead.qualified", {"lead_id": "L1"})
    assert result["delivered"] is True
    assert result["attempts"] == 1
    rows = cw._read_deliveries()
    assert rows[-1]["delivered"] is True
    assert rows[-1]["webhook_id"] == out["id"]


async def test_delivery_retries_on_5xx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "0")
    out = cw.register("client_a", "https://example.com/hook", ["lead.qualified"])

    state = {"calls": 0}

    class _Resp:
        def __init__(self, code):
            self.status_code = code

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, content, headers):  # noqa: ANN001
            state["calls"] += 1
            if state["calls"] < 3:
                return _Resp(503)
            return _Resp(200)

    import httpx as _httpx

    monkeypatch.setattr(_httpx, "AsyncClient", lambda *a, **kw: _Client())

    # Use 0-second backoff so the test runs fast
    result = await cw._deliver_one(out, "lead.qualified", {}, schedule=(0.0, 0.0, 0.0))
    assert result["delivered"] is True
    assert result["attempts"] == 3
    assert state["calls"] == 3


async def test_delivery_exhausts_retries_then_logs_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "0")
    out = cw.register("client_a", "https://example.com/hook", ["lead.qualified"])

    class _Resp:
        status_code = 500

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, content, headers):  # noqa: ANN001
            return _Resp()

    import httpx as _httpx

    monkeypatch.setattr(_httpx, "AsyncClient", lambda *a, **kw: _Client())

    result = await cw._deliver_one(out, "lead.qualified", {}, schedule=(0.0, 0.0, 0.0))
    assert result["delivered"] is False
    assert result["attempts"] == 3
    rows = cw._read_deliveries()
    assert rows[-1]["delivered"] is False
    assert rows[-1]["last_status"] == 500


# --------------------------------------------------------------------------- #
# emit()
# --------------------------------------------------------------------------- #
async def test_emit_inert_when_flag_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CUSTOMER_WEBHOOKS", raising=False)
    out = await cw.emit("client_a", "lead.qualified", {})
    assert out["disabled"] is True


async def test_emit_fires_only_for_subscribed_event(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "0")
    cw.register("client_a", "https://example.com/a", ["lead.qualified"])
    cw.register("client_a", "https://example.com/b", ["payment.received"])

    # Stub deliver_one so emit() returns synchronously-trackable
    fired: list[tuple[str, str]] = []

    async def _stub(row, event_type, payload, delivery_id=None, schedule=None):
        fired.append((row["url"], event_type))
        return {"delivered": True}

    monkeypatch.setattr(cw, "_deliver_one", _stub)
    out = await cw.emit("client_a", "lead.qualified", {"id": "L1"})
    assert out["emitted"] == 1
    # Let the scheduled task run
    await asyncio.sleep(0)
    assert ("https://example.com/a", "lead.qualified") in fired
    assert all(u != "https://example.com/b" for u, _ in fired)


async def test_emit_skips_disabled_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "0")
    out = cw.register("client_a", "https://example.com/a", ["lead.qualified"])
    # Toggle off by hand-editing the row + rewriting
    rows = cw._read_registrations()
    for r in rows:
        if r["id"] == out["id"]:
            r["enabled"] = False
    cw._atomic_rewrite(rows)

    async def _stub(row, event_type, payload, delivery_id=None, schedule=None):
        return {"delivered": True}

    monkeypatch.setattr(cw, "_deliver_one", _stub)
    result = await cw.emit("client_a", "lead.qualified", {})
    assert result["emitted"] == 0


# --------------------------------------------------------------------------- #
# call.report.ready (roadmap P0) — event + post-call emit helper
# --------------------------------------------------------------------------- #
def test_call_report_ready_is_supported_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """The new post-call report event must be registrable by a customer."""
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "0")
    assert "call.report.ready" in cw.SUPPORTED_EVENTS
    out = cw.register("client_a", "https://example.com/hook", ["call.report.ready"])
    assert out["ok"] is True
    assert out["events"] == ["call.report.ready"]


def test_emit_call_report_builds_full_report_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """emit_call_report() must delegate to fire_emit with the rich report
    payload under the call.report.ready event."""
    from app.telephony import post_call_hooks as pch

    captured: dict[str, Any] = {}

    def _fake_fire_emit(cid: str, event_type: str, payload: dict[str, Any]) -> None:
        captured["cid"] = cid
        captured["event"] = event_type
        captured["payload"] = payload

    monkeypatch.setattr(cw, "fire_emit", _fake_fire_emit)
    pch.emit_call_report(
        {"qualified": True, "interest_score": 82, "summary": "keen", "next_action": "send quote"},
        client_id="client_x",
        phone="+919812345678",
        call_id="sid_1",
        niche="gym",
        city="Pune",
        report_ready_at="2026-06-19T10:00:00",
    )
    assert captured["event"] == "call.report.ready"
    assert captured["cid"] == "client_x"
    p = captured["payload"]
    assert p["qualified"] is True
    assert p["interest_score"] == 82
    assert p["summary"] == "keen"
    assert p["next_action"] == "send quote"
    assert p["call_id"] == "sid_1"
    assert p["phone"] == "+919812345678"
    assert p["report_ready_at"] == "2026-06-19T10:00:00"


def test_emit_call_report_noop_without_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """No client_id → no emit (avoids firing an unattributable report)."""
    from app.telephony import post_call_hooks as pch

    calls: list[Any] = []
    monkeypatch.setattr(cw, "fire_emit", lambda *a, **k: calls.append(a))
    pch.emit_call_report({"qualified": True}, client_id="")
    assert calls == []


# --------------------------------------------------------------------------- #
# CONTRACT PIN — every literal event name emitted anywhere in app/ MUST be in
# SUPPORTED_EVENTS. fire_emit() drops unknown names SILENTLY (by design, never
# raises), which is how Stripe's "subscription.created"/"subscription.updated"
# went to /dev/null for weeks. This test turns that silent drop into a loud
# test failure at the moment someone types a bad event name.
# --------------------------------------------------------------------------- #
def _collect_emitted_event_literals() -> list[tuple[str, str]]:
    """(file, event_name) for every string-literal event passed to an emit call."""
    import ast

    app_dir = Path(__file__).resolve().parent.parent / "app"
    emit_funcs = {"fire_emit", "_emit_billing_customer_webhook"}
    emit_attrs = {"fire_emit", "emit"}
    emit_owners = {"cw", "_cw", "customer_webhooks"}
    found: list[tuple[str, str]] = []

    def _literals(node: ast.expr) -> list[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if isinstance(node, ast.IfExp):  # ("a.b" if cond else "c.d")
            return _literals(node.body) + _literals(node.orelse)
        return []  # dynamic (variable) — wrapper internals, skip

    for py in sorted(app_dir.rglob("*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:  # pragma: no cover - unparseable file is not this test's job
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or len(node.args) < 2:
                continue
            fn = node.func
            is_emit = (isinstance(fn, ast.Name) and fn.id in emit_funcs) or (
                isinstance(fn, ast.Attribute)
                and fn.attr in emit_attrs
                and isinstance(fn.value, ast.Name)
                and fn.value.id in emit_owners
            )
            if not is_emit:
                continue
            for name in _literals(node.args[1]):
                found.append((str(py.relative_to(app_dir)), name))
    return found


def test_every_emitted_event_name_is_supported() -> None:
    emitted = _collect_emitted_event_literals()
    # Sanity: the scanner must actually find the known emit sites — a refactor
    # that breaks collection would otherwise green-wash this contract.
    assert len(emitted) >= 8, f"emit-scan looks broken, only found: {emitted}"
    bad = [(f, e) for f, e in emitted if e not in cw.SUPPORTED_EVENTS]
    assert not bad, (
        f"Unsupported event names emitted (fire_emit will drop them SILENTLY): {bad}. "
        f"Either fix the name or append it to SUPPORTED_EVENTS."
    )


def test_supported_events_is_append_only_superset() -> None:
    """The original seven names are a public contract with customer verifiers —
    they may never be renamed or removed, only appended to."""
    original = {
        "lead.created",
        "lead.qualified",
        "call.completed",
        "call.report.ready",
        "payment.received",
        "subscription.activated",
        "subscription.cancelled",
    }
    assert original.issubset(set(cw.SUPPORTED_EVENTS))
    assert "subscription.updated" in cw.SUPPORTED_EVENTS


# --------------------------------------------------------------------------- #
# plan_charge_inr — the amount a payment.received webhook carries (UPI path)
# --------------------------------------------------------------------------- #
def test_plan_charge_inr_monthly_and_yearly() -> None:
    from app.billing.usage import plan_charge_inr

    assert plan_charge_inr("starter") == 1999
    assert plan_charge_inr("advanced") == 5999
    # yearly = 10x monthly (2 months free) — packages.py convention
    assert plan_charge_inr("starter_yearly") == 19990
    assert plan_charge_inr("advanced_annual") == 59990


def test_plan_charge_inr_unknown_is_none() -> None:
    from app.billing.usage import plan_charge_inr

    assert plan_charge_inr("") is None
    assert plan_charge_inr("no_such_plan") is None
