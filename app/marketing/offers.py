"""offers.py — immutable commercial offers (orders) bound to a sales deal.

Issue #240. An interested prospect used to receive a UPI link whose only context
was ``tn=LeadsGenAI <business name>``. A business name is not a payment
reference: it is not unique, so an incoming bank credit could not be mapped back
to a specific deal, and provisioning could never key off it.

WHY A SEPARATE ENTITY, NOT FIELDS ON THE DEAL
---------------------------------------------
``sales_pipeline.upsert_deal`` dedupes by phone/email and RETURNS the existing
row, so a deal is long-lived — one per prospect, for the life of the
relationship. Over that life a prospect can legitimately receive several
distinct commercial offers: the Main -> Combo upgrade path (₹1,999 -> ₹5,999),
the Voice bands, and the repeat ``topup_100`` / ``topup_250`` minute packs.

So the cardinality is deal 1..N offer. Storing a single mutable ``order_ref`` /
``quoted_amount`` on the deal would mean a second offer silently overwrites the
first — and an already-issued payment link would start resolving to a different
amount than the prospect was quoted. Offers are therefore their own append-only
entity; the deal is referenced, never mutated by an offer.

IMMUTABILITY
------------
An issued offer's ``package_code``, ``quoted_amount`` and ``currency`` are
frozen at issuance. A price change in ``packages.py`` must NEVER retroactively
alter what a prospect was already quoted — that is the billing-truth invariant
(CLAUDE.md §5). Revising an offer creates a NEW order that records
``supersedes_order_ref``, leaving the original intact and auditable.

ORDER REFERENCE
---------------
``LG-<uuid4 hex, 32 chars>`` — full 128-bit, deliberately NOT truncated. The
deal id is itself already ``uuid4().hex[:12]`` (48 bits); truncating again to
build a reference would stack birthday risk on an already-shortened value for no
benefit, since this string is never typed by hand. It is non-secret, URL-safe,
UPI-``tn``-safe, and carries no customer data. Uniqueness is additionally
enforced against the store at issuance.

Pure storage + logic: no network, no LLM. Follows the sales_pipeline store
conventions (cross-process locked rewrite, append-only, never raises).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_OFFERS = os.path.join("data", "offers.jsonl")

#: An issued offer stops being payable after this long. Keeps a stale quote from
#: being paid months later at a price that no longer exists.
DEFAULT_TTL_DAYS = 30

#: Terminal/live states. `issued` is the only payable one.
STATUS_ISSUED = "issued"
STATUS_PAID = "paid"
STATUS_SUPERSEDED = "superseded"
STATUS_EXPIRED = "expired"
STATUS_CANCELLED = "cancelled"

_PAYABLE = {STATUS_ISSUED}
_STATUSES = {STATUS_ISSUED, STATUS_PAID, STATUS_SUPERSEDED, STATUS_EXPIRED, STATUS_CANCELLED}

#: Custom-amount offers (DFY setup fee, promo-discounted re-issues) ke liye
#: sanity floor — ₹99 se neeche ka "order" sale nahi hota.
CUSTOM_MIN_INR = 99
CUSTOM_MAX_INR = 1_000_000

__all__ = [
    "CUSTOM_MAX_INR",
    "CUSTOM_MIN_INR",
    "DEFAULT_TTL_DAYS",
    "STATUS_CANCELLED",
    "STATUS_EXPIRED",
    "STATUS_ISSUED",
    "STATUS_PAID",
    "STATUS_SUPERSEDED",
    "get_offer",
    "issue_custom_offer",
    "issue_offer",
    "list_offers",
    "mark_status",
    "resolve_payable",
]


def _store() -> str:
    return _OFFERS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        path = _store()
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return rows


def _write_all(rows: list[dict[str, Any]]) -> bool:
    """Atomic rewrite (tmp + os.replace), deliberately WITHOUT taking the lock.

    Callers that mutate hold ``file_lock`` around their whole read-modify-write,
    which is what makes concurrent issuance safe. Using ``locked_rewrite`` here
    would re-enter the same sidecar lock and deadlock until timeout.
    """
    path = _store()
    tmp = f"{path}.tmp.{os.getpid()}"
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        content = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        return True
    except Exception as e:
        logger.warning("[offers] write failed: %s", e)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False


def _new_order_ref(existing: set[str]) -> str:
    """Full-entropy reference, re-rolled on the (astronomically unlikely) clash."""
    for _ in range(8):
        ref = "LG-" + uuid.uuid4().hex
        if ref not in existing:
            return ref
    return "LG-" + uuid.uuid4().hex + uuid.uuid4().hex[:8]  # pragma: no cover


def _is_expired(row: dict[str, Any], now: datetime | None = None) -> bool:
    exp = str(row.get("expires_at") or "").strip()
    if not exp:
        return False
    try:
        when = datetime.fromisoformat(exp)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return (now or datetime.now(timezone.utc)) >= when
    except Exception:
        return False


def _price_for(package_code: str) -> tuple[int, str] | None:
    """LEGACY offer price resolver — NOT the commercial authority.

    It takes a bare package code, which cannot by itself express product family,
    billing cadence, customer visibility or sellability. That is a stated
    limitation, not a claim about what it solves: it stays narrow on purpose
    until ``CommercialPackageDescriptor`` replaces it, and must not be cited as
    evidence that package/policy validation is complete.

    What it does resolve correctly:

    * **cadence**, from canonical voice-plan identity. Annual reads the band's
      ``price_year``, monthly reads ``price_month``. Both previously went through
      ``voice_packages.voice_plan_price()``, whose own docstring says it returns
      the MONTHLY equivalent even for annual plans — so an annual order froze
      Rs 4,999 against a Rs 49,990 commitment (~90% undercharge) and annual was
      indistinguishable from monthly. Verified against the deployed image at
      9f2ab9f8 before the fix.
    * **customer visibility**, from the catalogue's own ``public`` flag. `growth`
      is legacy/internal (``public: False``) yet priced at Rs 2,999, so a bare
      code lookup could turn it into a customer-paid offer. Non-public packages
      are refused — driven by catalogue metadata, not a hardcoded code list.
    * **zero amounts** (pilot/trial) are refused: a Rs 0 UPI order is not a sale
      and belongs on its own activation path.

    Top-up packs remain deliberately unresolvable here. Enabling a previously
    impossible order type is a commercial behaviour change, not a pricing
    correction, and it needs an explicit one-time descriptor carrying its own
    entitlement semantics.
    """
    code = (package_code or "").strip().lower()
    if not code:
        return None

    # Marketing / combo monthly subscriptions.
    try:
        from app.marketing import packages as pkgs

        for p in list(getattr(pkgs, "PACKAGES", []) or []):
            if str(p.get("key") or "").strip().lower() == code:
                if not bool(p.get("public", True)):
                    logger.warning("[offers] refusing non-public package %r", code)
                    return None
                price = int(p.get("price_inr_month") or 0)
                return (price, "INR") if price > 0 else None
    except Exception as e:
        logger.warning("[offers] package lookup failed: %s", e)
        return None

    # Standalone voice plans — cadence decides which field is payable.
    try:
        from app.marketing import voice_packages as vpkgs

        if vpkgs.is_voice_plan(code):
            key, band = vpkgs.voice_plan_parts(code)
            info = vpkgs.BANDS.get(band) if band else None
            if not key or not info:
                return None
            if key == info.get("plan_annual"):
                price = int(info.get("price_year") or 0)
            elif key == info.get("plan_monthly"):
                price = int(info.get("price_month") or 0)
            else:
                # pilot / unrecognised cadence -> not a paid order
                return None
            return (price, "INR") if price > 0 else None
    except Exception as e:
        logger.warning("[offers] voice package lookup failed: %s", e)
    return None


def issue_offer(
    deal_id: str,
    package_code: str,
    *,
    prospect_id: str = "",
    client_id: str = "",
    ttl_days: int = DEFAULT_TTL_DAYS,
    supersedes: str = "",
) -> dict[str, Any] | None:
    """Issue (or idempotently reuse) an immutable offer for ``deal_id``.

    Reuses the existing live offer when one is already issued for the same deal
    AND package — so a retried reply-triage run never mints a second reference
    for the same quote, and the prospect who already has a link keeps paying
    against it. A DIFFERENT package creates a new order (upgrade/top-up), which
    is exactly the case that made a deal-level ``order_ref`` untenable.

    Returns ``None`` (never raises) when the deal id is missing or the package
    is unknown/unpriced — fail-closed, so no offer can carry a guessed amount.
    """
    did = (deal_id or "").strip()
    code = (package_code or "").strip().lower()
    if not did or not code:
        return None

    priced = _price_for(code)
    if not priced:
        logger.warning("[offers] refusing offer for unknown/unpriced package: %r", package_code)
        return None
    amount, currency = priced

    try:
        from app.utils.file_lock import file_lock

        with file_lock(_store()) as locked:
            if not locked:
                logger.warning("[offers] could not lock store; refusing to issue")
                return None
            return _issue_locked(
                did, code, amount, currency, prospect_id, client_id, ttl_days, supersedes
            )
    except Exception as e:
        logger.warning("[offers] issue_offer failed: %s", e)
        return None


def _issue_locked(
    did: str,
    code: str,
    amount: int,
    currency: str,
    prospect_id: str,
    client_id: str,
    ttl_days: int,
    supersedes: str,
    *,
    reuse_live: bool = True,
    label: str = "",
) -> dict[str, Any] | None:
    rows = _read()

    if reuse_live:
        for r in rows:
            if (
                r.get("deal_id") == did
                and str(r.get("package_code") or "") == code
                and r.get("status") == STATUS_ISSUED
                and not _is_expired(r)
            ):
                return dict(r)  # idempotent reuse — same quote, same reference

    version = 1 + sum(1 for r in rows if r.get("deal_id") == did)
    ref = _new_order_ref({str(r.get("order_ref") or "") for r in rows})

    now = datetime.now(timezone.utc)
    rec: dict[str, Any] = {
        "order_ref": ref,
        "deal_id": did,
        "package_code": code,
        "quoted_amount": amount,
        "currency": currency,
        "offer_version": version,
        "status": STATUS_ISSUED,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=max(1, int(ttl_days or DEFAULT_TTL_DAYS)))).isoformat(),
    }
    if label:
        rec["label"] = str(label)[:120]
    if prospect_id:
        rec["prospect_id"] = str(prospect_id)
    if client_id:
        rec["client_id"] = str(client_id)
    if supersedes:
        rec["supersedes_order_ref"] = str(supersedes)
        for r in rows:
            if r.get("order_ref") == supersedes and r.get("status") == STATUS_ISSUED:
                r["status"] = STATUS_SUPERSEDED
                r["updated_at"] = now.isoformat()

    rows.append(rec)
    if not _write_all(rows):
        return None
    return dict(rec)


def issue_custom_offer(
    deal_id: str,
    package_code: str,
    quoted_amount: int,
    *,
    label: str = "",
    prospect_id: str = "",
    client_id: str = "",
    ttl_days: int = DEFAULT_TTL_DAYS,
    supersedes: str = "",
    reuse_live: bool = False,
) -> dict[str, Any] | None:
    """EXPLICIT-amount offer — admin-gated custom quotes (DFY setup fee) aur
    promo-discounted supersede orders ke liye (revenue sprint 2026-08-23).

    ``issue_offer`` sirf catalogue price resolve karta hai; ye function caller
    ka frozen amount leta hai with hard bounds (₹99..₹10L) — isliye SIRF
    admin-authenticated / engine-internal callers use kar sakte hain, kabhi
    public input par nahi. Fail-closed: bad amount/deal → None, kabhi raise
    nahi. ``reuse_live=False`` (default) guaranteed-new order banata hai taaki
    promo-derived offers apne parent se distinct rahen.
    """
    did = (deal_id or "").strip()
    code = (package_code or "").strip().lower()
    if not did or not code:
        return None
    try:
        amount = int(quoted_amount)
    except Exception:
        return None
    if amount < CUSTOM_MIN_INR or amount > CUSTOM_MAX_INR:
        logger.warning(
            "[offers] refusing custom offer out of bounds: %s (%s)", amount, code
        )
        return None

    try:
        from app.utils.file_lock import file_lock

        with file_lock(_store()) as locked:
            if not locked:
                logger.warning("[offers] could not lock store; refusing to issue")
                return None
            return _issue_locked(
                did,
                code,
                amount,
                "INR",
                prospect_id,
                client_id,
                ttl_days,
                supersedes,
                reuse_live=reuse_live,
                label=label,
            )
    except Exception as e:
        logger.warning("[offers] issue_custom_offer failed: %s", e)
        return None


def get_offer(order_ref: str) -> dict[str, Any] | None:
    """Exact lookup by reference. None when unknown — callers must fail closed."""
    ref = (order_ref or "").strip()
    if not ref:
        return None
    for r in _read():
        if str(r.get("order_ref") or "") == ref:
            out = dict(r)
            if out.get("status") == STATUS_ISSUED and _is_expired(out):
                out["status"] = STATUS_EXPIRED  # reported as expired without a write
            return out
    return None


def resolve_payable(order_ref: str) -> tuple[dict[str, Any] | None, str]:
    """``(offer, reason)``. Offer is non-None only when it is payable RIGHT NOW.

    reason is one of: ``ok``, ``unknown``, ``expired``, ``superseded``,
    ``already_paid``, ``cancelled``. Server-side gate for payment submission —
    a client-supplied reference is never trusted beyond this lookup.
    """
    off = get_offer(order_ref)
    if not off:
        return None, "unknown"
    status = str(off.get("status") or "")
    if status in _PAYABLE:
        return off, "ok"
    return None, {
        STATUS_EXPIRED: "expired",
        STATUS_SUPERSEDED: "superseded",
        STATUS_PAID: "already_paid",
        STATUS_CANCELLED: "cancelled",
    }.get(status, "not_payable")


def mark_status(order_ref: str, status: str, *, by: str = "system") -> bool:
    """Move an offer to a new status. Idempotent; never raises."""
    ref = (order_ref or "").strip()
    st = (status or "").strip().lower()
    if not ref or st not in _STATUSES:
        return False
    try:
        from app.utils.file_lock import file_lock

        with file_lock(_store()) as locked:
            if not locked:
                return False
            rows = _read()
            hit = False
            for r in rows:
                if str(r.get("order_ref") or "") == ref:
                    if r.get("status") == st:
                        return True  # idempotent
                    r["status"] = st
                    r["updated_at"] = _now()
                    r["status_by"] = by
                    hit = True
            return bool(hit and _write_all(rows))
    except Exception as e:
        logger.warning("[offers] mark_status failed: %s", e)
        return False


def list_offers(deal_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
    """Offers, newest first. Filtered to one deal when ``deal_id`` is given."""
    did = (deal_id or "").strip()
    rows = [r for r in _read() if not did or r.get("deal_id") == did]
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return rows[: max(1, min(int(limit or 100), 1000))]
