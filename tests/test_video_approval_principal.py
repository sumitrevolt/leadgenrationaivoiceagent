"""Stage 3B — trusted approval principals.

The saga used to take a caller-supplied ``actor_subject`` string. The identity
map showed three of four surfaces passing the literal ``"admin"``, including a
WhatsApp reply from an unverified phone number. These tests pin the replacement:
a principal is SERVER-CONSTRUCTED from an authenticated object, and a surface
that cannot produce one refuses instead of approving as someone else.
"""

from __future__ import annotations

import hashlib

import pytest

from app.marketing.video_production import approval_principal as P
from app.marketing.video_production import approval_saga as SAGA

# ruff: noqa: F811
from tests.test_video_preview_identity import preview_client  # noqa: F401


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    from app.marketing import auto_content, delivery_ledger
    from app.marketing import video_media_paths as vmp

    # HERMETIC PRECONDITION (do not remove): approve() snapshots the artifact, and
    # prepare_snapshot refuses `insufficient_disk_headroom` when the DESTINATION
    # filesystem would drop below VIDEO_SNAPSHOT_MIN_FREE_PCT (default floor). These
    # tests assert approval IDENTITY, not disk policy, but without pinning the floor
    # they silently inherit the host's free space: on a developer box under the floor
    # every approval here returns 409 and four identity tests go red for a reason that
    # has nothing to do with identity. The floor itself is covered on its own in
    # tests/test_video_snapshot_primitive.py, so pinning it here removes no coverage.
    monkeypatch.setenv("VIDEO_SNAPSHOT_MIN_FREE_PCT", "1")

    monkeypatch.setattr(vmp, "approved_media_dir", lambda: tmp_path / "approved")
    for name, sub in (("_LEDGER_DIR", "ledger"), ("_QUEUE_DIR", "queue")):
        d = tmp_path / sub
        d.mkdir()
        monkeypatch.setattr(
            delivery_ledger if name == "_LEDGER_DIR" else auto_content, name, lambda d=d: str(d)
        )


class _User:
    """Stands in for the User ORM row require_admin returns."""

    def __init__(self, uid="u-123", admin=True, role="super_admin"):
        self.id = uid
        self.email = "someone@example.com"
        self.role = role
        self._admin = admin

    def can_access_admin(self):
        return self._admin


def _customer(cid="acme"):
    """Approval-grade customer principal: both server-side facts proven."""
    return P.from_customer_session(cid, tenant_verified=True, revocation_verified=True)


# --- construction contract ------------------------------------------------


def test_principal_is_immutable():
    import dataclasses

    p = _customer("acme")
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.subject_id = "other"


def test_customer_session_yields_tenant_principal_not_a_human():
    """Auth has no per-user id for customers, so the principal must not imply
    individual attribution."""
    p = _customer("acme")
    assert p.principal_type is P.PrincipalType.CUSTOMER_TENANT
    assert p.tenant_id == "acme"
    assert p.subject_id == "tenant:acme"
    assert p.auth_evidence_type is P.AuthEvidence.CUSTOMER_SESSION
    assert p.can_approve


def test_missing_session_subject_refuses():
    with pytest.raises(P.PrincipalRefused) as exc:
        P.from_customer_session("")
    assert exc.value.code == "approver_identity_unavailable"
    assert exc.value.status == 401


def test_admin_with_stable_id_gets_account_principal():
    p = P.from_admin_user(_User(), tenant_id="acme")
    assert p.principal_type is P.PrincipalType.ADMIN_ACCOUNT
    assert p.subject_id == "user:u-123"
    assert p.tenant_id == "acme"
    assert p.can_approve


def test_admin_without_stable_id_refuses_rather_than_hashing_email():
    class _NoId:
        email = "admin@example.com"
        role = "admin"

        def can_access_admin(self):
            return True

    with pytest.raises(P.PrincipalRefused) as exc:
        P.from_admin_user(_NoId(), tenant_id="acme")
    assert exc.value.code == "approver_identity_unavailable"


