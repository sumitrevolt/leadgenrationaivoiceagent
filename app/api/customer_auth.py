"""Customer (client) login portal — self-contained, non-breaking.

Marketing clients ko apna account: email+password login → JWT → apni leads/calls/
content dekhein. Reuses the platform JWT helpers (admin.create_access_token /
decode_token). Credentials ek ALAG store me (data/customer_auth.jsonl) — User model /
admin auth ko touch nahi karta (zero migration, zero break).

pbkdf2-sha256 (stdlib) hashing — koi naya dep nahi. Import-safe, never raises on import.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
from app.security.turnstile import verify_turnstile
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/customer/auth", tags=["Customer Portal"])
_security = HTTPBearer(auto_error=True)
_security_optional = HTTPBearer(auto_error=False)

_STORE = os.path.join("data", "customer_auth.jsonl")
_ITER = 120_000

# Account-lockout (2026-08-01, enterprise-audit fix): per-account failed-attempt
# counter + lockout — admin login pe pehle se hai (admin.py 5-fail -> 30min lock),
# customer login pe sirf per-IP 10/60 limit thi. Ab Redis-backed lockout bhi.
# Fail-open on Redis error (InMemoryCache fallback = rate-limiter convention) —
# metering-class control, NOT a compliance gate; loud log on error.
_LOCKOUT_MAX_ATTEMPTS = 5
_LOCKOUT_WINDOW_S = 900  # 15 min lock


def _lockout_fail_key(email: str) -> str:
    return f"customer:login:fail:{(email or '').strip().lower()}"


def _lockout_lock_key(email: str) -> str:
    return f"customer:login:lock:{(email or '').strip().lower()}"


async def _account_locked(email: str) -> bool:
    """True agar account abhi locked hai (too many failed attempts).

    Fail-open on Redis error: lockout is anti-brute-force metering, not a
    compliance gate — per-IP rate limit abhi bhi pehle fire karta hai.
    """
    try:
        from app.cache import get_redis_client

        redis = await get_redis_client()
        return bool(await redis.exists(_lockout_lock_key(email)))
    except Exception as e:
        logger.debug(f"[customer-auth] lockout check failed (fail-open): {e}")
        return False


async def _record_login_failure(email: str) -> None:
    """Failed attempt increment; >= _LOCKOUT_MAX_ATTEMPTS pe account lock (15min).

    Redis down = InMemoryCache fallback (in-process, request-scoped) — lockout
    degrade karta, kabhi raise nahi.
    """
    try:
        from app.cache import get_redis_client

        redis = await get_redis_client()
        fkey = _lockout_fail_key(email)
        n = await redis.incr(fkey)
        if n == 1:
            await redis.expire(fkey, _LOCKOUT_WINDOW_S)
        if n >= _LOCKOUT_MAX_ATTEMPTS:
            await redis.set(_lockout_lock_key(email), "1", ex=_LOCKOUT_WINDOW_S)
            logger.warning(
                f"[customer-auth] account locked 15min after {n} failed attempts "
                f"(email={str(email)[:120]})"
            )
    except Exception as e:
        logger.debug(f"[customer-auth] lockout record failed (fail-open): {e}")


async def _clear_login_failures(email: str) -> None:
    try:
        from app.cache import get_redis_client

        redis = await get_redis_client()
        await redis.delete(_lockout_fail_key(email), _lockout_lock_key(email))
    except Exception as e:
        logger.debug(f"[customer-auth] lockout clear failed (fail-open): {e}")


# --------------------------------------------------------------------------- #
# password hashing (stdlib pbkdf2) + jsonl credential store
# --------------------------------------------------------------------------- #
def _hash(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", (password or "").encode(), salt.encode(), _ITER)
    return f"pbkdf2${_ITER}${salt}${dk.hex()}"


def _verify(password: str, stored: str) -> bool:
    try:
        _algo, it, salt, h = stored.split("$", 3)
        dk = hashlib.pbkdf2_hmac("sha256", (password or "").encode(), salt.encode(), int(it))
        return secrets.compare_digest(dk.hex(), h)
    except Exception:
        return False


def _read() -> list[dict]:
    out: list[dict] = []
    try:
        if os.path.exists(_STORE):
            for ln in open(_STORE, encoding="utf-8"):
                ln = ln.strip()
                if ln:
                    try:
                        out.append(json.loads(ln))
                    except Exception:
                        pass
    except Exception:
        pass
    return out


def _write_all(rows: list[dict]) -> None:
    # Lock + atomic — auth store corrupt hua to saare customer logins tut jaate.
    from app.utils.file_lock import locked_rewrite

    content = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    if not locked_rewrite(_STORE, content):
        # fallback: direct write (lock util hi na ho to bhi auth kabhi na ruke)
        os.makedirs(os.path.dirname(_STORE) or ".", exist_ok=True)
        with open(_STORE, "w", encoding="utf-8") as f:
            f.write(content)

    # ENTERPRISE FIX (2026-07-10): JSONL store corruption = all customer logins
    # break with zero recovery. Hourly gzip backup so worst-case loss is <1 hour.
    # Keeps last 72 backups (~1.5 MB each * 72 = ~108 MB). Best-effort, never raises.
    try:
        import gzip
        import shutil
        import time as _backup_time

        _bkp_dir = os.path.join("data", "backups")
        os.makedirs(_bkp_dir, exist_ok=True)
        _ts = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")
        _bkp_path = os.path.join(_bkp_dir, f"customer_auth.{_ts}.jsonl.gz")

        # Only backup once per hour (dedup by filename)
        if not os.path.exists(_bkp_path):
            with open(_STORE, "rb") as _src, gzip.open(_bkp_path + ".tmp", "wb") as _dst:
                shutil.copyfileobj(_src, _dst)
            os.replace(_bkp_path + ".tmp", _bkp_path)

            # Prune: keep latest 72 backups
            _all = sorted(
                [
                    f
                    for f in os.listdir(_bkp_dir)
                    if f.startswith("customer_auth.") and f.endswith(".jsonl.gz")
                ],
                reverse=True,
            )
            for _old in _all[72:]:
                try:
                    os.unlink(os.path.join(_bkp_dir, _old))
                except OSError:
                    pass
    except Exception:
        pass  # Backup failure must never block auth writes


def _find(email: str) -> dict | None:
    e = (email or "").strip().lower()
    for r in _read():
        if r.get("email") == e:
            return r
    return None


def _marketing_cid(client_id: str) -> str:
    """Resolve a customer's auth/login id to the canonical MARKETING client id.

    UPI-activated customers log in with their billing/subscription id (e.g. Jiya
    `d79d690f61b3`), but all marketing content / brand / mini-site stores are
    keyed on the marketing id (`jiya-makeover`, which carries the billing id in
    `billing_client_ids`). Marketing content/dashboard reads MUST canonicalize
    or the customer sees an orphaned partial view. Billing/invoice reads must
    NOT use this — invoices are owned by the billing id. Never raises;
    `canonical_client_id` falls back to the raw id when no marketing record
    matches (so seed/demo clients keyed by their own id are unaffected)."""
    try:
        from app.marketing.clients_store import canonical_client_id

        return canonical_client_id(client_id) or client_id
    except Exception:
        return client_id


def _biz_name(client_id: str) -> str:
    try:
        from app.marketing.clients_store import get_client

        return str((get_client(_marketing_cid(client_id)) or {}).get("business_name") or "")
    except Exception:
        return ""


# --------------------------------------------------------------------------- #
# Plain-Hinglish content summary (admin "Aaj" overview pattern → customer side).
# Mirrors app/platform/today_overview.py: emoji-first status + chhota Hinglish
# sentence so a NON-technical customer ek nazar me apne content ki state samajh
# jaaye (kitne publish ho chuke, kitne approval ka wait kar rahe). NO LLM
# (instant + free), kabhi raise nahi, additive only — raw status field intact.
# auto_content status values: draft / approved / posted / skipped.
# --------------------------------------------------------------------------- #
_CONTENT_STATUS_HI: dict[str, tuple[str, str]] = {
    "posted": ("✅", "Publish ho chuka"),
    "approved": ("👍", "Approve ho gaya — publish ka wait"),
    "draft": ("📝", "Draft — aapki approval ka wait"),
    "skipped": ("⏭️", "Skip kiya gaya"),
}


def _friendly_content_status(status: str | None) -> dict:
    """Ek content item ka raw status → emoji + chhota Hinglish line (additive)."""
    st = str(status or "").strip().lower()
    emoji, label = _CONTENT_STATUS_HI.get(st, ("⏳", "Taiyaar ho raha hai"))
    return {"status_emoji": emoji, "status_label": label, "status_line": f"{emoji} {label}"}


def _content_summary(items: list) -> dict:
    """Customer content queue ka plain-Hinglish headline + counts. Kabhi raise nahi.
    Example: '📣 Aapke aaj 3 posts ready hain — 1 publish ho chuka, 2 approval ka wait kar rahe'."""
    counts = {"total": 0, "posted": 0, "approved": 0, "draft": 0, "skipped": 0}
    try:
        for it in items or []:
            counts["total"] += 1
            st = str((it or {}).get("status") or "").strip().lower()
            if st in counts:
                counts[st] += 1
    except Exception:
        pass
    total = counts["total"]
    if total == 0:
        return {
            "headline": "📣 Aaj ka content abhi ban raha hai — subah 7 baje tak aa jaata hai 🌅",
            "counts": counts,
        }
    parts: list[str] = []
    if counts["posted"]:
        parts.append(f"{counts['posted']} publish ho chuk{'a' if counts['posted'] == 1 else 'e'}")
    if counts["approved"]:
        parts.append(
            f"{counts['approved']} publish hone wal{'a' if counts['approved'] == 1 else 'e'}"
        )
    if counts["draft"]:
        parts.append(
            f"{counts['draft']} approval ka wait kar rah{'a' if counts['draft'] == 1 else 'e'}"
        )
    if counts["skipped"]:
        parts.append(f"{counts['skipped']} skip kiy{'a' if counts['skipped'] == 1 else 'e'}")
    tail = (" — " + ", ".join(parts)) if parts else ""
    headline = f"📣 Aapke aaj {total} post{'' if total == 1 else 's'} ready hain{tail}"
    return {"headline": headline, "counts": counts}


# --------------------------------------------------------------------------- #
# auth dependency
# --------------------------------------------------------------------------- #
async def require_customer(creds: HTTPAuthorizationCredentials = Depends(_security)) -> str:
    """Return the authenticated client_id from a customer JWT (role=customer).
    Check Redis blacklist for logged-out tokens."""
    try:
        from app.api.admin import decode_token

        payload = decode_token(creds.credentials)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("role") != "customer":
        raise HTTPException(status_code=403, detail="Customer token required")
    cid = payload.get("sub")
    if not cid:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    # Check if token is blacklisted (logged out)
    # Fail-CLOSED (2026-08-01, enterprise-audit fix): pehle Redis error pe token pass
    # ho jata tha — a REVOKED (logged-out) token Redis blip ke dauran chal sakta tha.
    # Admin-tier revocation is_revoked(fail_closed=True) 503 deta hai (auth_deps.py);
    # customer portal bhi customer-data gate hai — same fail-closed. Redis blip alert
    # (RedisMainNearFull/outage) pehle se fire hota; transient 503 availability blip
    # security hole se behtar hai.
    try:
        from app.cache import get_redis_client

        redis_client = await get_redis_client()
        token = creds.credentials
        blacklist_key = f"customer:logout:{token[:20]}"
        is_blacklisted = await redis_client.exists(blacklist_key)
        if is_blacklisted:
            raise HTTPException(status_code=401, detail="Token has been revoked (logged out)")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[require_customer] blacklist check failed — FAIL-CLOSED 503 (revoked-token "
            f"guard intact): {e}"
        )
        raise HTTPException(
            status_code=503,
            detail="Session store unavailable — thodi der me retry karein",
        )

    return str(cid)


async def optional_customer(
    creds: HTTPAuthorizationCredentials | None = Depends(_security_optional),
) -> str:
    """Optional customer auth — guest (no/invalid header) → "" (never raises).

    Used ONLY for public self-serve paths where a guest submission is legitimate
    (e.g. homepage UPI ref submit: no JWT yet, record lands pending, admin
    reaches out via payer_contact). A VALID customer token still returns the
    real client_id (activation path intact). A PRESENT-but-invalid token is
    still rejected (fail-closed) — only the absent-token case downgrades to
    guest; we never silently treat a tampered credential as anonymous.
    """
    if creds is None:
        return ""
    return await require_customer(creds)


# --------------------------------------------------------------------------- #
# endpoints
# --------------------------------------------------------------------------- #
def register_login(
    email: str, password: str, client_id: str, *, allow_reassign: bool = True
) -> dict:
    """Public-safe helper: ek email+password login banao/overwrite (client_id se link).

    Admin set-password AUR public self-serve signup (public_site.py) dono isko use karte —
    credential-store wiring ek hi jagah. Existing email overwrite hoti (idempotent).

    Loop 23 (2026-07-10) race-safety: signup path checks `login_exists(email)` at
    line ~550 then registers ~70 lines later. Under load, two concurrent submits
    with the same email can BOTH pass the initial check, then BOTH call
    register_login → last-writer-wins, leaving one orphan `client` row in
    clients_store. `allow_reassign=False` (public signup path) refuses to overwrite
    a row whose existing client_id differs — the second submit gets
    `{ok: False, error: "email_claimed"}` and can be handled as a normal 409. Admin
    set-password keeps the default `allow_reassign=True` (support scenarios need
    to re-target an email to a different client_id manually).
    """
    e = (email or "").strip().lower()
    cid = str(client_id).strip()
    existing_rows = _read()
    if not allow_reassign:
        for r in existing_rows:
            if r.get("email") == e:
                existing_cid = str(r.get("client_id") or "").strip()
                if existing_cid and existing_cid != cid:
                    logger.warning(
                        "[customer-auth] register_login refused cross-tenant overwrite "
                        "for email=%s incoming_cid=%s existing_cid=%s",
                        e,
                        cid,
                        existing_cid,
                    )
                    return {
                        "ok": False,
                        "error": "email_claimed",
                        "email": e,
                        "client_id": existing_cid,
                    }
                # Same client_id → idempotent overwrite is safe (real password rotation).
                break
    rows = [r for r in existing_rows if r.get("email") != e]
    rows.append(
        {
            "email": e,
            "client_id": cid,
            "password_hash": _hash(password),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _write_all(rows)
    return {"ok": True, "email": e, "client_id": cid}


def login_exists(email: str) -> bool:
    """True agar is email ka login already hai (public signup dedupe ke liye)."""
    return _find(email) is not None


def client_has_login(client_id: str) -> bool:
    """True agar is client_id pe pehle se koi login attached hai.

    Self-serve signup me ANTI-HIJACK guard: add_client phone/business_name pe dedupe
    karta — koi existing client ka naam de ke uspe login attach na kar paaye.
    """
    cid = str(client_id or "").strip()
    if not cid:
        return False
    try:
        return any(str(r.get("client_id") or "").strip() == cid for r in _read())
    except Exception:
        return False


def client_login_email(client_id: str) -> str | None:
    """Exact-client customer portal email, normalized; never raises.

    This is first-party contact data created by admin onboarding or the
    customer's own signup. Password hashes and any other auth fields never
    leave this module.
    """
    cid = str(client_id or "").strip()
    if not cid:
        return None
    try:
        for row in _read():
            if str(row.get("client_id") or "").strip() != cid:
                continue
            email = str(row.get("email") or "").strip().lower()
            return email or None
    except Exception:
        pass
    return None


def revoke_login_by_client(client_id: str) -> dict:
    """Revoke ALL portal logins attached to a client_id (admin customer removal).

    Removes every credential row for this client so the customer can no longer
    log in. Returns {ok, removed, emails}; never raises. The store's own backup
    (``_write_all`` hourly gzip) protects against accidental loss.
    """
    cid = str(client_id or "").strip()
    if not cid:
        return {"ok": False, "removed": 0, "emails": []}
    try:
        rows = _read()
        keep = [r for r in rows if str(r.get("client_id") or "").strip() != cid]
        removed = len(rows) - len(keep)
        emails = [
            str(r.get("email") or "").strip().lower()
            for r in rows
            if str(r.get("client_id") or "").strip() == cid
        ]
        if removed:
            _write_all(keep)
        return {"ok": True, "removed": removed, "emails": emails}
    except Exception as e:
        logger.warning(f"[customer-auth] revoke_login_by_client failed: {e}")
        return {"ok": False, "removed": 0, "emails": []}


class SetPwIn(BaseModel):
    email: str = Field(..., min_length=3, max_length=200)
    password: str = Field(..., min_length=6, max_length=128)
    client_id: str = Field(..., min_length=1, max_length=64)


@router.post("/set-password")
async def set_password(req: SetPwIn, current_user=Depends(require_admin)):
    """ADMIN: ek client ka login email+password set/reset karo (client_id se link)."""
    res = register_login(req.email, req.password, req.client_id)
    return {"ok": True, **(res or {})}


class LoginIn(BaseModel):
    email: str = Field(..., min_length=3, max_length=200)
    password: str = Field(..., min_length=1, max_length=128)


@router.post("/login", dependencies=[Depends(rate_limit("cust_login", 10, 60))])
async def customer_login(req: LoginIn):
    """Client login → JWT (role=customer, sub=client_id).

    H.2: If customer has 2FA enabled, returns {needs_2fa: true, challenge_token}
    instead of an access_token; customer then calls /api/customer/2fa/verify
    with the challenge + TOTP code to get the real JWT.
    """
    # Account lockout (2026-08-01): 5 failed attempts -> 15min lock. Per-IP
    # limiter (10/60) alag cheez hai — yeh ACCOUNT-level hai (known-email
    # credential-stuffing). 429/403 detail enum reveal na kare.
    if await _account_locked(req.email):
        try:
            from app.platform import automation_log_service as _als

            _als.log_event(
                job_type="login_locked",
                status="blocked",
                output_summary=f"Login blocked (account locked) for {(req.email or '')[:120]}",
                error_message="account_locked",
                triggered_by="customer_login",
            )
        except Exception as _log_err:
            logger.debug(f"[customer-auth] login_locked log emit skip: {_log_err}")
        raise HTTPException(
            status_code=429, detail="Too many failed attempts — thodi der me try karein"
        )
    rec = _find(req.email)
    if not rec or not _verify(req.password, rec.get("password_hash", "")):
        # Account-level failed-attempt counter (Redis). Fire-and-forget — login
        # response ke liye blocking nahi; best-effort.
        try:
            await _record_login_failure(req.email)
        except Exception as _lf_err:
            logger.debug(f"[customer-auth] lockout record skip: {_lf_err}")
        # Loop 8 (2026-07-10): admin observability for credential-stuffing spikes.
        # A single failure is boring; the ADR-064 automation-logs panel filter
        # (job_type=login_failed) surfaces the RATE so ops sees brute-force early.
        # Never leak WHICH factor failed (no user enumeration) — reason=invalid_creds
        # covers both unknown-email and bad-password. Best-effort, never blocks 401.
        try:
            from app.platform import automation_log_service as _als

            _als.log_event(
                # No client_id (we don't want a fake attribution row on unknown email).
                job_type="login_failed",
                status="failed",
                output_summary=f"Login attempt failed for {(req.email or '')[:120]}",
                error_message="invalid_creds",
                triggered_by="customer_login",
                meta_json={
                    "email": (req.email or "")[:200],
                    "known_email": rec is not None,
                },
            )
        except Exception as _log_err:
            logger.debug(f"[customer-auth] login_failed log emit skip: {_log_err}")
        raise HTTPException(status_code=401, detail="Invalid email or password")
    cid = str(rec["client_id"])
    # Successful password verify — clear any accumulated failed-attempts.
    try:
        await _clear_login_failures(req.email)
    except Exception as _cl_err:
        logger.debug(f"[customer-auth] lockout clear skip: {_cl_err}")
    # 2FA gate — if armed, do NOT issue the JWT here; force the verify step.
    _twofa = False
    try:
        from app.platform import customer_totp

        _twofa = bool(customer_totp.is_enabled(cid))
    except Exception as e:
        # 2FA STATE unreadable (module/infra error) — documented fail-open so an
        # infra problem doesn't lock the (no-2FA) majority out. LOUD log — pehle
        # yeh silent tha aur enabled-account bypass bhi isi except me chhup jata tha.
        logger.error("[customer-auth] 2FA state check failed for %s: %s", cid, e)
    if _twofa:
        try:
            return {
                "needs_2fa": True,
                "challenge_token": customer_totp.create_challenge(cid),
                "client_id": cid,
                "business_name": _biz_name(cid),
            }
        except Exception as e:
            # Account KNOWN 2FA-enabled — yahan fall-through = password-only
            # bypass of 2FA (security hole). Fail-CLOSED: login temporarily block.
            logger.error("[customer-auth] 2FA challenge failed for %s: %s", cid, e)
            raise HTTPException(
                status_code=503,
                detail="2FA verification temporarily unavailable — thodi der me try karein",
            )

    from app.api.admin import create_access_token

    token = create_access_token(cid, rec["email"], "customer")
    return {
        "access_token": token,
        "token_type": "bearer",
        "client_id": cid,
        "business_name": _biz_name(cid),
    }


_VALID_PLANS = {"starter", "growth", "advanced"}


def _plan_minutes_safe(plan: str) -> int:
    try:
        from app.billing.usage import plan_minutes

        return plan_minutes(plan)
    except Exception:
        return 0


class SignupIn(BaseModel):
    business_name: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=3, max_length=200)
    password: str = Field(..., min_length=6, max_length=128)
    phone: str = Field("", max_length=40)
    niche: str = Field("general", max_length=80)
    city: str = Field("", max_length=80)
    plan: str = Field("starter", max_length=30)


@router.post(
    "/signup", dependencies=[Depends(rate_limit("cust_signup", 5, 300)), Depends(verify_turnstile)]
)
async def customer_signup(req: SignupIn, request: Request):
    """MERGED (2026-06-27): self-serve signup ka SINGLE canonical implementation ab
    `app.api.public_site.public_signup` hai. Pehle yeh ek DUPLICATE signup code-path tha
    (do alag implementations — yeh wala lighter, public_site wala honeypot + anti-hijack +
    IP rate-limit + referral/lifecycle/journey hooks ke saath). Ab yeh route backward-compat
    ke liye zinda hai par usi ek implementation ko delegate karta — koi duplicate logic nahi.

    Result: /api/public/signup aur /api/customer/auth/signup ab IDENTICAL behave karte hain.
    Call-time import = no module-level circular import (public_site bhi customer_auth ko
    call-time pe hi import karta hai).

    NOTE (audit #7): canonical public_signup abhi `activate_plan`/`reset_usage_period`
    provision NAHI karta (yeh duplicate karta tha, par iska koi caller nahi tha). Woh
    provisioning fix public_signup me alag se aayega jab public_site.py ka parallel-edit
    settle ho jaye — taaki dono path consistently provision karein.
    """
    from app.api.public_site import SignupIn as _PublicSignupIn
    from app.api.public_site import public_signup

    body = _PublicSignupIn(
        business_name=req.business_name,
        email=req.email,
        password=req.password,
        phone=req.phone or "",
        niche=req.niche or "general",
        city=req.city or "",
        plan=req.plan or "starter",
    )
    return await public_signup(body, request)


def _first_hour_setup_state(client_rec: dict | None) -> dict:
    """Loop 9 (2026-07-10) — new-customer first-hour anti-churn signal.

    Brand-new customers (signed up in the last 60 min AND still zero content)
    see "koi activity nahi" everywhere on their dashboard because the
    auto_onboard Celery job takes 10-30 min to seed the KB + generate the
    first content pack. Returns a self-describing dict the FE renders as
    "🚀 Aapki AI team abhi setup ho rahi hai — X min me pehla content taiyaar"
    instead of empty state. Never raises; missing timestamp = inactive.
    """
    out = {"active": False, "minutes_elapsed": 0, "minutes_remaining": 0, "message": ""}
    if not client_rec:
        return out
    try:
        from datetime import datetime, timezone

        created_raw = client_rec.get("created_at") or client_rec.get("created")
        if not created_raw:
            return out
        # Support ISO string OR datetime; tolerate trailing Z.
        if isinstance(created_raw, str):
            s = created_raw.rstrip("Z")
            created = datetime.fromisoformat(s)
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
        else:
            created = created_raw
            if getattr(created, "tzinfo", None) is None:
                created = created.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        elapsed_min = int((now - created).total_seconds() // 60)
        if elapsed_min < 0 or elapsed_min >= 60:
            return out
        # Optional: skip if the client already has content queued — no need for
        # the empty-state banner once real activity exists.
        try:
            from app.marketing.auto_content import list_queue

            cid = str(client_rec.get("id") or "").strip()
            if cid and (list_queue(cid, limit=1) or []):
                return out
        except Exception:
            pass
        remaining = max(1, 30 - elapsed_min)  # tuned to auto_onboard's typical 10-30 min
        out.update(
            {
                "active": True,
                "minutes_elapsed": elapsed_min,
                "minutes_remaining": remaining,
                "message": (
                    f"🚀 Aapki AI team abhi setup ho rahi hai — "
                    f"~{remaining} min me pehla content taiyaar hoga."
                ),
            }
        )
    except Exception:
        pass
    return out


class ChangePwIn(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=6, max_length=128)


# Same block-list as Loop 13B (public_site.py) — keep centralized here so a
# password rotation cannot land on a known-breached string post-signup either.
_BREACHED_PASSWORDS = {
    "password",
    "password1",
    "123456",
    "12345678",
    "123456789",
    "1234567890",
    "qwerty",
    "abc123",
    "111111",
    "000000",
    "admin",
    "welcome",
    "letmein",
    "iloveyou",
    "monkey",
    "dragon",
    "master",
    "shadow",
    "sunshine",
    "princess",
}


@router.post(
    "/change-password",
    dependencies=[Depends(rate_limit("cust_pw_change", 5, 300))],
)
async def customer_change_password(
    req: ChangePwIn,
    client_id: str = Depends(require_customer),
):
    """Loop 19 (2026-07-10) — customer self-serve password change.

    Verifies the old password against the JSONL store, applies the same
    Loop 13B breached-password block-list to the new value, then rewrites
    the credential row via `register_login` (idempotent overwrite). Emits a
    `password_changed` AutomationLog row for admin visibility (mirrors
    Loops 2/3B/7/8 pattern). Never leaks whether the account exists — the
    dependency injection layer already rejected an invalid JWT, so we're
    guaranteed to have a legitimate `client_id` at this point.
    """
    # 1) Find this client's email from the store (client_id is authoritative).
    #    NOTE: never take email from a request body — sub in the JWT is truth.
    row = None
    for r in _read():
        if str(r.get("client_id") or "").strip() == client_id:
            row = r
            break
    if row is None:
        # Legitimate client_id but no credential row (edge case: legacy accounts
        # created before customer_auth existed, or store corruption). Log for ops
        # then return a 409 — customer can email support for a manual reset.
        logger.warning("[customer-auth] change-password: no credential row for cid=%s", client_id)
        raise HTTPException(
            status_code=409, detail="Account credentials nahi mile — support se contact karo."
        )

    # 2) Verify old password (constant-time via _verify).
    if not _verify(req.old_password, row.get("password_hash", "")):
        # Emit a login_failed-style admin log so brute-force against change-password
        # is caught by the same monitor Loop 8 wired.
        try:
            from app.platform import automation_log_service as _als

            _als.log_event(
                client_id=client_id,
                job_type="password_change_failed",
                status="failed",
                error_message="invalid_old_password",
                triggered_by="customer_change_password",
                meta_json={"email": str(row.get("email") or "")[:200]},
            )
        except Exception as _e:
            logger.debug(f"[customer-auth] change-password log emit skip: {_e}")
        raise HTTPException(status_code=401, detail="Purana password galat hai.")

    # 3) Reject known-breached new password (Loop 13B parity).
    if (req.new_password or "").strip().lower() in _BREACHED_PASSWORDS:
        raise HTTPException(
            status_code=422,
            detail="Yeh naya password bahut common hai — kuch alag choose karein.",
        )
    # 4) Reject no-op reset (old == new — hint at a mistake).
    if req.old_password == req.new_password:
        raise HTTPException(
            status_code=422,
            detail="Naya password purana wale se alag hona chahiye.",
        )

    # 5) Update credentials. register_login is idempotent (email match dedupe + overwrite).
    email = str(row.get("email") or "").strip()
    if not email:
        raise HTTPException(
            status_code=500, detail="Account row corrupt — support se contact karo."
        )
    register_login(email, req.new_password, client_id)

    # 6) Emit admin AutomationLog for security audit trail.
    try:
        from app.platform import automation_log_service as _als

        _als.log_event(
            client_id=client_id,
            job_type="password_changed",
            status="success",
            output_summary=f"Password rotated for {email}",
            triggered_by="customer_change_password",
            meta_json={"email": email},
        )
    except Exception as _e:
        logger.debug(f"[customer-auth] change-password success log emit skip: {_e}")

    return {"ok": True, "message": "Password badal gaya — agli baar naye password se login karo."}


@router.get("/me")
async def me(client_id: str = Depends(require_customer)):
    # product drives which customer dashboard the client lands on
    # (marketing | voice | combo). ADR-009 two-product split.
    client_rec: dict | None = None
    try:
        from app.marketing.clients_store import get_client

        client_rec = get_client(_marketing_cid(client_id))
        product = str((client_rec or {}).get("product") or "marketing").strip().lower()
    except Exception:
        product = "marketing"
    if product not in ("marketing", "voice", "combo"):
        product = "marketing"
    return {
        "client_id": client_id,
        "business_name": _biz_name(client_id),
        "product": product,
        "first_hour_setup": _first_hour_setup_state(client_rec),
    }


@router.post("/logout")
async def logout(
    creds: HTTPAuthorizationCredentials = Depends(_security),
    client_id: str = Depends(require_customer),
):
    """Invalidate customer JWT token (Redis blacklist + return 200)."""
    try:
        from app.cache import get_redis_client

        redis_client = await get_redis_client()
        token = creds.credentials
        # Extract expiry from JWT to set Redis TTL
        from app.api.admin import decode_token

        payload = decode_token(token)
        exp = payload.get("exp", 0)
        ttl = max(1, exp - int(datetime.now(timezone.utc).timestamp()))
        # Blacklist the token
        blacklist_key = f"customer:logout:{token[:20]}"
        await redis_client.setex(blacklist_key, ttl, "1")
        logger.info(f"[logout] customer {client_id} invalidated")
    except Exception as e:
        logger.warning(f"[logout] blacklist failed: {e} (frontend logout still valid)")
    return {"message": "Logged out successfully"}


@router.get("/portal/content")
async def portal_content(client_id: str = Depends(require_customer)):
    """Customer ka APNA marketing content (Isha ke daily posts — ready/posted) +
    mini-site/bio/widget links. Dashboard '📣 Aapka Content' section ka payload.
    Ownership token se enforced; kabhi raise nahi (empty graceful).
    (2026-06-12 UX upgrade: pehle customer ko apna content dikhta hi nahi tha.)"""
    out: dict = {"items": [], "links": {}}
    # Marketing content is keyed on the canonical marketing id, not the
    # billing/login id the customer authenticates with (Jiya: d79d690f61b3 ->
    # jiya-makeover). Without this the portal showed an orphaned partial feed
    # (7 stray drafts) instead of the customer's real content bank.
    mcid = _marketing_cid(client_id)
    try:
        from app.marketing.auto_content import list_queue

        items = list_queue(mcid, limit=10) or []
        out["items"] = [
            {
                "id": i.get("id"),
                "date": i.get("date"),
                "type": i.get("type"),
                "title": i.get("title") or i.get("theme") or "",
                "caption": i.get("caption") or i.get("text") or "",
                "hashtags": i.get("hashtags") or [],
                "status": i.get("status"),
                "image_url": i.get("image_url") or "",
                # additive plain-Hinglish status (raw `status` field intact above)
                **_friendly_content_status(i.get("status")),
            }
            for i in items
        ]
    except Exception as e:
        logger.debug(f"portal content queue failed: {e}")
    # Plain-Hinglish at-a-glance summary (admin "🏠 Aaj" pattern → customer side).
    # Always present (empty queue → "ban raha hai" headline); never breaks items.
    out["summary"] = _content_summary(out["items"])
    try:
        from app.marketing.clients_store import get_client

        c = get_client(mcid) or {}
        slug = c.get("slug") or ""
        if slug:
            out["links"] = {
                "mini_site": f"/b/{slug}",
                "bio_link": f"/b/{slug}/bio",
                "digital_card": f"/b/{slug}/card",
            }
        out["business_name"] = c.get("business_name") or _biz_name(client_id)
        out["niche"] = c.get("niche") or ""
    except Exception as e:
        logger.debug(f"portal content client failed: {e}")
    return out


@router.get("/portal/invoices")
async def portal_invoices(client_id: str = Depends(require_customer)):
    """Customer ke APNE invoices (GST engine se) — ownership token se enforced."""
    try:
        from app.billing import gst_invoice

        # Voided invoices (accountant correction markers) customer portal me
        # nahi dikhte — sirf live bills. Admin list voided+flag dikhata hai.
        rows = [
            r
            for r in gst_invoice.list_invoices(500)
            if str(r.get("client_id")) == client_id and not r.get("voided")
        ]
        return {
            "invoices": [
                {
                    "number": r.get("number"),
                    "date": r.get("date"),
                    "description": r.get("description"),
                    "gross_inr": r.get("gross_inr"),
                    "plan": r.get("plan"),
                }
                for r in rows
            ]
        }
    except Exception:
        return {"invoices": []}


@router.get("/portal/invoice-html")
async def portal_invoice_html(number: str, client_id: str = Depends(require_customer)):
    """Apna invoice printable HTML (?number=INV/2026-27/0001) — ownership check ke saath."""
    from fastapi.responses import HTMLResponse

    try:
        from app.billing import gst_invoice

        inv = gst_invoice.get_by_number(number)
        if not inv or str(inv.get("client_id")) != client_id or inv.get("voided"):
            return {"error": "invoice not found"}
        return HTMLResponse(gst_invoice.invoice_html(inv))
    except Exception:
        return {"error": "invoice render error"}


@router.get("/portal/dashboard")
async def portal_dashboard(client_id: str = Depends(require_customer)):
    """Authenticated customer dashboard — sirf apna data (token ke client_id se)."""
    try:
        from app.api.customer_dashboard import _build_from_db, _build_from_files

        resp = _build_from_db(client_id=client_id, campaign=None)
        if resp is None:
            resp = _build_from_files(client_id=client_id, campaign=None)
        return resp
    except Exception as e:
        logger.error(f"portal dashboard failed: {e}")
        raise HTTPException(status_code=500, detail=f"dashboard failed: {e}")


# --------------------------------------------------------------------------- #
# Magic-link (passwordless) login — GATED `MAGIC_LINK=1` (default OFF).
# Reuses LIVE Hostinger SMTP. Single-use (redis NX) + 15-min expiry. Request kabhi
# email-enumeration leak nahi karta (generic response). Flag OFF = endpoints 404.
# --------------------------------------------------------------------------- #
def _magic_enabled() -> bool:
    return (os.getenv("MAGIC_LINK", "") or "").strip().lower() in ("1", "true", "yes", "on")


def _magic_ttl() -> int:
    try:
        return int(os.getenv("MAGIC_LINK_TTL_S", "900") or 900)  # 15 min
    except Exception:
        return 900


def _base_url() -> str:
    u = (os.getenv("PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
    return u or "https://leadsgenai.in"


def _mint_magic(client_id: str, email: str) -> str:
    from datetime import timedelta

    from app.utils.jwt_versioning import get_jwt_manager

    payload = {
        "sub": str(client_id),
        "email": (email or "").strip().lower(),
        "type": "magic",
        "jti": secrets.token_hex(16),
        "exp": datetime.now(timezone.utc) + timedelta(seconds=_magic_ttl()),
    }
    # SECURITY FIX (P0-5, 2026-07-19): Use JWT key manager for key versioning support
    jwt_mgr = get_jwt_manager()
    return jwt_mgr.encode(payload)


def _decode_magic(token: str) -> dict:
    from jose import JWTError

    from app.utils.jwt_versioning import get_jwt_manager

    try:
        # SECURITY FIX (P0-5, 2026-07-19): Use JWT key manager for key versioning support
        jwt_mgr = get_jwt_manager()
        payload = jwt_mgr.decode(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Link invalid ya expire ho gaya")
    if payload.get("type") != "magic" or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Link invalid")
    return payload


async def _consume_jti(jti: str) -> bool:
    """Single-use enforce: pehli baar True, dobara False. Redis down = True (fail-open,
    exp-only window). best-effort."""
    if not jti:
        return True
    try:
        from app.cache import get_redis_client

        r = await get_redis_client()
        # SET NX: agar pehle se hai => reused => None => reject.
        ok = await r.set(f"magiclink:used:{jti}", "1", nx=True, ex=_magic_ttl() + 60)
        return bool(ok)
    except Exception:
        return True  # redis unavailable => exp-only (15-min) window


async def _email_cooldown_ok(email: str) -> bool:
    """Per-email 60s cooldown (email-bomb se bachao). Fail-open."""
    try:
        from app.cache import get_redis_client

        r = await get_redis_client()
        ok = await r.set(f"magiclink:cd:{email}", "1", nx=True, ex=60)
        return bool(ok)
    except Exception:
        return True


async def _send_magic_email(email: str, link: str, biz: str) -> bool:
    try:
        from app.integrations.email_sender import EmailSender

        subject = "Aapka LeadGen AI login link"
        body = (
            f"Namaste{(' ' + biz) if biz else ''},\n\n"
            f"Apne LeadGen AI account me login karne ke liye is link pe click karein "
            f"(15 minute valid):\n\n{link}\n\n"
            "Agar aapne ye request nahi ki, to is email ko ignore karein.\n\n— LeadGen AI"
        )
        html = (
            f"<p>Namaste{(' ' + biz) if biz else ''},</p>"
            f"<p>Apne LeadGen AI account me login karne ke liye click karein (15 min valid):</p>"
            f'<p><a href="{link}" style="background:#2563eb;color:#fff;padding:10px 18px;'
            f'border-radius:8px;text-decoration:none;display:inline-block">Login karein</a></p>'
            f'<p style="color:#666;font-size:12px">Ya ye link: {link}</p>'
            "<p>Agar aapne ye request nahi ki, to ignore karein.</p><p>— LeadGen AI</p>"
        )
        return await EmailSender().send_email([email], subject, body, html_body=html)
    except Exception as e:
        logger.warning(f"magic-link email send failed: {e}")
        return False


class MagicRequestIn(BaseModel):
    email: str = Field(..., min_length=3, max_length=200)


@router.get("/magic-link/config")
async def magic_link_config():
    """Frontend ke liye: magic-link feature ON hai ya nahi (UI conditionally dikhaye)."""
    return {"enabled": _magic_enabled()}


@router.post("/magic-link/request", dependencies=[Depends(rate_limit("magic_req", 5, 300))])
async def magic_link_request(req: MagicRequestIn):
    """Email pe ek single-use login link bhejo. ENUMERATION-SAFE: response hamesha
    generic (chahe email registered ho ya na ho). GATED MAGIC_LINK=1."""
    if not _magic_enabled():
        raise HTTPException(status_code=404, detail="Not found")
    generic = {
        "ok": True,
        "message": "Agar ye email registered hai, to login link bhej diya gaya hai.",
    }

    email = (req.email or "").strip().lower()
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        return generic  # invalid email bhi generic — koi signal leak na ho

    rec = _find(email)
    if not rec:
        return generic  # unknown email — same response, koi enumeration nahi
    if not await _email_cooldown_ok(email):
        return generic  # spam guard — chup-chaap generic

    cid = str(rec.get("client_id") or "")
    token = _mint_magic(cid, email)
    link = f"{_base_url()}/app/login?magic={token}"
    # Fire-and-forget: SMTP ko inline await MAT karo — warna known-email response slow
    # (SMTP round-trip) = timing oracle = email enumeration (review finding #3/#4).
    # _send_magic_email khud apni exceptions nigalta hai (safe to detach).
    try:
        asyncio.create_task(_send_magic_email(email, link, _biz_name(cid)))
    except RuntimeError:
        await _send_magic_email(email, link, _biz_name(cid))  # no running loop (test/sync)
    return generic


class MagicVerifyIn(BaseModel):
    token: str = Field(..., min_length=10, max_length=4000)


@router.post("/magic-link/verify", dependencies=[Depends(rate_limit("magic_vrf", 10, 60))])
async def magic_link_verify(req: MagicVerifyIn):
    """Magic-link token verify → customer JWT (login.html ?magic= se POST hota). GATED."""
    if not _magic_enabled():
        raise HTTPException(status_code=404, detail="Not found")
    payload = _decode_magic(req.token)
    if not await _consume_jti(str(payload.get("jti") or "")):
        raise HTTPException(status_code=401, detail="Link pehle use ho chuka hai")

    from app.api.admin import create_access_token

    cid = str(payload["sub"])
    email = str(payload.get("email") or "")
    token = create_access_token(cid, email, "customer")
    return {
        "access_token": token,
        "token_type": "bearer",
        "client_id": cid,
        "business_name": _biz_name(cid),
    }
