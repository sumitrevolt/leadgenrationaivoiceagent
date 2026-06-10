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

Engine: app/platform/dpdp.py (atomic rewrites, .bak copies, audit log hash-only).
KABHI scheduler-wired nahi — erasure sirf explicit admin call.
Mount (main.py): `app.include_router(privacy_ops_router, prefix="/api")`
(creative.py pattern).
"""

from __future__ import annotations

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
    return await dpdp.erase_subject(
        body.phone, body.email, dry_run=body.dry_run, actor=str(actor)
    )


__all__ = ["router"]