def test_ordinary_admin_refuses_without_the_on_behalf_capability():
    """CORRECTED (audit). A stable User.id is necessary, not sufficient.

    The earlier cut assigned the target record's tenant to any platform admin,
    which authorizes nothing — every admin could approve every tenant's video.
    Approving another tenant's content is a distinct capability.
    """
    with pytest.raises(P.PrincipalRefused) as exc:
        P.from_admin_user(_User(role="admin"), tenant_id="acme")
    assert exc.value.code == "admin_approval_capability_missing"


def test_rbac_member_roles_refuse():
    for role in ("manager", "agent", "viewer", ""):
        with pytest.raises(P.PrincipalRefused) as exc:
            P.from_admin_user(_User(role=role), tenant_id="acme")
        assert exc.value.code == "admin_approval_capability_missing"


def test_capability_is_role_based_never_person_based():
    """No email or display name may unlock approval authority."""
    import inspect

    # Strip the docstring: it legitimately NAMES the things it forbids, and a
    # naive substring scan would flag the explanation instead of the code.
    src = inspect.getsource(P._has_on_behalf_capability)
    code = src.split('"""')[-1].lower()
    for forbidden in ("email", "sumit", "display_name", "@"):
        assert forbidden not in code


def test_explicit_grant_can_only_narrow_never_widen():
    denied = _User(role="super_admin")
    denied.preferences = {P.CAP_APPROVE_ON_BEHALF: False}
    with pytest.raises(P.PrincipalRefused) as exc:
        P.from_admin_user(denied, tenant_id="acme")
    assert exc.value.code == "admin_approval_capability_missing"

    granted = _User(role="admin")
    granted.preferences = {P.CAP_APPROVE_ON_BEHALF: True}
    with pytest.raises(P.PrincipalRefused):
        # role gate first — a grant cannot promote an ordinary admin
        P.from_admin_user(granted, tenant_id="acme")


# --- customer session facts the dependency does not establish -------------


def test_unverified_tenant_refuses():
    with pytest.raises(P.PrincipalRefused) as exc:
        P.from_customer_session("acme", tenant_verified=False, revocation_verified=True)
    assert exc.value.code == "approval_tenant_unresolved"


def test_unverified_revocation_refuses_fail_closed():
    """require_customer's blacklist check fails OPEN. Approval may not."""
    with pytest.raises(P.PrincipalRefused) as exc:
        P.from_customer_session("acme", tenant_verified=True, revocation_verified=False)
    assert exc.value.code == "approval_session_unverified"
    assert exc.value.status == 401


def test_both_facts_default_to_false_so_stale_callers_fail_closed():
    with pytest.raises(P.PrincipalRefused):
        P.from_customer_session("acme")


def test_pii_can_never_become_a_subject():
    for bad in ("someone@example.com", "+919876543210", "9876543210"):
        with pytest.raises(P.PrincipalRefused):
            P.ApprovalPrincipal(
                subject_id=bad,
                tenant_id="acme",
                principal_type=P.PrincipalType.CUSTOMER_TENANT,
                channel=P.ApprovalChannel.CUSTOMER_DASHBOARD,
                auth_evidence_type=P.AuthEvidence.CUSTOMER_SESSION,
                approval_capability=P.ApprovalCapability.APPROVE,
            )


def test_capability_is_an_enum_not_a_request_boolean():
    with pytest.raises(P.PrincipalRefused):
        P.ApprovalPrincipal(
            subject_id="tenant:acme",
            tenant_id="acme",
            principal_type=P.PrincipalType.CUSTOMER_TENANT,
            channel=P.ApprovalChannel.CUSTOMER_DASHBOARD,
            auth_evidence_type=P.AuthEvidence.CUSTOMER_SESSION,
            approval_capability=True,  # type: ignore[arg-type]
        )


# --- token binding --------------------------------------------------------


def _bound(**over):
    rec = {
        "token_record_id": "atr_abc",
        "bound_tenant": "acme",
        "bound_record_id": "vid-1",
        "bound_revision": 0,
        "bound_sha256": "a" * 64,
        "expires_at": 4102444800,  # 2100
    }
    rec.update(over)
    return rec


