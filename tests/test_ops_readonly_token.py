"""OPS-008 — read-only ops API key.

Why: four consecutive day-closes were BLIND because the ops truth endpoints
(/api/ops/revenue-summary, /api/ops/hotqueue) only accepted a JWT admin session
and no read-only token existed. This key unlocks MEASUREMENT only.

These tests are the compliance spine for that key. If one fails, do NOT relax
the assertion — a relaxed assertion here is a security regression:

  * unset token            -> key path disabled entirely (fail-closed)
  * GET + allowlisted path -> allowed
  * any mutation           -> never allowed
  * /api/ops/hotqueue/action and every non-allowlisted path -> never allowed
  * wrong / empty token    -> never allowed
"""

from __future__ import annotations

import importlib

import pytest
from starlette.requests import Request

auth = importlib.import_module("app.api.auth_deps")
from app.config import settings  # noqa: E402

TOKEN = "test-ops-token-abc123"  # nosecret — test fixture, not a credential


class _Creds:
    def __init__(self, value: str) -> None:
        self.credentials = value


def _req(method: str, path: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "path": path,
            "raw_path": path.encode(),
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "root_path": "",
        }
    )


@pytest.fixture
def armed(monkeypatch):
    monkeypatch.setattr(settings, "ops_readonly_token", TOKEN, raising=False)
    return TOKEN


def test_unset_token_is_fail_closed(monkeypatch):
    """Not armed => disabled. A presented key must NOT be honoured."""
    monkeypatch.setattr(settings, "ops_readonly_token", "", raising=False)
    assert auth._ops_readonly_allows(_req("GET", "/api/ops/revenue-summary"), _Creds(TOKEN)) is False


def test_armed_allows_get_on_allowlisted_path(armed):
    assert auth._ops_readonly_allows(_req("GET", "/api/ops/revenue-summary"), _Creds(TOKEN)) is True
    assert auth._ops_readonly_allows(_req("GET", "/api/ops/hotqueue"), _Creds(TOKEN)) is True


def test_wrong_token_rejected(armed):
    assert auth._ops_readonly_allows(_req("GET", "/api/ops/revenue-summary"), _Creds("nope")) is False


def test_empty_token_rejected(armed):
    assert auth._ops_readonly_allows(_req("GET", "/api/ops/revenue-summary"), _Creds("")) is False
    assert auth._ops_readonly_allows(_req("GET", "/api/ops/revenue-summary"), None) is False


def test_mutation_never_allowed(armed):
    """POST on an allowlisted path must still fall through to the admin path."""
    assert auth._ops_readonly_allows(_req("POST", "/api/ops/hotqueue"), _Creds(TOKEN)) is False
    assert auth._ops_readonly_allows(_req("DELETE", "/api/ops/revenue-summary"), _Creds(TOKEN)) is False


def test_hotqueue_action_never_allowed(armed):
    """The one endpoint that MUST stay admin-only. Explicitly pinned."""
    assert auth._ops_readonly_allows(_req("POST", "/api/ops/hotqueue/action"), _Creds(TOKEN)) is False
    assert auth._ops_readonly_allows(_req("GET", "/api/ops/hotqueue/action"), _Creds(TOKEN)) is False
    assert (("POST", "/api/ops/hotqueue/action") not in auth.OPS_READONLY_ALLOWLIST)
    assert (("GET", "/api/ops/hotqueue/action") not in auth.OPS_READONLY_ALLOWLIST)


def test_non_allowlisted_paths_rejected(armed):
    for path in ("/api/ops/other", "/api/billing/invoices", "/api/admin/anything", "/health", "/"):
        assert auth._ops_readonly_allows(_req("GET", path), _Creds(TOKEN)) is False, path


def test_allowlist_contains_only_gets():
    for method, _path in auth.OPS_READONLY_ALLOWLIST:
        assert method == "GET"
