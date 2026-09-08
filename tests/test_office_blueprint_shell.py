"""Blueprint Virtual Office shell — INERT-flag proof, fallback, and security drift locks.

Matrix: docs/UNITY_VIRTUAL_OFFICE_SECURITY.md §5 (S1-S9).
- Static tests (S4-S7, S9, geometry drift-lock) are hermetic: no app import.
- Route tests (S1-S3, S8) use FastAPI TestClient on app.main.

Backend guarantees (admin auth on snapshot, customer tenant isolation, etc.) are covered by
EXISTING suites (test_customer_tenant_isolation_authenticated.py etc.) — not re-proven here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHELL_PATH = ROOT / "frontend" / "office_blueprint.html"
OFFICE_MAP_PATH = ROOT / "frontend" / "office_map.html"
CONTRACT_PATH = ROOT / "docs" / "UNITY_OFFICE_API_CONTRACT.md"

# Canonical bridge allowlist — must match UNITY_OFFICE_API_CONTRACT.md §4 AND the shell.
DOCUMENTED_ACTIONS = {
    "open_command_center",
    "open_customer_360",
    "open_delivery_proof",
    "open_approval",
    "open_setup",
    "open_reports",
    "open_social_connect",
    "open_billing",
    "open_support",
    "open_agent_details",
    "refresh_office_state",
}


@pytest.fixture(scope="module")
def shell_html() -> str:
    assert SHELL_PATH.is_file(), "office_blueprint.html missing"
    return SHELL_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Static security checks (hermetic)
# ---------------------------------------------------------------------------


def test_s4_no_secret_shaped_literals(shell_html):
    patterns = [
        r"sk_[A-Za-z0-9]{8,}",  # provider secret keys
        r"AKIA[0-9A-Z]{16}",  # AWS
        r"postgres(ql)?://",  # DB URLs
        r"redis://",  # Redis URLs
        r"eyJ[A-Za-z0-9_\-]{20,}",  # JWT literals
        r"whsec_[A-Za-z0-9]{8,}",  # webhook secrets
    ]
    for pat in patterns:
        assert not re.search(pat, shell_html), f"secret-shaped literal matches {pat}"


def test_s5_bridge_allowlist_matches_contract_doc(shell_html):
    # actions defined in the shell's BRIDGE_ACTIONS object
    block = shell_html.split("const BRIDGE_ACTIONS", 1)[1].split("};", 1)[0]
    shell_actions = set(re.findall(r"^\s*([a-z0-9_]+):", block, re.M))
    assert shell_actions == DOCUMENTED_ACTIONS, (
        f"shell allowlist drifted: extra={shell_actions - DOCUMENTED_ACTIONS}, "
        f"missing={DOCUMENTED_ACTIONS - shell_actions}"
    )
    # contract doc lists the same actions (drift lock against docs)
    doc = CONTRACT_PATH.read_text(encoding="utf-8")
    doc_actions = set(re.findall(r"^\|\s*`([a-z0-9_]+)`\s*\|", doc, re.M))
    assert doc_actions == DOCUMENTED_ACTIONS, (
        f"contract doc drifted: extra={doc_actions - DOCUMENTED_ACTIONS}, "
        f"missing={DOCUMENTED_ACTIONS - doc_actions}"
    )


def test_s6_no_hardcoded_customer_data(shell_html):
    low = shell_html.lower()
    for banned in ("jiya", "makeover", "₹1,999", "₹5,999", "invoice inv/"):
        assert banned not in low, f"hard-coded customer/plan data found: {banned!r}"


def test_s7_shell_fetches_only_allowlisted_api_paths(shell_html):
    api_paths = set(re.findall(r"/api/[a-zA-Z0-9_\-/{}.]*", shell_html))
    allowed = {"/api/platform/office/snapshot"}
    assert api_paths <= allowed, f"unexpected API paths in shell: {api_paths - allowed}"


def test_s9_no_wildcard_postmessage(shell_html):
    assert "postMessage" not in shell_html, (
        "shell must not use postMessage; if introduced, pin same-origin (never '*') "
        "and update UNITY_VIRTUAL_OFFICE_SECURITY.md §3 + this test"
    )


def test_room_geometry_mirrors_office_map(shell_html):
    """ROOM_GEOM in the shell must stay 1:1 with office_map.html OFFICE.ROOMS (drift lock)."""
    office_map = OFFICE_MAP_PATH.read_text(encoding="utf-8")
    room_ids = [
        "coordinator",
        "lead_lab",
        "sales_crm",
        "voice_team",
        "marketing_team",
        "qa_audit",
        "platform_engineering",
        "admin_finance",
    ]
    for rid in room_ids:
        assert f'"{rid}"' in shell_html or f"'{rid}'" in shell_html, f"shell missing room {rid}"
        assert rid in office_map, f"office_map missing room {rid} — canonical layout changed?"
    # spot-check one geometry literal pair (coordinator strip 1200x120)
    assert re.search(r"coordinator[^\n]*w:\s*1200\s*,\s*h:\s*120", shell_html), (
        "coordinator geometry drifted from office_map OFFICE.ROOMS"
    )


def test_bridge_ids_are_sanitized(shell_html):
    assert "ID_RE" in shell_html and "{1,64}" in shell_html, "id sanitization regex missing"
    assert "rejected non-allowlisted action" in shell_html, "allowlist rejection path missing"


# ---------------------------------------------------------------------------
# Route behavior (TestClient) — INERT-flag proof
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def _is_office_map(resp) -> bool:
    return b"office_map" in resp.content or b"Operating HQ" in resp.content


def _is_shell(resp) -> bool:
    return b"Blueprint Virtual Office" in resp.content


def test_s1_default_serves_existing_map_when_flag_unset(client, monkeypatch):
    monkeypatch.delenv("UNITY_VIRTUAL_OFFICE_ENABLED", raising=False)
    r = client.get("/app/office")
    assert r.status_code == 200
    assert _is_office_map(r) and not _is_shell(r)


def test_s2_mode3d_with_flag_off_serves_existing_map(client, monkeypatch):
    monkeypatch.delenv("UNITY_VIRTUAL_OFFICE_ENABLED", raising=False)
    r = client.get("/app/office", params={"mode": "3d"})
    assert r.status_code == 200
    assert _is_office_map(r) and not _is_shell(r), "flag OFF must be fully INERT"


def test_s2b_mode_map_always_serves_existing_map(client, monkeypatch):
    monkeypatch.setenv("UNITY_VIRTUAL_OFFICE_ENABLED", "1")
    r = client.get("/app/office", params={"mode": "map"})
    assert r.status_code == 200
    assert _is_office_map(r) and not _is_shell(r)


def test_s3_mode3d_with_flag_on_serves_shell(client, monkeypatch):
    monkeypatch.setenv("UNITY_VIRTUAL_OFFICE_ENABLED", "1")
    r = client.get("/app/office", params={"mode": "3d"})
    assert r.status_code == 200
    assert _is_shell(r)


def test_s8_unity_static_mount_guarded(client):
    """No build dir committed → mount absent → 404 (never a boot failure)."""
    unity_dir = ROOT / "frontend" / "office_unity"
    if unity_dir.is_dir():
        pytest.skip("office_unity build present — mount active by design")
    r = client.get("/static/office-unity/Build/LeadGenVirtualOffice.loader.js")
    assert r.status_code in (404, 405)


# ---------------------------------------------------------------------------
# Customer office route + customer shell (Milestone E)
# ---------------------------------------------------------------------------

CUSTOMER_SHELL_PATH = ROOT / "frontend" / "office_customer_blueprint.html"

# Customer bridge allowlist = strict SUBSET of the documented set — NO admin actions.
CUSTOMER_ACTIONS = {
    "open_setup",
    "open_reports",
    "open_social_connect",
    "open_billing",
    "open_support",
    "open_approval",
    "open_delivery_proof",
    "refresh_office_state",
}
ADMIN_ONLY_ACTIONS = {"open_command_center", "open_customer_360", "open_agent_details"}


@pytest.fixture(scope="module")
def customer_shell_html() -> str:
    assert CUSTOMER_SHELL_PATH.is_file(), "office_customer_blueprint.html missing"
    return CUSTOMER_SHELL_PATH.read_text(encoding="utf-8")


def test_c1_customer_route_flag_off_redirects_to_dashboard(client, monkeypatch):
    monkeypatch.delenv("UNITY_CUSTOMER_OFFICE_ENABLED", raising=False)
    r = client.get("/app/customer/office", params={"mode": "3d"}, follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/app/customer"


def test_c2_customer_route_default_redirects_even_with_flag_on(client, monkeypatch):
    monkeypatch.setenv("UNITY_CUSTOMER_OFFICE_ENABLED", "1")
    r = client.get("/app/customer/office", follow_redirects=False)
    assert r.status_code == 307, "no mode param → safe default (dashboard redirect)"


def test_c3_customer_route_flag_on_mode3d_serves_customer_shell(client, monkeypatch):
    monkeypatch.setenv("UNITY_CUSTOMER_OFFICE_ENABLED", "1")
    r = client.get("/app/customer/office", params={"mode": "3d"})
    assert r.status_code == 200
    assert b"CUSTOMER Blueprint Office SHELL" in r.content


def test_c4_admin_flag_does_not_open_customer_route(client, monkeypatch):
    """Flag independence: admin flag ON must not enable the customer shell."""
    monkeypatch.delenv("UNITY_CUSTOMER_OFFICE_ENABLED", raising=False)
    monkeypatch.setenv("UNITY_VIRTUAL_OFFICE_ENABLED", "1")
    r = client.get("/app/customer/office", params={"mode": "3d"}, follow_redirects=False)
    assert r.status_code == 307


def test_c5_customer_shell_fetches_only_customer_api_paths(customer_shell_html):
    api_paths = set(re.findall(r"/api/[a-zA-Z0-9_\-/{}.]*", customer_shell_html))
    assert api_paths, "customer shell must fetch customer APIs"
    for p in api_paths:
        assert p.startswith("/api/customer/"), f"non-customer API path in customer shell: {p}"


def test_c6_customer_shell_has_no_admin_actions(customer_shell_html):
    block = customer_shell_html.split("const BRIDGE_ACTIONS", 1)[1].split("};", 1)[0]
    actions = set(re.findall(r"^\s*([a-z0-9_]+):", block, re.M))
    assert actions == CUSTOMER_ACTIONS, (
        f"customer allowlist drifted: extra={actions - CUSTOMER_ACTIONS}, "
        f"missing={CUSTOMER_ACTIONS - actions}"
    )
    for a in ADMIN_ONLY_ACTIONS:
        assert a not in customer_shell_html, f"admin-only action {a} present in customer shell"
    assert actions <= DOCUMENTED_ACTIONS, (
        "customer actions must be a subset of the documented contract"
    )


def test_c7_customer_shell_no_admin_routes_or_secrets(customer_shell_html):
    for banned in ("/app/admin", "/app/control-center", "/api/platform/office"):
        assert banned not in customer_shell_html, (
            f"admin surface {banned} leaked into customer shell"
        )
    for pat in (r"sk_[A-Za-z0-9]{8,}", r"eyJ[A-Za-z0-9_\-]{20,}", r"postgres(ql)?://", r"redis://"):
        assert not re.search(pat, customer_shell_html), f"secret-shaped literal: {pat}"
    low = customer_shell_html.lower()
    for banned in ("jiya", "makeover", "₹1,999", "₹5,999"):
        assert banned not in low, f"hard-coded customer/plan data: {banned!r}"


def test_c8_customer_shell_never_sends_client_id(customer_shell_html):
    """Tenant is JWT-derived server-side; the shell must never send a client_id hint."""
    assert "client_id=" not in customer_shell_html
    assert "clientId" not in customer_shell_html


def test_c9_customer_shell_id_sanitization_present(customer_shell_html):
    assert "{1,64}" in customer_shell_html, "id regex missing in customer shell"
    assert "rejected non-allowlisted action" in customer_shell_html


def test_c10_shells_use_distinct_token_keys_no_shared_cache(shell_html, customer_shell_html):
    """Admin shell uses accessToken; customer shell uses lgai_token — no shared global cache."""
    assert 'localStorage.getItem("accessToken")' in shell_html
    assert 'localStorage.getItem("lgai_token")' in customer_shell_html
    assert "lgai_token" not in shell_html, "admin shell must not read the customer token"
    assert "accessToken" not in customer_shell_html, "customer shell must not read the admin token"


# ---------------------------------------------------------------------------
# Bridge ID fuzz — malicious ids must fail the shell's ID_RE (both shells)
# ---------------------------------------------------------------------------

MALICIOUS_IDS = [
    "../../../etc/passwd",
    "<script>alert(1)</script>",
    "a" * 65,
    "room id with spaces",
    "javascript:alert(1)",
    "room/../../admin",
    "room%2e%2e",
    "тест",
    "",
]


def test_fuzz_ids_rejected_by_documented_regex():
    id_re = re.compile(r"^[a-zA-Z0-9_\-\.]{1,64}$")
    for bad in MALICIOUS_IDS:
        assert not id_re.match(bad), f"regex must reject {bad!r}"
    for good in ("voice_team", "agent-1", "item.42", "a"):
        assert id_re.match(good), f"regex must accept {good!r}"