def test_legacy_unbound_token_requires_regeneration_not_backfill():
    legacy = {"id": "x", "token": "t", "client_id": "acme", "status": "pending"}
    with pytest.raises(P.PrincipalRefused) as exc:
        P.from_approval_token(legacy, observed_sha256="a" * 64)
    assert exc.value.code == "approval_token_regeneration_required"


@pytest.mark.parametrize("field", P.REQUIRED_TOKEN_BINDINGS)
def test_each_missing_binding_refuses(field):
    with pytest.raises(P.PrincipalRefused) as exc:
        P.from_approval_token(_bound(**{field: ""}), observed_sha256="a" * 64)
    assert exc.value.code == "approval_token_regeneration_required"


def test_bound_token_yields_tenant_principal_and_token_is_not_identity():
    p = P.from_approval_token(_bound(), observed_sha256="A" * 64)
    assert p.tenant_id == "acme"
    assert p.subject_id == "tenant:acme"
    assert p.auth_evidence_type is P.AuthEvidence.APPROVAL_TOKEN
    # the RECORD id is evidence; the secret token never appears
    assert p.evidence_ref == "atr_abc"
    assert "t" != p.subject_id


def test_expired_token_refuses():
    with pytest.raises(P.PrincipalRefused) as exc:
        P.from_approval_token(_bound(expires_at=1), observed_sha256="a" * 64)
    assert exc.value.code == "approval_token_expired"


def test_absent_expiry_counts_as_expired():
    assert P.token_is_expired({}) if hasattr(P, "token_is_expired") else True
    from app.marketing import content_approval

    assert content_approval.token_is_expired({}) is True
    assert content_approval.token_is_expired({"expires_at": "nonsense"}) is True


def test_reused_token_refuses():
    with pytest.raises(P.PrincipalRefused) as exc:
        P.from_approval_token(_bound(consumed_at="2026-01-01"), observed_sha256="a" * 64)
    assert exc.value.code == "approval_token_already_used"


def test_content_drift_invalidates_the_token():
    with pytest.raises(P.PrincipalRefused) as exc:
        P.from_approval_token(_bound(), observed_sha256="b" * 64)
    assert exc.value.code == "approval_token_content_drift"


def test_unverifiable_content_refuses():
    with pytest.raises(P.PrincipalRefused) as exc:
        P.from_approval_token(_bound(), observed_sha256="")
    assert exc.value.code == "content_unverifiable"


def test_issuance_binds_all_required_fields(tmp_path, monkeypatch):
    from app.marketing import content_approval

    monkeypatch.setattr(content_approval, "_FILE", lambda: str(tmp_path / "a.jsonl"))
    sub = content_approval.submit("acme", {"title": "t"})
    assert sub["ok"]
    out = content_approval.bind_token_to_content(
        sub["approval"]["id"],
        tenant_id="acme",
        record_id="vid-1",
        revision=3,
        sha256="c" * 64,
        issued_by="user:u-1",
    )
    assert out["ok"]
    rec = content_approval.get_by_token(sub["approval"]["token"])
    for field in P.REQUIRED_TOKEN_BINDINGS:
        assert str(rec.get(field) or "").strip(), f"issuance did not bind {field}"
    assert rec["bound_revision"] == 3
    assert rec["issued_by"] == "user:u-1"
    # a bound token now resolves
    p = P.from_approval_token(rec, observed_sha256="c" * 64)
    assert p.tenant_id == "acme"


# --- surfaces that must refuse -------------------------------------------


def test_whatsapp_refuses_controlled():
    with pytest.raises(P.PrincipalRefused) as exc:
        P.from_whatsapp_inbound(from_phone="919876543210", tenant_id="acme")
    assert exc.value.code == "whatsapp_approval_identity_unavailable"


def test_harness_refuses_controlled():
    with pytest.raises(P.PrincipalRefused) as exc:
        P.from_harness_executor(agent="isha", tenant_id="acme")
    assert exc.value.code == "harness_approval_not_authorized"


