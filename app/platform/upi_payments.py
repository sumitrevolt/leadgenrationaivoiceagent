"""Self-serve UPI payment submissions — kill manual WhatsApp-screenshot friction.

Customer pays via UPI, then submits "maine pay kiya" (ref + plan) from the site.
Record lands in a pending queue (``data/upi_payments.json``). Admin approves/rejects,
OR — when ``UPI_AUTO_ACTIVATE=1`` — the plan auto-activates instantly on submit.

Patterned on ``app.platform.upi_config`` (json data-file store, never raises).
ADDITIVE + defensive: every function wraps work in try/except and returns a safe
default; nothing here ever lets an exception escape into a request path.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def _STORE() -> str:
    """UPI payment records — resolved per call, never frozen at import."""
    from app.platform import runtime_data_authority as _auth

    return str(
        _auth.resolve_store_path(
            store_id="billing.upi_payments",
            legacy_path=Path("data") / "upi_payments.json",
            target_segments=("billing", "upi_payments.json"),
        )
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def auto_activate_clients_allowed(client_id: str) -> bool:
    """Fail-closed tenant allowlist for ``UPI_AUTO_ACTIVATE``.

    Master flag ``UPI_AUTO_ACTIVATE=1`` alone is never enough: the client must
    also appear in ``UPI_AUTO_ACTIVATE_CLIENTS`` (comma list). Empty allowlist
    refuses every auto-activation. ``*`` is an explicit graduation to all
    tenants (same convention as ``VIDEO_CUSTOMER_REVIEW_CLIENTS``).
    """
    if os.environ.get("UPI_AUTO_ACTIVATE") != "1":
        return False
    raw = (os.environ.get("UPI_AUTO_ACTIVATE_CLIENTS") or "").strip()
    if not raw:
        return False
    allowed = {part.strip().lower() for part in raw.split(",") if part.strip()}
    cid = str(client_id or "").strip().lower()
    if not cid:
        return False
    return "*" in allowed or cid in allowed


def _read_store() -> list[dict]:
    """Read the payment records list. Never raises — bad/missing file → []."""
    try:
        # Resolver at each I/O site — binding to a local unbinds the allowlist.
        if os.path.isfile(_STORE()):
            with open(_STORE(), encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.debug("upi_payments read failed: %s", e)
    return []


def _write_store(rows: list[dict]) -> bool:
    """Persist the records list. Never raises — returns False on failure."""
    try:
        os.makedirs(os.path.dirname(_STORE()) or ".", exist_ok=True)
        with open(_STORE(), "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.warning("upi_payments write failed: %s", e)
        return False


def _make_id(existing: list[dict], upi_ref: str) -> str:
    """Deterministic-ish id: counter + short hash of upi_ref (no uuid/random)."""
    try:
        h = hashlib.sha1((upi_ref or "").encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
    except Exception:
        h = "00000000"
    return f"upi_{len(existing) + 1}_{h}"


def _notify_admin(record: dict) -> None:
    """Best-effort ntfy push to admin. Never blocks / never raises."""
    try:
        from app.platform import ops_alerts

        msg = (
            f"Plan: {record.get('plan')} · Ref: {record.get('upi_ref')} · "
            f"Client: {record.get('client_id') or '-'} · "
            f"Naam: {record.get('payer_name') or '-'} · Amt: {record.get('amount')}"
        )
        ops_alerts._ntfy("New UPI payment", msg)
    except Exception as e:
        logger.debug("upi_payments admin notify skipped: %s", e)


def _valid_plan_keys() -> set[str]:
    """Canonical set of activatable plan keys (lowercased). Never raises.

    Built from the pure-data pricing source-of-truth modules (import-safe, no DB):
      - marketing packages incl. FREE trial  → {trial, starter, growth, advanced}
      - voice product plan ids               → VOICE_PLAN_IDS (7)
      - combo product plan ids               → COMBO_PLAN_IDS (7)
    NB: ``subscription.PRICING_PLANS`` is NOT used — those marketing/voice/combo keys
    are injected at RUNTIME by billing_manager sync (not at import), so it would be
    empty/partial here. Each source is unioned best-effort so a missing/broken module
    never breaks validation (the others still gate). Empty set only if ALL fail.
    """
    keys: set[str] = set()
    try:
        from app.marketing.packages import get_packages

        for p in get_packages(include_trial=True) or []:
            k = str((p or {}).get("key") or "").strip().lower()
            if k:
                keys.add(k)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("upi_payments valid-keys packages skipped: %s", e)
    try:
        from app.marketing.voice_packages import VOICE_PLAN_IDS

        keys.update(str(k).strip().lower() for k in (VOICE_PLAN_IDS or []) if k)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("upi_payments valid-keys voice skipped: %s", e)
    try:
        from app.marketing.combo_packages import COMBO_PLAN_IDS

        keys.update(str(k).strip().lower() for k in (COMBO_PLAN_IDS or []) if k)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("upi_payments valid-keys combo skipped: %s", e)
    return keys


def _min_plan_price(plan_key: str) -> float | None:
    """Cheapest legitimate amount (INR) for `plan_key` — the monthly price, which
    is always <= the annual price, so `amount >= this` accepts either billing
    period without needing to know which one was submitted. Returns None if the
    plan isn't found in any pricing source (caller must not block on None — same
    fail-open-on-missing-data posture as `_valid_plan_keys()`)."""
    try:
        from app.marketing.packages import get_packages

        for p in get_packages(include_trial=True) or []:
            if str((p or {}).get("key") or "").strip().lower() == plan_key:
                return float(p.get("price_inr_month") or 0)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("upi_payments min-price packages skipped: %s", e)
    try:
        # Band-aware helper — get_voice_packages() only returns ONE band's
        # payload, so scraping it missed voice_b_*/voice_c_* entirely and the
        # price floor silently never applied to the most expensive voice plans.
        from app.marketing.voice_packages import voice_plan_price

        price = voice_plan_price(plan_key)
        if price:
            return float(price)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("upi_payments min-price voice skipped: %s", e)
    try:
        # get_combo_packages() payload keys plans under "tiers" (not "plans"),
        # so the old scrape resolved None for every combo plan — use the
        # dedicated price helper instead.
        from app.marketing.combo_packages import combo_plan_price

        price = combo_plan_price(plan_key)
        if price:
            return float(price)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("upi_payments min-price combo skipped: %s", e)
    return None


def _try_activate(client_id: str, plan: str, amount: float = 0, enforce_floor: bool = True) -> bool:
    """Best-effort plan activation. Never raises — returns activation success bool.

    Validates the plan against the canonical activatable set BEFORE provisioning so a
    typo/retired/unknown plan can never silently activate (record stays pending). Also
    rejects if `amount` is below the plan's real listed price (production audit
    2026-07-01: UPI_AUTO_ACTIVATE previously only checked the plan key, not the paid
    amount — a fabricated amount:0 self-serve submission could auto-activate the
    highest paid tier for free). On a successful activation also drops the renewal
    usage watermark (parity with the Stripe webhook path) so a renew/upgrade zeroes
    the minute counter for the period.

    ``enforce_floor=False`` is for the ADMIN approve path only (missing-work audit
    2026-07-04): every frontend submit records ``amount: 0`` (no amount field), so
    enforcing the floor on ``decide()`` made the admin "Approve" button silently
    fail to activate ANY real submission. A human approving has already verified
    the payment in the bank/UPI app — the floor exists to stop UNattended
    auto-activation, not attended approval.
    """
    cid = (client_id or "").strip()
    if not cid:
        return False
    plan_k = (plan or "").strip().lower()
    if not plan_k:
        return False
    valid = _valid_plan_keys()
    # Only reject when we actually have a known set to check against; if every pricing
    # source failed to import (valid == empty) we don't block legitimate activation.
    if valid and plan_k not in valid:
        logger.warning(
            "upi_payments activation REJECTED — unknown plan %r (not in %d known plans)",
            plan,
            len(valid),
        )
        return False
    min_price = _min_plan_price(plan_k) if enforce_floor else None
    # Only enforce when we actually resolved a real price — same fail-open-on-missing-
    # data posture as the plan-key check above (never block on our own lookup failure).
    if min_price and float(amount or 0) < min_price:
        logger.warning(
            "upi_payments activation REJECTED — amount %r below plan %r price floor %r",
            amount,
            plan,
            min_price,
        )
        return False
    try:
        from app.billing import usage

        # ensure_subscription: real UPI payment — create/activate the Subscription
        # row too (portal /billing/subscription 404s without one; audit 2026-07-04).
        if not bool(usage.activate_plan(cid, plan, ensure_subscription=True)):
            return False
        # Parity with Stripe path: reset the metered-usage watermark on activation so a
        # renewal/upgrade zeroes the minute counter. Best-effort — never raises.
        try:
            usage.reset_usage_period(cid)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("upi_payments reset_usage_period skipped: %s", e)
        # Funnel event (audit 2026-07-04) — silent no-op without POSTHOG_API_KEY.
        # niche + business_type properties paid side pe bhi + distinct_id = phone
        # (lead_captured bhi phone-keyed hai — inquiry → paid funnel same person pe
        # match karta hai; posthog_funnel module). Client ka phone record se aata
        # hai; na ho to cid fallback.
        try:
            from app.analytics import posthog_client as _ph
            from app.integrations.posthog_funnel import client_business_type

            props = {"plan": plan_k, "amount": float(amount or 0), "gateway": "upi"}
            props.update({k: v for k, v in client_business_type(cid).items() if v})
            _ph.capture(
                str(props.pop("phone", "") or cid),
                "payment_activated",
                props,
            )
        except Exception:
            pass
        return True
    except Exception as e:
        logger.debug("upi_payments activate skipped: %s", e)
        return False


def _fire_gst_invoice(client_id: str, plan: str, amount: float = 0) -> None:
    """Best-effort GST invoice on a successful UPI activation — parity with the
    Stripe path (``billing._provision_usage`` → ``gst_invoice.on_payment_success``).
    Without this a UPI-paying customer got NO invoice record (audit 2026-07-05:
    real paying client had a live plan but zero downloadable bill). Record hamesha
    banta; email sirf ``AUTO_INVOICE=1`` pe (that gate lives inside on_payment_success).

    ``payment_ref`` = client + plan + month so monthly renewals each get one invoice
    and a double-approve/re-activate of the SAME month dedupes (``_already_invoiced``).

    on_payment_success is ``async``; this helper runs from SYNC callers (submit auto-
    activate + admin decide), so we prefer scheduling on a running loop when one
    exists and otherwise run it to completion. NEVER raises — a billing hiccup must
    never break the activation/onboarding that already succeeded.
    """
    try:
        cid = (client_id or "").strip()
        plan_k = (plan or "").strip()
        if not cid or not plan_k:
            return
        import asyncio as _aio

        from app.billing import gst_invoice

        _ref = f"upi:{cid}:{plan_k}:{datetime.now(timezone.utc):%Y-%m}"
        _amt = float(amount or 0) or None
        coro = gst_invoice.on_payment_success(
            cid, plan_k, payment_ref=_ref, gateway="upi", amount_inr=_amt
        )
        try:
            _loop = _aio.get_running_loop()
        except RuntimeError:
            _loop = None
        if _loop is not None:
            # Async context (called from within a request coroutine) — schedule it.
            _loop.create_task(coro)
        else:
            # Pure-sync caller (Celery worker / admin CLI) — run to completion.
            _aio.run(coro)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("upi_payments gst invoice hook skipped: %s", e)


def _credit_referral(record: dict) -> None:
    """Best-effort referral 'lead' → 'paid' flip on a successful activation.

    Revenue sprint (2026-08-23): affiliate referrals signup par record hote the
    par payment hone par kabhi 'paid' nahi hote the — commission ledger dead
    tha. Match payer_contact (ya client ka email) se; idempotent, never raises.
    """
    try:
        from app.marketing import affiliate

        contact = str(record.get("payer_contact") or "")
        email = ""
        cid = str(record.get("client_id") or "").strip()
        if cid and "@" not in contact:
            try:
                from app.marketing.clients_store import resolve_client

                rec = resolve_client(cid) or {}
                email = str(rec.get("email") or "")
                if not contact:
                    contact = str(rec.get("phone") or "")
            except Exception:
                pass
        affiliate.mark_referral_paid_by_contact(
            contact=contact, email=email, phone=contact,
            amount=float(record.get("amount", 0) or 0),
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("upi_payments referral credit skipped: %s", e)


def _trigger_onboarding(client_id: str = "") -> None:
    """Front-run day-1 onboard for a just-activated client (KB seed + first pack).

    Prefer per-client ``onboard_client`` (same as signup) so we do **not** depend on
    the ``AUTO_ONBOARD``-gated hourly sweep. Falls back to the sweep task when
    ``client_id`` is empty. Runs on the WORKER, never the web process. Never raises.
    """
    cid = (client_id or "").strip()
    try:
        if cid:
            from app.tasks.staff_jobs import onboard_client

            # send_welcome=False — payment path already has its own notifies; avoid
            # double WhatsApp on activate (ban-safety + signup parity).
            onboard_client.delay(cid, False)
            return
        from app.worker import celery_app

        # ignore_result=True → fire-and-forget; skips the Redis result-backend
        # pre-subscription that can block (unbounded retry) if the backend is slow/down.
        # Broker send stays bounded by broker_connection_timeout (10s).
        celery_app.send_task(
            "app.tasks.staff_jobs.run_staff_job", args=("onboard",), ignore_result=True
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("upi_payments onboarding enqueue skipped: %s", e)


def _mark_deal_won(phone: str) -> None:
    """A real payment just activated — if a sales_pipeline deal exists for this
    phone (e.g. the AI voice agent closed it to "negotiating" on a call), mark
    it won so the Sales dashboard reflects what actually happened instead of
    showing it stuck forever. Best-effort/read-after-write on the jsonl store;
    a missing/ambiguous match is a silent no-op — never affects the payment or
    onboarding that already succeeded. Safe from double-onboard: voice-call
    deals never carry a client_id, so run_pipeline's own "won -> onboard"
    auto-action (which requires client_id) cannot fire a second time from this.
    """
    digits = "".join(c for c in str(phone or "") if c.isdigit())[-10:]
    if not digits:
        return
    try:
        from app.marketing import sales_pipeline

        for d in sales_pipeline.list_deals(limit=500) or []:
            if d.get("phone") == digits and d.get("stage") not in ("won", "lost"):
                sales_pipeline.set_stage(d["id"], "won")
                break
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("upi_payments mark_deal_won skipped: %s", e)


def _close_order(record: dict, by: str = "system") -> None:
    """Money for this record is confirmed → flip its bound offer to ``paid``.

    ``submit_payment`` already refuses a reference that is not payable right now,
    and its own comment (see the order gate) relies on the offer leaving `issued`
    "once the owner approves". Nothing performed that transition, so an order
    stayed payable forever: a second submission under the SAME order_ref with a
    different upi_ref slips past the (upi_ref, client, plan) duplicate guard,
    lands as a fresh pending row, and on approve runs `_try_activate` again —
    re-zeroing a metered client's usage period and firing a second GST invoice.

    Called on approve and on auto-activation. NOT called on reject: a rejected
    claim means the money never arrived, so the order must stay payable for the
    prospect who really does pay. `offers.mark_status` is idempotent, so a
    re-approve of an already-closed order is a no-op. Best-effort — a failure
    here never affects a payment that has already been persisted.
    """
    ref = str(record.get("order_ref") or "").strip()
    if not ref:
        return
    try:
        from app.marketing import offers

        if not offers.mark_status(ref, offers.STATUS_PAID, by=(by or "system")[:80]):
            logger.warning(
                "upi_payments could not close order %s for payment %s — "
                "it stays payable; reconcile manually",
                ref,
                record.get("id"),
            )
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("upi_payments close_order failed for %s: %s", ref, e)


def submit_payment(
    client_id: str,
    plan: str,
    upi_ref: str,
    amount: float = 0,
    payer_name: str = "",
    payer_contact: str = "",
    order_ref: str = "",
) -> dict:
    """Customer self-serve "maine pay kiya" submission.

    Validates plan + upi_ref non-empty, appends a pending record, notifies admin,
    and (when ``UPI_AUTO_ACTIVATE=1`` + client_id) tries instant activation.
    Never raises — returns ``{"ok": False, "error": ...}`` on validation failure.

    ``order_ref`` (#240, optional) binds the payment to an immutable offer so an
    owner reconciling a bank credit sees the exact deal instead of matching on a
    business name. It is NOT trusted as submitted: the reference is re-resolved
    server-side against the offer store and must be payable right now. An
    unknown, expired, superseded, already-paid or cancelled reference is
    rejected fail-closed rather than being recorded as an unverified hint.
    Omitting it preserves the pre-#240 behaviour exactly.
    """
    try:
        plan_s = (plan or "").strip()
        ref_s = (upi_ref or "").strip()
        if not plan_s:
            return {"ok": False, "error": "Plan zaroori hai"}
        if not ref_s:
            return {"ok": False, "error": "UPI reference / transaction id zaroori hai"}

        order_ref_s = (order_ref or "").strip()
        cid = (client_id or "").strip()
        rows = _read_store()

        # Loop 5 (2026-07-10) idempotency: customer double-click / retry / offline
        # resubmit shouldn't create duplicate rows or (worse, with UPI_AUTO_ACTIVATE=1)
        # double-activate the plan. UPI refs are supposed to be unique per transaction;
        # if we see the same ref for the same client+plan already recorded, return
        # THAT record instead of appending a fresh one. `decide()` is already
        # idempotent on the `activated` flag, so this closes the submit side.
        try:
            existing = next(
                (
                    r
                    for r in rows
                    if (r.get("upi_ref") or "").strip() == ref_s
                    and (not cid or (r.get("client_id") or "").strip() == cid)
                    and (r.get("plan") or "").strip() == plan_s
                ),
                None,
            )
        except Exception:
            existing = None
        if existing is not None:
            logger.info(
                "upi_payments duplicate submit ignored — ref=%s plan=%s cid=%s existing_id=%s",
                ref_s,
                plan_s,
                cid or "-",
                existing.get("id"),
            )
            # Signal to caller that this is a replay so FE can show a friendlier
            # "aapki payment already dekh liye" state instead of duplicate success.
            return {"ok": True, "duplicate": True, **existing}

        # Order gate runs AFTER the duplicate check, deliberately (post-merge review
        # of #241). Gating first meant a legitimate retry of an ALREADY-RECORDED
        # payment — double-click, offline resubmit, network retry — started failing
        # the moment its offer left `issued`: once the owner approves and the offer
        # flips to `paid`, or once it expires, resolve_payable refuses and the payer
        # who really did pay saw "Order reference not payable (already_paid)" instead
        # of the reassuring duplicate acknowledgement. Only genuinely NEW submissions
        # need a payable order.
        order: dict | None = None
        if order_ref_s:
            try:
                from app.marketing import offers

                order, reason = offers.resolve_payable(order_ref_s)
            except Exception as exc:  # store unavailable => cannot verify => refuse
                logger.warning("upi_payments offer lookup failed: %s", exc)
                order, reason = None, "unavailable"
            if not order:
                return {"ok": False, "error": f"Order reference not payable ({reason})"}
            # The offer owns the commercial truth; a client-supplied plan that
            # disagrees with the issued order is a mismatch, not an override.
            if str(order.get("package_code") or "").lower() != plan_s.lower():
                return {"ok": False, "error": "Order reference does not match the submitted plan"}

        record = {
            "id": _make_id(rows, ref_s),
            "client_id": cid,
            "plan": plan_s,
            "upi_ref": ref_s,
            "amount": amount,
            "payer_name": (payer_name or "").strip(),
            "payer_contact": (payer_contact or "").strip(),
            "status": "pending",
            "auto_activated": False,
            "needs_client_bind": not bool(cid),
            "created_at": _now_iso(),
            "decided_at": None,
            "decided_by": None,
        }
        if order:
            # Server-resolved (#240) — reconciliation anchor for /upi/pending.
            # `expected_amount` comes from the ISSUED offer, never a live
            # catalogue lookup, so a later price change cannot retro-quote.
            record["order_ref"] = str(order.get("order_ref") or "")
            record["deal_id"] = str(order.get("deal_id") or "")
            record["package_code"] = str(order.get("package_code") or "")
            record["expected_amount"] = order.get("quoted_amount")
            record["currency"] = str(order.get("currency") or "INR")
            try:
                record["amount_mismatch"] = bool(
                    float(amount or 0) > 0
                    and float(amount) != float(order.get("quoted_amount") or 0)
                )
            except Exception:
                record["amount_mismatch"] = False
        rows.append(record)
        _write_store(rows)

        # Best-effort admin notify (after persist so the record is durable first).
        _notify_admin(record)

        # Optional instant activation (flag + tenant allowlist, default OFF).
        if auto_activate_clients_allowed(cid):
            if _try_activate(cid, plan_s, amount):
                record["status"] = "auto_activated"
                record["auto_activated"] = True
                record["decided_at"] = _now_iso()
                record["decided_by"] = "auto"
                # Persist the updated status (record is the same object in rows).
                _write_store(rows)
                # Order is settled — stop it being payable a second time (#240).
                _close_order(record, by="auto")
                # Just activated → per-client day-1 onboard (not AUTO_ONBOARD sweep).
                _trigger_onboarding(cid)
                _mark_deal_won(record.get("payer_contact", ""))
                # GST invoice parity with Stripe path (best-effort, never-raise).
                _fire_gst_invoice(cid, plan_s, amount)
                # No real bank/UPI verification backs this instant activation —
                # nudge the founder to spot-check (council decision 2026-07-03:
                # ship UPI_AUTO_ACTIVATE's speed, pair it with a reconciliation
                # signal instead of a blocking review).
                _credit_referral(record)
                try:
                    from app.platform import ops_alerts

                    ops_alerts.maybe_alert_upi_auto_activated(
                        record.get("id", ""), cid, plan_s, float(amount or 0)
                    )
                except Exception as e:  # pragma: no cover - defensive
                    logger.debug("upi_payments auto-activate alert skipped: %s", e)
        elif os.environ.get("UPI_AUTO_ACTIVATE") == "1" and cid:
            # Master flag on but tenant not allowlisted — stay pending (fail-closed).
            logger.info(
                "upi_payments auto-activate refused (client not on UPI_AUTO_ACTIVATE_CLIENTS)"
            )

        return {"ok": True, **record}
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("submit_payment failed: %s", e)
        return {"ok": False, "error": "Submit fail — thodi der baad try karo"}


def list_payments(status: str | None = None) -> list[dict]:
    """All payment records, optionally filtered by status. Never raises."""
    try:
        rows = _read_store()
        if status:
            return [r for r in rows if r.get("status") == status]
        return rows
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("list_payments failed: %s", e)
        return []


def list_actionable() -> list[dict]:
    """Operator queue: pending claims plus approved payments not yet activated.

    An owner may confirm bank credit before a guest submission is bound to a
    marketing client. That row is ``approved`` but revenue is not delivered yet,
    so it remains visible both before and after Bind until re-Approve activates it.
    """
    try:
        return [
            row
            for row in _read_store()
            if row.get("status") == "pending"
            or (
                row.get("status") == "approved"
                and not row.get("activated")
                and not row.get("auto_activated")
            )
        ]
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("list_actionable failed: %s", e)
        return []


def decide(payment_id: str, approve: bool, decided_by: str = "admin") -> dict:
    """Admin approve/reject a pending submission.

    On approve (and not already auto-activated) + client_id → activate the plan.
    Returns the updated record, or ``{"ok": False, "error": "not_found"}``.
    Never raises.
    """
    try:
        pid = (payment_id or "").strip()
        rows = _read_store()
        record = None
        for r in rows:
            if r.get("id") == pid:
                record = r
                break
        if record is None:
            return {"ok": False, "error": "not_found"}

        record["status"] = "approved" if approve else "rejected"
        record["decided_at"] = _now_iso()
        record["decided_by"] = (decided_by or "admin")[:80]

        # The owner confirming the bank credit IS the payment event (#240). Close
        # the order here, BEFORE the activation branches below: activation can
        # legitimately fail or be deferred (unbound client), but the money has
        # still arrived, so the order must stop being payable either way.
        if approve:
            _close_order(record, by=record["decided_by"])

        # Fail-closed: empty client_id cannot activate — bind client first.
        if approve and not (record.get("client_id") or "").strip():
            record["needs_client_bind"] = True
            record["activation_blocked"] = "empty_client_id"
            _write_store(rows)
            return {
                "ok": True,
                **record,
                "warning": "approved_but_unbound — client_id bind karo phir re-approve",
            }

        # Idempotency: only activate if NOT already SUCCESSFULLY activated. _try_activate
        # → reset_usage_period() re-zeros a metered client's usage; a second approve of an
        # already-activated submission would hand out free minutes. We guard on a success
        # flag (not on status) so a FAILED activation stays retryable: first approve sets
        # status=approved but leaves `activated` falsy → admin can re-approve to recover.
        if (
            approve
            and not record.get("activated")
            and not record.get("auto_activated")
            and record.get("client_id")
        ):
            if _try_activate(
                record.get("client_id", ""),
                record.get("plan", ""),
                record.get("amount", 0),
                # Human admin approving = payment already verified in the UPI app;
                # frontends record amount:0, so enforcing the floor here made every
                # real approval silently fail to activate (audit 2026-07-04).
                enforce_floor=False,
            ):
                record["activated"] = True
                record.pop("activation_blocked", None)
                # Activation succeeded → per-client day-1 onboard (signup parity).
                _trigger_onboarding(str(record.get("client_id") or ""))
                _mark_deal_won(record.get("payer_contact", ""))
                # GST invoice parity with Stripe path (best-effort, never-raise).
                _fire_gst_invoice(
                    record.get("client_id", ""),
                    record.get("plan", ""),
                    record.get("amount", 0),
                )
                # Referral commission loop — lead → paid (revenue sprint).
                _credit_referral(record)
            else:
                # Approved but activation did NOT succeed (unknown plan / activation
                # error) → revenue-critical SILENT failure: alert ops (best-effort).
                record["activation_blocked"] = "activation_failed"
                try:
                    from app.platform import ops_alerts

                    ops_alerts.maybe_alert_payment_failed(
                        f"UPI approve activation FAILED — client={record.get('client_id')} "
                        f"plan={record.get('plan')} pid={pid}"
                    )
                except Exception:
                    pass

        _write_store(rows)
        return record
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("decide failed: %s", e)
        return {"ok": False, "error": "decide_failed"}


def bind_client(payment_id: str, client_id: str, decided_by: str = "admin") -> dict:
    """Bind a marketing client to an UPI submission that has no client_id.

    Guest "maine pay kiya" submissions land with ``client_id=""`` +
    ``needs_client_bind=True``; approving one without a client fails closed
    (``approved_but_unbound``, #304). This is the operator queue action that
    resolves it: bind the verified client, then Approve activates.

    Fail-closed + cross-tenant safe:
      - the payment record must exist;
      - ``client_id`` is required AND must resolve to a real marketing client
        (``resolve_client`` — never creates, so a typo'd/unknown id is refused);
      - an already-activated submission is refused (binding cannot resurrect a
        settled payment);
      - an already-bound submission may only be re-bound to the SAME client
        (idempotent no-op) — re-pointing at a different client is refused
        (cross-tenant guard);
      - bind NEVER activates: the owner's Approve remains the single activation
        gate, so after binding the admin re-approves and ``decide`` activates
        (matches the approved_but_unbound warning's own "bind karo phir
        re-approve").

    Never raises — returns the updated record or ``{"ok": False, "error": ...}``.
    """
    try:
        pid = (payment_id or "").strip()
        cid = (client_id or "").strip()
        rows = _read_store()
        record = None
        for r in rows:
            if r.get("id") == pid:
                record = r
                break
        if record is None:
            return {"ok": False, "error": "not_found"}
        if not cid:
            return {"ok": False, "error": "client_id_required"}

        current = (record.get("client_id") or "").strip()
        if record.get("activated") or record.get("auto_activated"):
            if current == cid:
                return {"ok": True, **record}
            return {"ok": False, "error": "already_activated"}

        # Cross-tenant guard: never re-point an already-bound submission.
        if current and current != cid:
            return {"ok": False, "error": "already_bound_to_other"}

        # Resolve to the canonical marketing id (id OR billing alias). Fail
        # closed on unknown — activation itself would fail anyway (activate_plan
        # needs the marketing record), so refusing here gives the operator a
        # clear error instead of a silent later failure.
        try:
            from app.marketing.clients_store import resolve_client

            rec = resolve_client(cid)
        except Exception:  # pragma: no cover - defensive
            rec = None
        if rec is None:
            return {"ok": False, "error": "unknown_client"}
        canonical = str(rec.get("id") or "").strip() or cid

        if current == canonical:
            # Idempotent re-bind of the same client — clear the flag, done.
            record["needs_client_bind"] = False
            record.pop("activation_blocked", None)
            _write_store(rows)
            return {"ok": True, **record}

        record["client_id"] = canonical
        record["needs_client_bind"] = False
        record.pop("activation_blocked", None)
        record["bound_at"] = _now_iso()
        record["bound_by"] = (decided_by or "admin")[:80]
        _write_store(rows)
        return {"ok": True, **record}
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("bind_client failed: %s", e)
        return {"ok": False, "error": "bind_failed"}
