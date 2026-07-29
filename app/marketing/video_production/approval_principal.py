"""Stage 3B — trusted approval principals.

Before this module the saga accepted an ``actor_subject`` STRING chosen by the
caller. The read-only identity map showed what that produced in practice:

  customer dashboard  ->  "customer:<client_id>"   (tenant, no user id)
  admin route         ->  "admin"                  (User object discarded)
  WhatsApp inbound    ->  "admin"                  (a phone reply, logged as admin)
  public token link   ->  "customer:approval_token"

Three of four collapsed to the literal ``"admin"``, so the audit trail could not
say who approved anything. A principal is therefore SERVER-CONSTRUCTED from an
authenticated object and never accepted from a request.

What this module deliberately does NOT do:

* It does not filter ``@`` or ``/`` and call the result verified. Character
  shape is not provenance — a string with no ``@`` can still be untrusted or
  PII. Trust comes from WHICH resolver built the principal.
* It does not hash an email or phone to manufacture a "non-PII" id. A hash of
  PII is still PII; it is a pseudonym, not an internal identity.
* It does not invent individual-human attribution where the auth system has
  none. Customer sessions carry only a tenant, so they yield an explicitly
  tenant-scoped principal.
* It does not create the missing WhatsApp phone-binding or harness
  authorization systems. Those surfaces refuse.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class PrincipalType(str, Enum):
    """WHAT was authenticated — not merely which endpoint was used."""

    #: A tenant account proved possession of a customer session. No individual
    #: human is identified, because the credential store has no per-user id.
    CUSTOMER_TENANT = "customer_tenant"
    #: A specific admin User row (stable DB id).
    ADMIN_ACCOUNT = "admin_account"


class AuthEvidence(str, Enum):
    CUSTOMER_SESSION = "customer_session"
    APPROVAL_TOKEN = "approval_token"  # nosecret - enum label, not a credential
    ADMIN_SESSION = "admin_session"


class ApprovalChannel(str, Enum):
    CUSTOMER_DASHBOARD = "customer_dashboard"
    APPROVAL_LINK = "approval_link"
    ADMIN = "admin"
    WHATSAPP = "whatsapp"
    HARNESS = "harness"


class ApprovalCapability(str, Enum):
    APPROVE = "approve"
    NONE = "none"


class PrincipalRefused(Exception):
    """Controlled refusal. ``code`` is a stable, non-sensitive reason string."""

    def __init__(self, code: str, *, status: int = 403):
        super().__init__(code)
        self.code = code
        self.status = status


# A subject id is an INTERNAL identifier. These patterns are a last-resort
# tripwire against a resolver regression, NOT the trust boundary.
_SUBJECT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_PHONE_SHAPED = re.compile(r"^\+?\d[\d\s-]{8,}$")


@dataclass(frozen=True)
class ApprovalPrincipal:
    """Immutable, server-created. There is no public constructor path that
    takes request input — every field is derived by a resolver below."""

    subject_id: str
    tenant_id: str
    principal_type: PrincipalType
    channel: ApprovalChannel
    auth_evidence_type: AuthEvidence
    approval_capability: ApprovalCapability
    #: Non-secret pointer to the credential (e.g. an approval-token RECORD id).
    #: Never the credential itself.
    evidence_ref: str = ""

    def __post_init__(self) -> None:
        for name in ("subject_id", "tenant_id"):
            val = getattr(self, name)
            if not isinstance(val, str) or not val.strip():
                raise PrincipalRefused("approver_identity_unavailable")
        if not _SUBJECT_RE.match(self.subject_id):
            raise PrincipalRefused("approver_identity_unavailable")
        if "@" in self.subject_id or _PHONE_SHAPED.match(self.subject_id):
            # Reached only via a resolver bug; PII must never become identity.
            raise PrincipalRefused("approver_identity_unavailable")
        for enum_field, enum_cls in (
            ("principal_type", PrincipalType),
            ("channel", ApprovalChannel),
            ("auth_evidence_type", AuthEvidence),
            ("approval_capability", ApprovalCapability),
        ):
            if not isinstance(getattr(self, enum_field), enum_cls):
                raise PrincipalRefused("approver_identity_unavailable")

    @property
    def can_approve(self) -> bool:
        return self.approval_capability is ApprovalCapability.APPROVE

    def audit_fields(self) -> dict[str, str]:
        """Safe to log or return. Contains no credential and no PII."""
        return {
            "subject": self.subject_id,
            "tenant": self.tenant_id,
            "type": self.principal_type.value,
            "channel": self.channel.value,
            "evidence": self.auth_evidence_type.value,
        }


# --------------------------------------------------------------------------
# Resolvers. Each takes an ALREADY-AUTHENTICATED server-side object.
# --------------------------------------------------------------------------


def from_customer_session(client_id: str) -> ApprovalPrincipal:
    """``require_customer`` returns a canonical client id and nothing else.

    The customer credential row (email / client_id / password_hash) has no
    per-user primary key, so two humans on one account are indistinguishable to
    the auth system. Claiming individual attribution here would be a lie in the
    audit trail — the principal is therefore explicitly TENANT-scoped.
    """
    cid = str(client_id or "").strip()
    if not cid:
        raise PrincipalRefused("approver_identity_unavailable", status=401)
    return ApprovalPrincipal(
        subject_id=f"tenant:{cid}",
        tenant_id=cid,
        principal_type=PrincipalType.CUSTOMER_TENANT,
        channel=ApprovalChannel.CUSTOMER_DASHBOARD,
        auth_evidence_type=AuthEvidence.CUSTOMER_SESSION,
        approval_capability=ApprovalCapability.APPROVE,
    )


def from_admin_user(user: Any, *, tenant_id: str) -> ApprovalPrincipal:
    """``require_admin`` returns the User ORM row, which DOES carry a stable
    ``User.id`` (uuid string, loaded from the DB, not from the token).

    Capability is derived from ``can_access_admin()`` — platform-level admin
    authority. A member who only passed ``require_admin`` through an RBAC module
    grant is NOT given approval authority here: passing a path check is not the
    same as holding approval authority over a tenant's content.
    """
    uid = str(getattr(user, "id", "") or "").strip()
    if not uid:
        # Only email/display-name available => no internal identity. Refuse
        # rather than hashing the email and calling it a subject.
        raise PrincipalRefused("approver_identity_unavailable")
    tid = str(tenant_id or "").strip()
    if not tid:
        raise PrincipalRefused("approval_tenant_unresolved")
    try:
        platform_admin = bool(user.can_access_admin())
    except Exception:
        platform_admin = False
    return ApprovalPrincipal(
        subject_id=f"user:{uid}",
        tenant_id=tid,
        principal_type=PrincipalType.ADMIN_ACCOUNT,
        channel=ApprovalChannel.ADMIN,
        auth_evidence_type=AuthEvidence.ADMIN_SESSION,
        approval_capability=(
            ApprovalCapability.APPROVE if platform_admin else ApprovalCapability.NONE
        ),
    )


#: Fields a token record must carry before it can authorize anything.
REQUIRED_TOKEN_BINDINGS = (
    "token_record_id",
    "bound_tenant",
    "bound_record_id",
    "bound_revision",
    "bound_sha256",
    "expires_at",
)


def from_approval_token(record: dict[str, Any], *, observed_sha256: str) -> ApprovalPrincipal:
    """The bearer token is CREDENTIAL EVIDENCE, never identity.

    The actor is the tenant the token authorizes; the token's non-secret record
    id is retained as evidence. Legacy tokens carry none of the required
    bindings and are refused for regeneration — they are not backfilled, because
    inventing a binding after the fact would assert a content identity nobody
    ever previewed.
    """
    from app.marketing import content_approval

    rec = record or {}
    # `or ""` would treat revision 0 — a legitimate first version — as missing,
    # so absence is tested explicitly rather than by truthiness.
    missing = [
        f
        for f in REQUIRED_TOKEN_BINDINGS
        if rec.get(f) is None or str(rec.get(f)).strip() in ("", "None")
    ]
    if missing:
        raise PrincipalRefused("approval_token_regeneration_required")
    if str(rec.get("consumed_at") or "").strip():
        raise PrincipalRefused("approval_token_already_used", status=409)
    if content_approval.token_is_expired(rec):
        raise PrincipalRefused("approval_token_expired", status=401)

    # Drift check: the bound hash is what the recipient was shown. If the file
    # has changed since issuance the token no longer authorizes these bytes.
    observed = str(observed_sha256 or "").strip().lower()
    if not observed:
        raise PrincipalRefused("content_unverifiable", status=409)
    if observed != str(rec.get("bound_sha256") or "").strip().lower():
        raise PrincipalRefused("approval_token_content_drift", status=409)

    tid = str(rec.get("bound_tenant") or "").strip()
    return ApprovalPrincipal(
        subject_id=f"tenant:{tid}",
        tenant_id=tid,
        principal_type=PrincipalType.CUSTOMER_TENANT,
        channel=ApprovalChannel.APPROVAL_LINK,
        auth_evidence_type=AuthEvidence.APPROVAL_TOKEN,
        approval_capability=ApprovalCapability.APPROVE,
        evidence_ref=str(rec.get("token_record_id") or ""),
    )


def from_whatsapp_inbound(*_a: Any, **_k: Any) -> ApprovalPrincipal:
    """Always refuses today, and the refusal is the correct behaviour.

    The route that actually reaches ``ingest_inbound`` is the WAHA self-host
    webhook, authenticated by a SHARED STATIC token in a query string that
    returns permissive when unset outside production. A shared secret is not
    per-message provider authenticity: anyone holding it can post an arbitrary
    ``from`` and speak as any tenant. The sender phone is routing data, not
    identity, and there is no review token bound to record/revision/hash.

    Building that binding system is out of this slice's scope by instruction.
    """
    raise PrincipalRefused("whatsapp_approval_identity_unavailable")


def from_harness_executor(*_a: Any, **_k: Any) -> ApprovalPrincipal:
    """Always refuses today.

    ``video.version.approve`` is registered AMBER + APPROVAL_REQUIRED, which the
    enforcer denies before any executor runs, and no executor is bound for it at
    all. ``RunContext.actor_id`` exists but is never populated or checked, so
    there is no verified executor subject to build a principal from. Shadow mode
    is a pure evaluator and must never mutate.
    """
    raise PrincipalRefused("harness_approval_not_authorized")


__all__ = [
    "REQUIRED_TOKEN_BINDINGS",
    "ApprovalCapability",
    "ApprovalChannel",
    "ApprovalPrincipal",
    "AuthEvidence",
    "PrincipalRefused",
    "PrincipalType",
    "from_admin_user",
    "from_approval_token",
    "from_customer_session",
    "from_harness_executor",
    "from_whatsapp_inbound",
]
