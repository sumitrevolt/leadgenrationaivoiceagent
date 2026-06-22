"""Privacy Ops API — DPDP Act 2023 rights endpoints (/privacy promise -> real).

- POST /api/privacy/request            (PUBLIC, rate-limited 5/60s) — data-principal
                                        access/erasure/correction request intake.
- GET  /api/privacy/requests           (admin) — pending/processed requests.
- POST /api/privacy/requests/{id}/done (admin) — mark processed.
- POST /api/privacy/find               (admin) — kaunse stores me subject ka data hai.
- POST /api/privacy/export             (admin) — Right to Access full JSON export.
- POST /api/privacy/erase              (admin) — Right to Erasure. dry_run=True
                                        DEFAULT; real erase ke liye dry_run=false
                                        + confirm=true DONO chahiye (destructive).

DSAR bundle (data_privacy.py wrapper):
- POST /api/privacy/dsar/export        (admin) — export_subject_data (flat records).
- POST /api/privacy/dsar/delete        (admin) — delete_subject_data; gate DATA_ERASURE=1.
- POST /api/privacy/retention/run      (admin) — enforce_retention sweep; gate DATA_RETENTION=1.
- POST /api/privacy/anonymize          (admin) — anonymize_pii on arbitrary data.

Engine: app/platform/dpdp.py + app/platform/data_privacy.py.
KABHI scheduler-wired nahi — erasure sirf explicit admin call.
Mount (main.py): `app.include_router(privacy_ops_router, prefix="/api")`
(creative.py pattern).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/privacy", tags=["Privacy DPDP"])


# ------------------------------ Schemas ------------------------------------ #
class SubjectIn(BaseModel):
    phone: str | None = None
    email: str | None = None


class RequestIn(SubjectIn):
    type: str = "access"  # access | erasure | correction
    note: str | None = ""


class EraseIn(SubjectIn):
    dry_run: bool = True
    confirm: bool = False


# ------------------------- PUBLIC: request intake --------------------------- #
@router.post("/request", dependencies=[Depends(rate_limit("dpdp_req", 5, 60))])
async def submit_privacy_request(body: RequestIn):
    """DPDP request intake (public) — /privacy page se linked. Never raises."""
    from app.platform import dpdp

    res = dpdp.record_request(body.phone, body.email, body.type, body.note or "")
    if not res.get("ok"):
        return res
    return {
        **res,
        "message": (
            "Aapki request mil gayi hai — 30 din ke andar process hogi. "
            "Koi dikkat ho to Grievance Officer ko escalate kar sakte ho "
            "(details /privacy page par)."
        ),
    }


# ------------------------------ ADMIN: queue -------------------------------- #
@router.get("/requests")
async def get_requests(status: str | None = None, _user=Depends(require_admin)):
    """Privacy requests list (default sab; ?status=pending|done filter)."""
    from app.platform import dpdp

    rows = dpdp.list_requests(status=status)
    return {"ok": True, "count": len(rows), "requests": rows}


@router.post("/requests/{request_id}/done")
async def request_done(request_id: str, _user=Depends(require_admin)):
    """Request processed mark karo (export bheja / erase chal gaya)."""
    from app.platform import dpdp

    actor = getattr(_user, "email", None) or "admin"
    return dpdp.mark_request_done(request_id, actor=str(actor))


# --------------------------- ADMIN: find / export --------------------------- #
@router.post("/find")
async def find(body: SubjectIn, _user=Depends(require_admin)):
    """Discovery — {store: count} + masked preview + DB Lead count (best-effort)."""
    from app.platform import dpdp

    actor = getattr(_user, "email", None) or "admin"
    return await dpdp.find_subject(body.phone, body.email, actor=str(actor))


@router.post("/export")
async def export(body: SubjectIn, _user=Depends(require_admin)):
    """Right to Access — subject ka FULL data ek JSON me (admin-only, audited)."""
    from app.platform import dpdp

    actor = getattr(_user, "email", None) or "admin"
    return await dpdp.export_subject(body.phone, body.email, actor=str(actor))


# ------------------------------ ADMIN: erase -------------------------------- #
@router.post("/erase")
async def erase(body: EraseIn, _user=Depends(require_admin)):
    """Right to Erasure. dry_run=true (default) = sirf report. REAL erase =
    dry_run=false + confirm=true dono (double-gate — destructive operation).
    Har touched file ki .bak_dpdp_<ts> copy + atomic rewrite; DB Lead anonymize."""
    from app.platform import dpdp

    if not body.dry_run and not body.confirm:
        return {
            "ok": False,
            "error": (
                "Real erase ke liye confirm=true bhi bhejo (dry_run=false akela "
                "kaafi nahi — destructive operation hai). Pehle dry_run se dekho."
            ),
        }
    actor = getattr(_user, "email", None) or "admin"
    return await dpdp.erase_subject(body.phone, body.email, dry_run=body.dry_run, actor=str(actor))


# ---------------------------------------------------------------------------
# DSAR bundle — data_privacy.py wrapper endpoints
# ---------------------------------------------------------------------------


class DsarExportIn(BaseModel):
    identifier: str  # phone (10-digit) or email


class DsarDeleteIn(BaseModel):
    identifier: str
    confirm: bool = False  # must be True + DATA_ERASURE=1 for real erase


class RetentionRunIn(BaseModel):
    dry_run: bool = True  # False + DATA_RETENTION=1 gate = real purge


class AnonymizeIn(BaseModel):
    data: Any  # str or dict — PII will be masked


@router.post("/dsar/export")
async def dsar_export(body: DsarExportIn, _user=Depends(require_admin)):
    """DSAR Right-to-Access — flat record list across all stores + DB (best-effort).
    Wrapper over data_privacy.export_subject_data."""
    from app.platform import data_privacy

    return await data_privacy.export_subject_data(body.identifier)


@router.post("/dsar/delete")
async def dsar_delete(body: DsarDeleteIn, _user=Depends(require_admin)):
    """DSAR Right-to-Erasure. Default = DRY-RUN preview.
    Real erase: confirm=true + DATA_ERASURE=1 env gate DONO chahiye."""
    from app.platform import data_privacy

    return await data_privacy.delete_subject_data(
        identifier=body.identifier,
        confirm=body.confirm,
    )


@router.post("/retention/run")
async def retention_run(body: RetentionRunIn, _user=Depends(require_admin)):
    """Records older than RETENTION_DAYS (default 365) ka sweep.
    dry_run=true (default) = sirf report.
    Real purge: dry_run=false + DATA_RETENTION=1 env gate."""
    from app.platform import data_privacy

    return data_privacy.enforce_retention(dry_run=body.dry_run)


@router.post("/anonymize")
async def anonymize(body: AnonymizeIn, _user=Depends(require_admin)):
    """Arbitrary str ya dict me se PII mask karo (phone/email/name keys + embedded
    phone-runs). Preview / testing ke liye — poora data wapas karta hai, sirf masked."""
    from app.platform import data_privacy

    result = data_privacy.anonymize_pii(body.data)
    return {"ok": True, "anonymized": result}


__all__ = ["router"]