def test_whatsapp_inbound_approve_no_longer_writes_an_approval(monkeypatch):
    """The end-to-end refusal: no approval, and nothing recorded as "admin"."""
    from app.marketing.video_production import cell, review_whatsapp

    called = {"n": 0}
    monkeypatch.setattr(
        cell,
        "approve_version",
        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or {"ok": True},
    )
    monkeypatch.setattr(
        review_whatsapp, "_clients_matching_phone", lambda d: [{"id": "acme"}], raising=False
    )
    out = review_whatsapp.ingest_inbound("919876543210", "APPROVE", "m1")
    assert out.get("handled") is not True or out.get("intent") != "approve"
    assert called["n"] == 0


# --- saga boundary --------------------------------------------------------


def test_saga_refuses_a_raw_actor_string(preview_client):
    """The old signature is gone; a string cannot be smuggled in."""
    out = SAGA.approve(
        record_id="vid-preview-1",
        expected_revision=0,
        expected_sha256="a" * 64,
        principal="customer:fixture-tenant-p",  # type: ignore[arg-type]
    )
    assert out["ok"] is False
    assert out["error"] == "approver_identity_unavailable"


def test_saga_refuses_principal_without_capability(preview_client):
    p = P.ApprovalPrincipal(
        subject_id="user:u-1",
        tenant_id="fixture-tenant-p",
        principal_type=P.PrincipalType.ADMIN_ACCOUNT,
        channel=P.ApprovalChannel.ADMIN,
        auth_evidence_type=P.AuthEvidence.ADMIN_SESSION,
        approval_capability=P.ApprovalCapability.NONE,
    )
    out = SAGA.approve(
        record_id="vid-preview-1",
        expected_revision=0,
        expected_sha256="a" * 64,
        principal=p,
    )
    assert out["error"] == "approval_not_permitted"


def test_wrong_tenant_fails_before_any_snapshot(preview_client, tmp_path):
    c, artifact = preview_client
    from app.marketing import video_ad_cycle as V
    from app.marketing.video_media_paths import approved_media_dir

    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    out = SAGA.approve(
        record_id="vid-preview-1",
        expected_revision=0,
        expected_sha256=digest,
        principal=_customer("someone-else"),
    )
    assert out["error"] == "approval_tenant_mismatch"

    # no artifact, no record mutation
    snap_root = approved_media_dir()
    assert not snap_root.exists() or not any(snap_root.rglob("*.mp4"))
    rec = (V._latest() or {}).get("vid-preview-1") or {}
    assert not rec.get("approval_txn")
    assert not rec.get("approved_at")


def test_valid_customer_principal_approves_and_records_identity(preview_client):
    c, artifact = preview_client
    from app.marketing import video_ad_cycle as V

    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    r = c.post(
        "/api/customer/videos/vid-preview-1/feedback",
        json={"action": "approve", "expected_revision": 0, "expected_content_sha256": digest},
    )
    assert r.status_code == 200
    rec = (V._latest() or {}).get("vid-preview-1") or {}
    assert rec["approval_actor"] == "tenant:fixture-tenant-p"
    assert rec["approval_channel"] == "customer_dashboard"
    assert rec["approval_principal_type"] == "customer_tenant"
    assert rec["approval_evidence_type"] == "customer_session"
    # the old self-named actor is gone
    assert rec["approval_actor"] != "admin"


def test_identical_principal_replay_is_idempotent(preview_client):
    c, artifact = preview_client
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    body = {"action": "approve", "expected_revision": 0, "expected_content_sha256": digest}
    first = c.post("/api/customer/videos/vid-preview-1/feedback", json=body)
    assert first.status_code == 200
    again = SAGA.approve(
        record_id="vid-preview-1",
        expected_revision=0,
        expected_sha256=digest,
        principal=_customer("fixture-tenant-p"),
    )
    assert again["ok"] is True
    assert again["already_finalized"] is True


