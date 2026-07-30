"""Legacy reapproval scope — only empty txn_state may reopen."""

from __future__ import annotations

from app.marketing.video_production import approval_principal as P
from app.marketing.video_production import cell


def _principal():
    return P.ApprovalPrincipal(
        subject_id="user:u-admin-1",
        tenant_id="c1",
        principal_type=P.PrincipalType.ADMIN_ACCOUNT,
        channel=P.ApprovalChannel.ADMIN,
        auth_evidence_type=P.AuthEvidence.ADMIN_SESSION,
        approval_capability=P.ApprovalCapability.APPROVE,
    )


def _rec(**over):
    base = {
        "id": "va_legacy",
        "client_id": "c1",
        "revision": 0,
        "approved_version": 0,
        "status": "approved",
        "token": "tok",
        "video_path": "/tmp/x.mp4",
        "approved_content_sha256": "a" * 64,
        "approval_snapshot_path": "/tmp/snap.mp4",
    }
    base.update(over)
    return base


def test_finalized_is_already_decided(monkeypatch):
    from app.marketing import video_ad_cycle as V

    rec = _rec(approval_txn_state="finalized")
    monkeypatch.setattr(V, "list_all", lambda *a, **k: [rec])
    out = cell.approve_version("va_legacy", principal=_principal(), expected_revision=0)
    assert out.get("already_decided") is True


def test_empty_txn_legacy_may_reenter(monkeypatch):
    from app.marketing import video_ad_cycle as V
    from app.marketing.video_production import approval_saga

    rec = _rec(approval_txn_state="", approved_content_sha256="", approval_snapshot_path="")
    monkeypatch.setattr(V, "list_all", lambda *a, **k: [rec])
    called = {}

    def _approve(**kw):
        called.update(kw)
        return {"ok": True, "txn_id": "t"}

    monkeypatch.setattr(approval_saga, "approve", _approve)
    out = cell.approve_version(
        "va_legacy",
        principal=_principal(),
        expected_revision=0,
        expected_sha256="b" * 64,
    )
    assert out.get("ok") is True
    assert called.get("record_id") == "va_legacy"


def test_prepared_cannot_reenter(monkeypatch):
    from app.marketing import video_ad_cycle as V

    rec = _rec(approval_txn_state="prepared")
    monkeypatch.setattr(V, "list_all", lambda *a, **k: [rec])
    out = cell.approve_version("va_legacy", principal=_principal(), expected_revision=0)
    assert out.get("ok") is False
    assert out.get("error") == "approval_not_finalized"
    assert out.get("txn_state") == "prepared"


def test_decision_recorded_cannot_reenter(monkeypatch):
    from app.marketing import video_ad_cycle as V

    rec = _rec(approval_txn_state="decision_recorded")
    monkeypatch.setattr(V, "list_all", lambda *a, **k: [rec])
    out = cell.approve_version("va_legacy", principal=_principal(), expected_revision=0)
    assert out.get("ok") is False
    assert out.get("txn_state") == "decision_recorded"


def test_compensated_cannot_reenter(monkeypatch):
    from app.marketing import video_ad_cycle as V

    rec = _rec(approval_txn_state="compensated")
    monkeypatch.setattr(V, "list_all", lambda *a, **k: [rec])
    out = cell.approve_version("va_legacy", principal=_principal(), expected_revision=0)
    assert out.get("ok") is False
    assert out.get("txn_state") == "compensated"


def test_inconsistent_cannot_reenter(monkeypatch):
    from app.marketing import video_ad_cycle as V

    rec = _rec(approval_txn_state="inconsistent")
    monkeypatch.setattr(V, "list_all", lambda *a, **k: [rec])
    out = cell.approve_version("va_legacy", principal=_principal(), expected_revision=0)
    assert out.get("ok") is False
    assert out.get("txn_state") == "inconsistent"


def test_rejected_remains_terminal(monkeypatch):
    from app.marketing import video_ad_cycle as V

    rec = _rec(status="rejected", approval_txn_state="")
    monkeypatch.setattr(V, "list_all", lambda *a, **k: [rec])
    out = cell.approve_version("va_legacy", principal=_principal(), expected_revision=0)
    assert out.get("ok") is False
    assert out.get("error") == "video_review_not_pending"


def test_changes_requested_not_silent_approve(monkeypatch):
    from app.marketing import video_ad_cycle as V

    rec = _rec(status="changes_requested", approval_txn_state="")
    monkeypatch.setattr(V, "list_all", lambda *a, **k: [rec])
    out = cell.approve_version("va_legacy", principal=_principal(), expected_revision=0)
    assert out.get("ok") is False
    assert out.get("error") == "video_review_not_pending"


def test_harness_without_principal_cannot_trigger(monkeypatch):
    from app.marketing import video_ad_cycle as V

    rec = _rec(approval_txn_state="", status="pending")
    monkeypatch.setattr(V, "list_all", lambda *a, **k: [rec])
    out = cell.approve_version("va_legacy", principal=None, expected_revision=0)
    assert out.get("ok") is False
    assert out.get("error") == "approver_identity_unavailable"
