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

logger = logging.getLogger(__name__)

_STORE = os.path.join("data", "upi_payments.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_store() -> list[dict]:
    """Read the payment records list. Never raises — bad/missing file → []."""
    try:
        if os.path.isfile(_STORE):
            with open(_STORE, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.debug("upi_payments read failed: %s", e)
    return []


def _write_store(rows: list[dict]) -> bool:
    """Persist the records list. Never raises — returns False on failure."""
    try:
        os.makedirs(os.path.dirname(_STORE) or ".", exist_ok=True)
        with open(_STORE, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.warning("upi_payments write failed: %s", e)
        return False


def _make_id(existing: list[dict], upi_ref: str) -> str:
    """Deterministic-ish id: counter + short hash of upi_ref (no uuid/random)."""
    try:
        h = hashlib.sha1((upi_ref or "").encode("utf-8")).hexdigest()[:8]
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
        from app.marketing.voice_packages import get_voice_packages

        for band_plans in (get_voice_packages() or {}).values():
            if not isinstance(band_plans, list):
                continue
            for p in band_plans:
                if str((p or {}).get("key") or "").strip().lower() == plan_key:
                    return float(p.get("price_inr_month") or 0)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("upi_payments min-price voice skipped: %s", e)
    try:
        from app.marketing.combo_packages import get_combo_packages

        for p in (get_combo_packages() or {}).get("plans", []) or []:
            if str((p or {}).get("key") or "").strip().lower() == plan_key:
                return float(p.get("price_inr_month") or 0)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("upi_payments min-price combo skipped: %s", e)
    return None


def _try_activate(client_id: str, plan: str, amount: float = 0) -> bool:
    """Best-effort plan activation. Never raises — returns activation success bool.

    Validates the plan against the canonical activatable set BEFORE provisioning so a
    typo/retired/unknown plan can never silently activate (record stays pending). Also
    rejects if `amount` is below the plan's real listed price (production audit
    2026-07-01: UPI_AUTO_ACTIVATE previously only checked the plan key, not the paid
    amount — a fabricated amount:0 self-serve submission could auto-activate the
    highest paid tier for free). On a successful activation also drops the renewal
    usage watermark (parity with the Stripe webhook path) so a renew/upgrade zeroes
    the minute counter for the period.
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
    min_price = _min_plan_price(plan_k)
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

        if not bool(usage.activate_plan(cid, plan)):
            return False
        # Parity with Stripe path: reset the metered-usage watermark on activation so a
        # renewal/upgrade zeroes the minute counter. Best-effort — never raises.
        try:
            usage.reset_usage_period(cid)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("upi_payments reset_usage_period skipped: %s", e)
        return True
    except Exception as e:
        logger.debug("upi_payments activate skipped: %s", e)
        return False


def _trigger_onboarding() -> None:
    """Front-run the hourly onboarding sweep so a just-activated client gets their
    KB seed + first content pack in seconds, not up to an hour. Best-effort: enqueues
    the existing Celery staff job (runs on the WORKER, never in the web process) and
    falls back to the hourly sweep if the broker is unavailable. Never raises."""
    try:
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


def submit_payment(
    client_id: str,
    plan: str,
    upi_ref: str,
    amount: float = 0,
    payer_name: str = "",
    payer_contact: str = "",
) -> dict:
    """Customer self-serve "maine pay kiya" submission.

    Validates plan + upi_ref non-empty, appends a pending record, notifies admin,
    and (when ``UPI_AUTO_ACTIVATE=1`` + client_id) tries instant activation.
    Never raises — returns ``{"ok": False, "error": ...}`` on validation failure.
    """
    try:
        plan_s = (plan or "").strip()
        ref_s = (upi_ref or "").strip()
        if not plan_s:
            return {"ok": False, "error": "Plan zaroori hai"}
        if not ref_s:
            return {"ok": False, "error": "UPI reference / transaction id zaroori hai"}

        cid = (client_id or "").strip()
        rows = _read_store()
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
            "created_at": _now_iso(),
            "decided_at": None,
            "decided_by": None,
        }
        rows.append(record)
        _write_store(rows)

        # Best-effort admin notify (after persist so the record is durable first).
        _notify_admin(record)

        # Optional instant activation (flag-gated, default OFF).
        if os.environ.get("UPI_AUTO_ACTIVATE") == "1" and cid:
            if _try_activate(cid, plan_s, amount):
                record["status"] = "auto_activated"
                record["auto_activated"] = True
                record["decided_at"] = _now_iso()
                record["decided_by"] = "auto"
                # Persist the updated status (record is the same object in rows).
                _write_store(rows)
                # Just activated → front-run onboarding so output lands in seconds.
                _trigger_onboarding()
                _mark_deal_won(record.get("payer_contact", ""))

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
                record.get("client_id", ""), record.get("plan", ""), record.get("amount", 0)
            ):
                record["activated"] = True
                # Activation succeeded → front-run onboarding (KB seed + first content
                # pack) instead of waiting for the hourly sweep.
                _trigger_onboarding()
                _mark_deal_won(record.get("payer_contact", ""))
            else:
                # Approved but activation did NOT succeed (unknown plan / activation
                # error) → revenue-critical SILENT failure: alert ops (best-effort).
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