def test_conflicting_principal_cannot_overwrite_the_original_actor(preview_client):
    c, artifact = preview_client
    from app.marketing import video_ad_cycle as V

    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert (
        c.post(
            "/api/customer/videos/vid-preview-1/feedback",
            json={"action": "approve", "expected_revision": 0, "expected_content_sha256": digest},
        ).status_code
        == 200
    )
    before = (V._latest() or {}).get("vid-preview-1") or {}

    out = SAGA.approve(
        record_id="vid-preview-1",
        expected_revision=0,
        expected_sha256=digest,
        principal=P.from_admin_user(_User(), tenant_id="fixture-tenant-p"),
    )
    assert out["error"] == "approval_transaction_conflict"
    after = (V._latest() or {}).get("vid-preview-1") or {}
    assert after["approval_actor"] == before["approval_actor"]
    assert after["approved_at"] == before["approved_at"]


# --- admin HTTP surface ---------------------------------------------------


def test_admin_approve_route_is_actually_executable(preview_client, monkeypatch):
    """Executes the admin route, not just its imports.

    This test exists because the first cut of that route raised HTTPException
    without importing it. Ruff, prod_check and the whole video suite stayed
    green — nothing CALLED the route, and an import-time gate cannot see a name
    that is only resolved on request. Every refusal branch is exercised here.
    """
    from app.api.auth_deps import require_admin
    from app.main import app as fastapi_app

    class _Admin:
        id = "u-admin-1"
        email = "root@example.com"
        role = "super_admin"  # holds approve_customer_video_on_behalf

        def can_access_admin(self):
            return True

    async def _as_admin():
        return _Admin()

    fastapi_app.dependency_overrides[require_admin] = _as_admin
    c, artifact = preview_client
    try:
        # missing hash -> 400, and the handler must not blow up on a bare name
        bad = c.post("/api/clientops/video-production/vid-preview-1/approve", json={})
        assert bad.status_code == 400
        assert "expected_content_sha256" in bad.text

        # unknown record -> 404
        missing = c.post(
            "/api/clientops/video-production/nope/approve",
            json={"expected_revision": 0, "expected_content_sha256": "a" * 64},
        )
        assert missing.status_code == 404

        # real approval records the admin subject, not the literal "admin"
        from app.marketing import video_ad_cycle as V

        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        ok = c.post(
            "/api/clientops/video-production/vid-preview-1/approve",
            json={"expected_revision": 0, "expected_content_sha256": digest},
        )
        assert ok.status_code == 200, ok.text
        rec = (V._latest() or {}).get("vid-preview-1") or {}
        assert rec["approval_actor"] == "user:u-admin-1"
        assert rec["approval_principal_type"] == "admin_account"
    finally:
        fastapi_app.dependency_overrides.pop(require_admin, None)


def test_admin_route_refuses_when_identity_has_no_stable_id(preview_client):
    from app.api.auth_deps import require_admin
    from app.main import app as fastapi_app

    class _NoId:
        email = "root@example.com"

        def can_access_admin(self):
            return True

    async def _as_admin():
        return _NoId()

    fastapi_app.dependency_overrides[require_admin] = _as_admin
    c, artifact = preview_client
    try:
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        r = c.post(
            "/api/clientops/video-production/vid-preview-1/approve",
            json={"expected_revision": 0, "expected_content_sha256": digest},
        )
        assert r.status_code == 403
        # The app's exception handler reshapes the body, so assert on the
        # payload rather than assuming FastAPI's default `detail` key.
        assert "approver_identity_unavailable" in r.text
        # and nothing sensitive rides along with the refusal
        assert "root@example.com" not in r.text
    finally:
        fastapi_app.dependency_overrides.pop(require_admin, None)


# --- leakage --------------------------------------------------------------


def test_audit_fields_carry_no_credential_or_pii():
    p = P.from_approval_token(_bound(), observed_sha256="a" * 64)
    blob = repr(p.audit_fields())
    for leak in ("@", "password", "Bearer"):
        assert leak not in blob


def test_refusal_responses_do_not_leak_tokens_or_paths(preview_client):
    c, artifact = preview_client
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    r = c.post(
        "/api/customer/videos/vid-preview-1/feedback",
        json={"action": "approve", "expected_revision": 99, "expected_content_sha256": digest},
    )
    body = r.text
    assert r.status_code >= 400
    for leak in ("/", "\\\\", "@"):
        assert leak not in str(r.json().get("detail") or "")
    assert "token" not in body.lower() or "approval_token_regeneration_required" in body
