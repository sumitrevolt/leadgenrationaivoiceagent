"""Product One delivery state.

One compact, customer-safe view of what the Rs.1999 AI Marketing plan owes,
what is done, what is blocked, and what proof exists. This module is deliberately
derived from existing stores (clients_store, content_queue, content_approval,
delivery_ledger) plus a tiny manual-action jsonl. No migration, no new page.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_DELIVERY_DIR = os.path.join("data", "product_one_delivery")
_REPORT_DIR = os.path.join("data", "client_reports")

PIPELINE = [
    "payment_received",
    "onboarding_pending",
    "setup_in_progress",
    "content_ready",
    "approval_pending",
    "scheduled",
    "published",
    "report_sent",
    "renewal_ready",
]

STAGE_LABELS = {
    "payment_received": "Payment Received",
    "onboarding_pending": "Onboarding Pending",
    "setup_in_progress": "Setup In Progress",
    "content_ready": "Content Ready",
    "approval_pending": "Approval Pending",
    "scheduled": "Scheduled",
    "published": "Published",
    "report_sent": "Report Sent",
    "renewal_ready": "Renewal Ready",
}

DELIVERABLES = [
    ("business_profile", "Business profile setup", "Customer details + local offer captured"),
    ("brand_kit", "Brand kit", "Logo text, colors, tone, and basic brand identity"),
    (
        "branded_posters",
        "4 branded posters",
        "At least 4 branded SVG poster drafts (type=poster only)",
    ),
    ("social_posts", "12 social captions or posts", "Monthly social content draft bank"),
    ("festival_ideas", "Festival/local post suggestions", "Local/festival campaign ideas"),
    (
        "gbp_suggestions",
        "Google Business Profile audit + suggestions",
        "Scored GBP audit (0–100) OR GBP content suggestions ready",
    ),
    ("whatsapp_pack", "WhatsApp marketing content pack", "Ready-to-send WhatsApp promo copy"),
    ("review_replies", "Review reply drafts", "Reusable review response drafts"),
    ("monthly_report", "Monthly performance/report summary", "Monthly proof/report generated"),
    (
        "proof",
        "Proof of published/scheduled work",
        "Published, scheduled, or manual proof note exists",
    ),
]

ACTION_LABELS = {
    "manual_task_done": "Manual task marked done",
    "retry_failed": "Retry requested",
    "send_reminder": "Customer reminder prepared",
    "generate_content": "Missing content generated",
    "approve_pending": "Pending approvals approved",
    "publish_manual": "Manual publishing proof added",
    "monthly_report": "Monthly report generated",
    "assign_owner": "Owner assigned",
}

ProductOnePlanDeliverables = {
    "starter": [
        {
            "deliverable_type": "business_profile",
            "title": "Business profile setup",
            "description": "Customer details + local offer captured",
            "channel": "dashboard",
            "owner": "Customer",
        },
        {
            "deliverable_type": "brand_kit",
            "title": "Brand kit",
            "description": "Logo text, colors, tone, and basic brand identity",
            "channel": "dashboard",
            "owner": "Customer + AI",
        },
        {
            "deliverable_type": "branded_posters",
            "title": "4 branded posters",
            "description": "At least 4 branded SVG poster drafts (type=poster only)",
            "channel": "poster",
            "owner": "AI",
        },
        {
            "deliverable_type": "social_posts",
            "title": "12 social captions or posts",
            "description": "Monthly social content draft bank",
            "channel": "dashboard",
            "owner": "AI",
        },
        {
            "deliverable_type": "festival_ideas",
            "title": "Festival/local post suggestions",
            "description": "Local/festival campaign ideas",
            "channel": "dashboard",
            "owner": "AI",
        },
        {
            "deliverable_type": "gbp_suggestions",
            "title": "Google Business Profile content suggestions",
            "description": "GBP/update ideas ready",
            "channel": "gbp",
            "owner": "AI",
        },
        {
            "deliverable_type": "whatsapp_pack",
            "title": "WhatsApp marketing content pack",
            "description": "Ready-to-send WhatsApp promo copy",
            "channel": "whatsapp_manual",
            "owner": "AI",
        },
        {
            "deliverable_type": "review_replies",
            "title": "Review reply drafts",
            "description": "Reusable review response drafts",
            "channel": "dashboard",
            "owner": "AI",
        },
        {
            "deliverable_type": "monthly_report",
            "title": "Monthly performance snapshot",
            "description": "Monthly proof/report generated",
            "channel": "report",
            "owner": "System",
        },
        {
            "deliverable_type": "proof",
            "title": "Proof of published/scheduled work",
            "description": "Published, scheduled, or manual proof note exists",
            "channel": "dashboard",
            "owner": "System",
        },
    ]
}

_LEGACY_DB_DELIVERABLE_TYPES = {
    "onboarding_profile": "business_profile",
    "branded_poster": "branded_posters",
    "monthly_content_calendar": "social_posts",
    "social_post_draft": "social_posts",
    "whatsapp_content_pack": "whatsapp_pack",
    "google_business_profile_suggestion": "gbp_suggestions",
    "review_reply_draft": "review_replies",
    "monthly_performance_snapshot": "monthly_report",
}


def _deliverable_type_candidates(did: str) -> list[str]:
    """Current type + every legacy alias that maps to it.

    `_LEGACY_DB_DELIVERABLE_TYPES` is only applied in-place when
    `initialize_deliverables_for_client` re-runs for the same client+cycle. Rows
    seeded before the rename and never re-seeded still hold the OLD names, so a
    writer passing the current name (`social_posts`) misses a row stored as
    `social_post_draft`. Matching both is read-side only — no data is rewritten.
    """
    key = str(did or "").strip()
    if not key:
        return []
    out = [key]
    for legacy, current in _LEGACY_DB_DELIVERABLE_TYPES.items():
        if current == key and legacy not in out:
            out.append(legacy)
    return out


def _deliverable_client_id_candidates(cid: str) -> list[str]:
    """Every id this customer's deliverable rows could legitimately be keyed on.

    The two stores use different ids on purpose (`clients_store.resolve_client`
    docstring). `customer_deliverables.client_id` is an FK to Postgres
    `clients.id`, so rows are seeded under the BILLING id — while every writer
    that advances them (`auto_content`, admin actions) passes the MARKETING id.
    Exact-match therefore returns 0 rows and `sync_customer_deliverable_status`
    silently returns False; production showed 24 successful content runs against
    20 rows still reading `not_started`.

    Every other marketing-domain consumer already got the canonicalisation
    retrofit (`customer_delivery_status`, `customer_auth`, `_billing_client_ids`);
    this writer is the one that was missed. Expanding the match — rather than
    re-keying rows or moving the seed to the marketing id (which would violate
    the FK) — keeps the fix read-side and reversible.

    Never raises: an unresolvable id degrades to exact-match, i.e. today's
    behaviour.
    """
    key = str(cid or "").strip()
    if not key:
        return []
    out = [key]
    try:
        from app.marketing import clients_store

        rec = clients_store.resolve_client(key)
        if rec:
            mid = str(rec.get("id") or "").strip()
            if mid and mid not in out:
                out.append(mid)
            for alias in rec.get("billing_client_ids") or []:
                a = str(alias or "").strip()
                if a and a not in out:
                    out.append(a)
    except Exception:
        pass
    return out


def cycle_seed_enabled() -> bool:
    """`DELIVERABLE_CYCLE_SEED` gate — unset/0 = INERT (default)."""
    return os.environ.get("DELIVERABLE_CYCLE_SEED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def current_cycle_month() -> str:
    """Billing cycle key `YYYY-MM` in IST — these are Indian-business cycles, and
    a UTC month boundary would flip 5h30m early for the customer."""
    return (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime("%Y-%m")


# Subscription states that mean "this tenant is no longer paying". Anything NOT
# in here is treated as live, so an unknown/new status fails SAFE (seeds a row)
# rather than silently withholding a paying customer's deliverables.
_DEAD_SUBSCRIPTION_STATES = frozenset({"cancelled", "canceled", "expired", "ended"})


def seed_current_cycle_deliverables(
    month: str | None = None, limit: int = 200, dry_run: bool = True
) -> dict[str, Any]:
    """Create the CURRENT billing cycle's deliverable rows for every live tenant.

    WHY THIS EXISTS (2026-08-07). `initialize_deliverables_for_client` is called
    from exactly one place — `app/billing/usage.py` on plan activation. Nothing
    re-seeds when the month rolls over. Production proof: `customer_deliverables`
    held 20 rows, ALL `billing_cycle_month = '2026-07'`, newest created
    2026-07-18, and no scheduler job referenced deliverables at all. The one
    paying customer was 30+ days into a paid month with no current-cycle ledger,
    so `sync_customer_deliverable_status` had nothing to attach to no matter how
    much content was generated.

    Selector is the SUBSCRIPTION, not `clients.status`: a subscription that is
    not in a terminal state is the only honest definition of "still paying".
    This also keeps quarantined fixture tenants out by construction — they have
    no subscription rows at all.

    Seeds under the BILLING id (Postgres `clients.id`) because
    `customer_deliverables.client_id` is an FK to that table. The marketing-id
    side is handled read-side by `_deliverable_client_id_candidates`.

    Idempotent — `initialize_deliverables_for_client` already skips existing
    types for the same client+cycle, so re-running is a no-op. Never raises.
    """
    out: dict[str, Any] = {
        "cycle": month or current_cycle_month(),
        "clients_scanned": 0,
        "rows_created": 0,
        "skipped_existing": 0,
        "skipped_dead_subscription": 0,
        "skipped_no_db_client": 0,
        "errors": 0,
        "dry_run": bool(dry_run),
        "seeded_clients": [],
    }
    cycle = out["cycle"]
    try:
        from app.models.base import get_db_session
        from app.models.client import Client
        from app.models.customer_deliverable import CustomerDeliverable
        from app.models.payment import Subscription

        with get_db_session() as db:
            subs = db.query(Subscription).limit(max(1, int(limit))).all()
            for sub in subs:
                cid = str(getattr(sub, "client_id", "") or "").strip()
                if not cid:
                    continue
                out["clients_scanned"] += 1
                try:
                    st = (
                        str(
                            getattr(getattr(sub, "status", ""), "value", getattr(sub, "status", ""))
                            or ""
                        )
                        .strip()
                        .lower()
                    )
                    if st in _DEAD_SUBSCRIPTION_STATES:
                        out["skipped_dead_subscription"] += 1
                        continue

                    # FK guard — seeding against a missing client row would raise.
                    client = db.get(Client, cid)
                    if client is None:
                        out["skipped_no_db_client"] += 1
                        continue

                    before = (
                        db.query(CustomerDeliverable)
                        .filter(
                            CustomerDeliverable.client_id == cid,
                            CustomerDeliverable.billing_cycle_month == cycle,
                        )
                        .count()
                    )
                    if before and dry_run:
                        out["skipped_existing"] += 1
                        continue
                    if dry_run:
                        out["seeded_clients"].append({"client_id": cid, "would_create": True})
                        continue

                    plan = str(
                        getattr(sub, "plan_name", "") or getattr(client, "plan", "") or "starter"
                    )
                    initialize_deliverables_for_client(db, cid, plan, cycle)
                    db.commit()

                    after = (
                        db.query(CustomerDeliverable)
                        .filter(
                            CustomerDeliverable.client_id == cid,
                            CustomerDeliverable.billing_cycle_month == cycle,
                        )
                        .count()
                    )
                    created = max(0, after - before)
                    out["rows_created"] += created
                    if created == 0:
                        out["skipped_existing"] += 1
                    else:
                        out["seeded_clients"].append({"client_id": cid, "created": created})
                except Exception as inner:
                    out["errors"] += 1
                    logger.warning("[cycle-seed] client %s failed: %s", cid, inner)
    except Exception as e:
        out["errors"] += 1
        out["error"] = str(e)[:200]
        logger.warning("[cycle-seed] sweep failed: %s", e)
    return out


def initialize_deliverables_for_client(
    db, client_id: str, plan_code: str | None, billing_cycle_month: str
) -> None:
    """Create initial customer deliverables for the billing cycle month from the plan template if missing.
    Idempotent, never duplicates.
    """
    from app.models.customer_deliverable import (
        CustomerDeliverable,
        DeliverableChannel,
        DeliverableStatus,
    )

    plan_code = (plan_code or "starter").strip().lower()
    template_key = (
        "starter"
        if plan_code in ("starter", "marketing", "growth", "combo", "advanced")
        else "starter"
    )

    template = ProductOnePlanDeliverables.get(template_key, ProductOnePlanDeliverables["starter"])

    existing_rows = (
        db.query(CustomerDeliverable)
        .filter(
            CustomerDeliverable.client_id == client_id,
            CustomerDeliverable.billing_cycle_month == billing_cycle_month,
        )
        .all()
    )
    existing_types: set[str] = set()
    for row in existing_rows:
        dtype = str(row.deliverable_type or "")
        mapped = _LEGACY_DB_DELIVERABLE_TYPES.get(dtype, dtype)
        # One-time in-place taxonomy reconciliation. No destructive delete:
        # if a legacy row maps to an existing semantic row, leave it as audit
        # history; otherwise rename it so future reports can key on the same
        # ids as the frontend/jsonl status (`DELIVERABLES`).
        if mapped != dtype and mapped not in existing_types:
            row.deliverable_type = mapped
            dtype = mapped
        existing_types.add(dtype)

    for item in template:
        dtype = item["deliverable_type"]
        if dtype not in existing_types:
            due_date = datetime.utcnow() + timedelta(days=30)
            if dtype == "business_profile":
                due_date = datetime.utcnow() + timedelta(days=1)
            elif dtype == "brand_kit":
                due_date = datetime.utcnow() + timedelta(days=3)
            elif dtype == "social_posts":
                due_date = datetime.utcnow() + timedelta(days=7)

            status_val = DeliverableStatus.NOT_STARTED
            if dtype == "business_profile":
                status_val = DeliverableStatus.WAITING_CUSTOMER

            row = CustomerDeliverable(
                id=str(uuid.uuid4()),
                client_id=client_id,
                plan_code=plan_code,
                billing_cycle_month=billing_cycle_month,
                deliverable_type=dtype,
                title=item["title"],
                description=item["description"],
                status=status_val,
                channel=DeliverableChannel(item["channel"]),
                due_date=due_date,
                delivered_at=None,
                evidence_url=None,
                owner=item["owner"],
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(row)
    db.commit()


def sync_customer_deliverable_status(
    client_id: str,
    deliverable_id: str,
    status: str,
    *,
    billing_cycle_month: str | None = None,
    evidence_url: str = "",
    evidence_payload: dict[str, Any] | str | None = None,
    note: str = "",
    owner: str = "",
    error_message: str = "",
) -> bool:
    """Best-effort DB row sync for real delivery actions.

    This intentionally updates existing rows only. Plan activation owns row
    creation because that path guarantees a DB Client row exists; generation/
    publish paths may still be serving jsonl-only customers and must never fail
    or create FK errors while doing delivery work.
    """
    cid = str(client_id or "").strip()
    did = str(deliverable_id or "").strip()
    if not cid or not did:
        return False

    # Alias-expand BOTH keys before querying — see the two helpers above for why
    # exact-match silently lost every update on the dual-id / pre-rename path.
    cid_candidates = _deliverable_client_id_candidates(cid)
    did_candidates = _deliverable_type_candidates(did)

    def _apply(db) -> bool:
        from app.models.customer_deliverable import CustomerDeliverable, DeliverableStatus

        q = db.query(CustomerDeliverable).filter(
            CustomerDeliverable.client_id.in_(cid_candidates),
            CustomerDeliverable.deliverable_type.in_(did_candidates),
        )
        if billing_cycle_month:
            q = q.filter(CustomerDeliverable.billing_cycle_month == billing_cycle_month)
        row = q.order_by(
            CustomerDeliverable.billing_cycle_month.desc(), CustomerDeliverable.created_at.desc()
        ).first()
        if row is None:
            return False

        try:
            status_val = DeliverableStatus(str(status or "").strip().lower())
        except Exception:
            return False

        row.status = status_val
        row.updated_at = datetime.utcnow()
        if status_val == DeliverableStatus.DELIVERED and row.delivered_at is None:
            row.delivered_at = row.updated_at
        if evidence_url:
            row.evidence_url = str(evidence_url)[:500]
        if evidence_payload is not None or note:
            payload = evidence_payload
            if payload is None:
                payload = {"note": note}
            elif isinstance(payload, dict) and note and "note" not in payload:
                payload = {**payload, "note": note}
            row.evidence_payload = json.dumps(payload, ensure_ascii=False, default=str)[:4000]
        if owner:
            row.owner = str(owner)[:50]
        if error_message:
            row.error_message = str(error_message)[:2000]
        elif status_val != DeliverableStatus.FAILED:
            row.error_message = None
        return True

    try:
        from app.models.base import get_db_session

        with get_db_session() as db:
            return _apply(db)
    except Exception as exc:
        logger.debug("customer deliverable status sync skipped (%s/%s): %s", cid, did, exc)
        return False


def _db_progress_from_status(status: Any) -> str:
    raw = getattr(status, "value", status)
    s = str(raw or "").strip().lower()
    if s == "delivered":
        return "done"
    if s in ("ready_to_generate", "generating", "pending_approval", "approved", "scheduled"):
        return "in_progress"
    if s in ("failed", "skipped"):
        return s
    return "pending"


def customer_deliverable_db_audit(cards: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Compare DB sidecar rows with current customer-facing derived state.

    This is an admin/operator migration-safety signal, not the customer read
    path. It lets us prove whether `customer_deliverables` is ready to become a
    source of truth later without silently changing the UI today.
    """
    cards = list(cards or [])
    out: dict[str, Any] = {
        "ok": True,
        "checked_customers": len(cards),
        "checked_deliverables": 0,
        "missing_rows": 0,
        "stale_db_rows": 0,
        "ahead_db_rows": 0,
        "mismatches": [],
        "read_path_ready": False,
    }
    client_ids = [str(c.get("id") or "").strip() for c in cards if str(c.get("id") or "").strip()]
    if not client_ids:
        out["read_path_ready"] = True
        return out

    try:
        from app.models.base import get_db_session
        from app.models.customer_deliverable import CustomerDeliverable

        with get_db_session() as db:
            rows = (
                db.query(CustomerDeliverable)
                .filter(CustomerDeliverable.client_id.in_(client_ids))
                .order_by(
                    CustomerDeliverable.billing_cycle_month.desc(),
                    CustomerDeliverable.created_at.desc(),
                )
                .all()
            )
            db_by_client: dict[str, dict[str, Any]] = {}
            for row in rows:
                cid = str(row.client_id or "")
                dtype = str(row.deliverable_type or "")
                if cid and dtype and dtype not in db_by_client.setdefault(cid, {}):
                    db_by_client[cid][dtype] = {
                        "status": getattr(row.status, "value", row.status),
                        "billing_cycle_month": row.billing_cycle_month,
                    }
    except Exception as exc:
        out.update({"ok": False, "error": str(exc)[:180], "read_path_ready": False})
        return out

    mismatches: list[dict[str, Any]] = []
    for card in cards:
        cid = str(card.get("id") or "")
        customer_name = str(card.get("customer_name") or card.get("business_name") or cid)
        db_rows = db_by_client.get(cid, {})
        for deliverable in card.get("deliverables") or []:
            did = str(deliverable.get("id") or "")
            if not did:
                continue
            out["checked_deliverables"] += 1
            derived = str(deliverable.get("status") or "pending").lower()
            row = db_rows.get(did)
            if row is None:
                out["missing_rows"] += 1
                mismatches.append(
                    {
                        "client_id": cid,
                        "customer_name": customer_name,
                        "deliverable_id": did,
                        "derived_status": derived,
                        "db_status": "missing",
                        "kind": "missing_row",
                    }
                )
                continue
            db_status = row.get("status")
            db_progress = _db_progress_from_status(db_status)
            if derived == "done" and db_progress != "done":
                out["stale_db_rows"] += 1
                mismatches.append(
                    {
                        "client_id": cid,
                        "customer_name": customer_name,
                        "deliverable_id": did,
                        "derived_status": derived,
                        "db_status": str(db_status or ""),
                        "kind": "db_behind",
                    }
                )
            elif db_progress == "done" and derived != "done":
                out["ahead_db_rows"] += 1
                mismatches.append(
                    {
                        "client_id": cid,
                        "customer_name": customer_name,
                        "deliverable_id": did,
                        "derived_status": derived,
                        "db_status": str(db_status or ""),
                        "kind": "db_ahead",
                    }
                )

    out["mismatches"] = mismatches[:50]
    out["read_path_ready"] = not (
        out["missing_rows"] or out["stale_db_rows"] or out["ahead_db_rows"]
    )
    return out


WORKFLOWS = [
    {
        "id": "after_payment_customer_creation",
        "name": "After payment customer creation",
        "trigger_source": "payment_confirmed",
        "action": "send_reminder",
        "deliverable_id": "business_profile",
        "customer_safe": True,
    },
    {
        "id": "onboarding_reminder",
        "name": "Onboarding reminder",
        "trigger_source": "setup_incomplete",
        "action": "send_reminder",
        "deliverable_id": "business_profile",
        "customer_safe": True,
    },
    {
        "id": "brand_kit_generation",
        "name": "Brand kit generation",
        "trigger_source": "setup_completed",
        "action": "manual_task_done",
        "deliverable_id": "brand_kit",
        "customer_safe": True,
    },
    {
        "id": "content_generation",
        "name": "Content generation",
        "trigger_source": "admin_or_scheduler",
        "action": "generate_content",
        "deliverable_id": "social_posts",
        "customer_safe": True,
    },
    {
        "id": "approval_request",
        "name": "Approval request",
        "trigger_source": "content_ready",
        "action": "send_reminder",
        "deliverable_id": "social_posts",
        "customer_safe": True,
    },
    {
        "id": "scheduled_publishing",
        "name": "Scheduled publishing",
        "trigger_source": "approval_received",
        "action": "publish_manual",
        "deliverable_id": "proof",
        "customer_safe": True,
    },
    {
        "id": "failed_publish_retry",
        "name": "Failed publish retry",
        "trigger_source": "automation_failed",
        "action": "retry_failed",
        "deliverable_id": "proof",
        "customer_safe": False,
    },
    {
        "id": "manual_task_creation",
        "name": "Manual task creation",
        "trigger_source": "admin",
        "action": "manual_task_done",
        "deliverable_id": "proof",
        "customer_safe": True,
    },
    {
        "id": "monthly_report_generation",
        "name": "Monthly report generation",
        "trigger_source": "month_end",
        "action": "monthly_report",
        "deliverable_id": "monthly_report",
        "customer_safe": True,
    },
    {
        "id": "renewal_reminder",
        "name": "Renewal reminder",
        "trigger_source": "renewal_window",
        "action": "send_reminder",
        "deliverable_id": "monthly_report",
        "customer_safe": True,
    },
]

_WORKFLOW_BY_ID = {w["id"]: w for w in WORKFLOWS}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_cid(cid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in str(cid or "").strip())[:80]


def _events_path(cid: str) -> str:
    return os.path.join(_DELIVERY_DIR, f"{_safe_cid(cid)}.jsonl")


def _append_event(cid: str, rec: dict[str, Any]) -> None:
    os.makedirs(_DELIVERY_DIR, exist_ok=True)
    with open(_events_path(cid), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


def manual_events(cid: str, limit: int = 200) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        path = _events_path(cid)
        if not os.path.isfile(path):
            return rows
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict):
                    rows.append(rec)
        rows.sort(key=lambda r: str(r.get("at") or ""), reverse=True)
        return rows[: max(1, min(int(limit or 200), 500))]
    except Exception as exc:
        logger.debug("product_one_delivery manual_events failed (%s): %s", cid, exc)
        return []


def _content_items(cid: str) -> list[dict[str, Any]]:
    try:
        from app.marketing import auto_content

        return list(auto_content.list_queue(cid, limit=500) or [])
    except Exception:
        return []


def _approvals(cid: str) -> list[dict[str, Any]]:
    try:
        from app.marketing import content_approval

        return list(content_approval.list_all(cid, limit=500) or [])
    except Exception:
        return []


def _ledger_summary(cid: str) -> dict[str, Any]:
    try:
        from app.marketing import delivery_ledger

        delivery_ledger.ensure_backfilled(cid)
        return dict(delivery_ledger.summary(cid) or {})
    except Exception:
        return {}


def _monthly_report_on_disk(cid: str, client: dict[str, Any] | None = None) -> bool:
    """True if this month's white-label HTML report exists for marketing id OR billing aliases."""
    try:
        month = time.strftime("%Y-%m")
        ids: list[str] = [str(cid or "").strip()]
        aliases = (client or {}).get("billing_client_ids") or []
        if isinstance(aliases, list | tuple | set):
            ids.extend(str(a).strip() for a in aliases if str(a).strip())
        out_dir = _REPORT_DIR
        for i in ids:
            if i and os.path.isfile(os.path.join(out_dir, f"{i}_{month}.html")):
                return True
    except Exception:
        return False
    return False


# Persisted by POST /api/customer/gbp/score (customer_dashboard._GBP_DIR).
# Override in tests via monkeypatch — never invent a score from GBP URL alone.
_GBP_AUDIT_DIR = os.path.join("data", "gbp_audits")


def _gbp_scored_audit(cid: str) -> dict[str, Any] | None:
    """Latest persisted GBP self-audit (0–100) for this client, if any. Never raises."""
    try:
        fp = os.path.join(_GBP_AUDIT_DIR, f"{_safe_cid(cid)}.json")
        if not os.path.isfile(fp):
            return None
        with open(fp, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return None
        score = data.get("score")
        if score is None:
            return None
        return data
    except Exception:
        return None


def _ledger_recent_failures(cid: str) -> int:
    """24h rolling failure count — used for health score RED flag instead of
    all-time `automation_failures`. Prevents historical failures from
    permanently tanking the score once the root cause is fixed."""
    try:
        from app.marketing import delivery_ledger

        rc = delivery_ledger.recent_counts(cid, hours=24) or {}
        return int(rc.get("failures_24h") or 0)
    except Exception:
        return 0


def _ledger_events(cid: str) -> list[dict[str, Any]]:
    try:
        from app.marketing import delivery_ledger

        delivery_ledger.ensure_backfilled(cid)
        return list(delivery_ledger.timeline(cid, limit=120, customer_only=False) or [])
    except Exception:
        return []


def _client_plan_paid(client: dict[str, Any]) -> bool:
    plan = str(client.get("plan") or "").strip().lower()
    return plan not in ("", "trial", "free", "none", "pending")


# --------------------------------------------------------------------------- #
# Customer Health + Approval Reminder + SLA Recovery (2026-07-08 Product 1
# Customer Deliverability layer). These are DERIVED, read-mostly additions on
# top of the state already computed above — no new store, no duplicate agent.
# --------------------------------------------------------------------------- #
_APPROVAL_STALE_HOURS = 24
_APPROVAL_URGENT_HOURS = 48
_APPROVAL_CRITICAL_HOURS = 72
_SLA_NO_DELIVERABLE_HOURS = 24


def _parse_dt(raw: str) -> datetime | None:
    try:
        s = str(raw or "").strip()
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _hours_since(raw: str) -> float | None:
    dt = _parse_dt(raw)
    if dt is None:
        return None
    delta = datetime.now(timezone.utc) - dt
    return max(0.0, delta.total_seconds() / 3600.0)


def _approval_escalation_level(hours_open: float) -> str:
    if hours_open >= _APPROVAL_CRITICAL_HOURS:
        return "admin_manual_action"
    if hours_open >= _APPROVAL_URGENT_HOURS:
        return "urgent_48h"
    if hours_open >= _APPROVAL_STALE_HOURS:
        return "stale_24h"
    return "normal"


def _escalate_approvals(pending_approvals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Approval Reminder Agent scoring: age every pending approval into a
    normal/stale_24h/urgent_48h/admin_manual_action escalation level (never
    sends anything — notification is a separate, explicitly-gated channel)."""
    out: list[dict[str, Any]] = []
    for a in pending_approvals:
        created = str(a.get("created_at") or a.get("at") or "")
        hours_open = _hours_since(created)
        hours_open = 0.0 if hours_open is None else round(hours_open, 1)
        out.append(
            {
                "id": a.get("id") or a.get("token") or "",
                "client_id": a.get("client_id") or "",
                "hours_open": hours_open,
                "escalation": _approval_escalation_level(hours_open),
                "owner": a.get("owner") or "Sumit",
            }
        )
    return out


# Lifecycle/bookkeeping events, not marketing deliverables. `ensure_backfilled`
# writes `customer_created` (and sometimes `onboarding_completed`) with an
# "at"=now() timestamp on a customer's FIRST ever ledger read, regardless of
# whether any real content exists — so if these counted toward "last
# deliverable", a paid customer with zero posts/reports would look freshly
# delivered the moment anyone opened their dashboard, masking exactly the
# "zero deliverables" red flag this health check exists to catch.
_NON_DELIVERABLE_EVENTS = {
    "customer_created",
    "plan_activated",
    "onboarding_started",
    "onboarding_completed",
}


def _last_deliverable_hours(
    led_events: list[dict[str, Any]],
    actions: list[dict[str, Any]] | None = None,
) -> float | None:
    """Hours since the most recent real deliverable: either a customer-visible
    Delivery Ledger event, OR a successful Delivery Cockpit manual action
    (generate content / publish manual / monthly report). The cockpit's manual
    actions only write the internal `admin_manual_action` ledger marker
    (customer_visible=False, by design — see delivery_ledger.LABELS), so
    without also checking `actions` here, an admin manually publishing/
    generating for a customer would correctly mark the deliverable "done" but
    never register as recent activity for health scoring. Both lists are
    already newest-first, so the first qualifying hit from each is enough."""
    candidates: list[float] = []
    for ev in led_events:
        if str(ev.get("event") or "") in _NON_DELIVERABLE_EVENTS:
            continue
        if ev.get("customer_visible", True):
            hrs = _hours_since(str(ev.get("at") or ""))
            if hrs is not None:
                candidates.append(hrs)
            break
    for ev in actions or []:
        if str(ev.get("status") or "") in ("success", "manual_required", "done"):
            hrs = _hours_since(str(ev.get("at") or ev.get("started_at") or ""))
            if hrs is not None:
                candidates.append(hrs)
            break
    return min(candidates) if candidates else None


def _customer_health(
    *,
    client: dict[str, Any],
    stage: str,
    risk_flag: str,
    setup_pct: int,
    setup: dict[str, bool],
    failed_count: int,
    led_events: list[dict[str, Any]],
    approvals_escalated: list[dict[str, Any]],
    actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Customer Health Agent: green/yellow/red + score + reason codes + SLA
    countdown. Only meaningful for paid Product 1 customers; unpaid/trial
    customers are always 'green' (not yet an SLA-bearing relationship)."""
    if not _client_plan_paid(client):
        return {"status": "green", "score": 100, "reasons": [], "sla_hours_remaining": None}

    red: list[str] = []
    yellow: list[str] = []
    worst_escalation = "normal"
    for a in approvals_escalated:
        order = ["normal", "stale_24h", "urgent_48h", "admin_manual_action"]
        if order.index(a["escalation"]) > order.index(worst_escalation):
            worst_escalation = a["escalation"]

    hours_since_last = _last_deliverable_hours(led_events, actions)
    # IMPORTANT: "blank" means no CUSTOMER-VISIBLE deliverable ever happened —
    # not "the ledger file is empty". Ops-only events (automation_failed,
    # admin_manual_action, sla_breached/sla_recovered) are customer_visible=
    # False, so without this the SLA sweep's OWN sla_breached write would
    # "un-blank" a customer who still has zero real deliverables the very
    # next time health is computed (self-masking bug caught in review).
    blank_timeline = hours_since_last is None

    if failed_count:
        red.append("automation_failed")
    if blank_timeline:
        red.append("blank_timeline")
    elif (
        hours_since_last is not None
        and hours_since_last > _SLA_NO_DELIVERABLE_HOURS
        and stage
        in (
            "payment_received",
            "onboarding_pending",
            "setup_in_progress",
            "content_ready",
        )
    ):
        red.append("no_deliverable_24h")
    if worst_escalation == "admin_manual_action":
        red.append("approval_critical_stale")

    if setup_pct < 100:
        yellow.append("setup_incomplete")
    if approvals_escalated:
        yellow.append("pending_approval")
    if worst_escalation in ("stale_24h", "urgent_48h"):
        yellow.append("approval_stale")
    if not setup.get("social"):
        yellow.append("manual_publish_mode")

    if red:
        status = "red"
    elif yellow:
        status = "yellow"
    else:
        status = "green"

    score = 100 - 35 * len(red) - 12 * len(yellow)
    score = max(0, min(100, score))

    sla_hours_remaining: float | None = None
    if hours_since_last is not None:
        sla_hours_remaining = round(_SLA_NO_DELIVERABLE_HOURS - hours_since_last, 1)
    for a in approvals_escalated:
        if a["escalation"] in ("normal", "stale_24h"):
            remaining = (
                round(_APPROVAL_STALE_HOURS - a["hours_open"], 1)
                if a["escalation"] == "normal"
                else round(_APPROVAL_URGENT_HOURS - a["hours_open"], 1)
            )
            if sla_hours_remaining is None or remaining < sla_hours_remaining:
                sla_hours_remaining = remaining

    return {
        "status": status,
        "score": score,
        "reasons": red + yellow,
        "sla_hours_remaining": sla_hours_remaining,
    }


def _setup_checks(client: dict[str, Any]) -> dict[str, bool]:
    brand = client.get("brand") if isinstance(client.get("brand"), dict) else {}
    socials = client.get("socials") if isinstance(client.get("socials"), dict) else {}
    return {
        "business": bool(
            client.get("business_name") and (client.get("city") or client.get("phone"))
        ),
        "offer": bool(client.get("services") or client.get("target_area")),
        "brand": bool(
            (brand or {}).get("primary")
            or (brand or {}).get("logo_text")
            or (brand or {}).get("tagline")
        ),
        "social": bool(
            any((socials or {}).get(k) for k in ("instagram", "facebook", "gbp"))
            or client.get("whatsapp_phone")
        ),
        "approval": bool(client.get("approval_preference")),
    }


def _manual_done(actions: list[dict[str, Any]], deliverable_id: str) -> dict[str, Any] | None:
    for ev in actions:
        if ev.get("deliverable_id") == deliverable_id and ev.get("status") in (
            "success",
            "manual_required",
            "done",
        ):
            return ev
    return None


def _deliverable(
    did: str,
    title: str,
    description: str,
    status: str,
    *,
    created_at: str = "",
    approved_at: str = "",
    published_at: str = "",
    proof_url: str = "",
    proof_note: str = "",
    owner: str = "AI Team",
    customer_visible: bool = True,
    next_action: str = "",
    integration_required: str = "",
) -> dict[str, Any]:
    return {
        "id": did,
        "title": title,
        "description": description,
        "status": status,
        "created_at": created_at,
        "approved_at": approved_at,
        "published_at": published_at,
        "proof_url": proof_url,
        "proof_note": proof_note,
        "owner": owner,
        "customer_visible": bool(customer_visible),
        "next_action": next_action,
        "integration_required": integration_required,
    }


def customer_delivery_status(
    client_id: str, client: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Full Product One state for one customer. Never raises."""
    cid = str(client_id or "").strip()
    try:
        from app.marketing import clients_store

        # Canonicalize billing/subscription/login ids (e.g. Jiya's
        # `d79d690f61b3`) to the marketing client id (`jiya-makeover`) so every
        # content/approval/ledger/report read below hits the SAME identity the
        # marketing pipeline keyed the work on. Passing the alias id otherwise
        # produced a partial "orphan" view (Jiya: 10% shown vs 60% real).
        # canonical_client_id falls back to the raw id; never raises.
        canon = clients_store.canonical_client_id(cid)
        if canon:
            cid = canon
        if client is None:
            client = clients_store.get_client(cid) or {}
        client = client or {}
        setup = _setup_checks(client)
        setup_pct = int(round(sum(1 for v in setup.values() if v) / max(1, len(setup)) * 100))
        items = _content_items(cid)
        approvals = _approvals(cid)
        ledger = _ledger_summary(cid)
        led_events = _ledger_events(cid)
        actions = manual_events(cid)

        # Branded posters = type "poster" ONLY. Festival SVG/text posts are a
        # separate deliverable (festival_ideas). Counting festival as posters
        # padded "4/4" for Jiya with 1 real poster + 3 festival items (audit 2026-07-17).
        posters = [i for i in items if str(i.get("type") or "").lower() == "poster"]
        post_like = [
            i
            for i in items
            if str(i.get("type") or "").lower()
            in ("post", "reel", "festival", "campaign", "whatsapp")
        ]
        approved = [
            i
            for i in items
            if str(i.get("status") or "").lower()
            in ("approved", "scheduled", "posted", "published")
        ]
        published = [
            i for i in items if str(i.get("status") or "").lower() in ("posted", "published")
        ]
        pending_approvals = [a for a in approvals if str(a.get("status") or "") == "pending"]
        # 24h rolling window — historical failures don't permanently tank
        # health score; once root cause is fixed, score recovers within a day.
        failed_count = _ledger_recent_failures(cid)

        def has_content_type(*types: str) -> bool:
            want = {t.lower() for t in types}
            return any(str(i.get("type") or "").lower() in want for i in items)

        report_action = _manual_done(actions, "monthly_report")
        proof_action = _manual_done(actions, "proof")
        publish_action = _manual_done(actions, "publish_manual")
        report_on_disk = _monthly_report_on_disk(cid, client)
        gbp_audit = _gbp_scored_audit(cid)
        gbp_done = bool(
            gbp_audit
            or has_content_type("gbp", "gbp_post")
            or _manual_done(actions, "gbp_suggestions")
        )
        gbp_link = bool(client.get("gbp") or (client.get("socials") or {}).get("gbp"))

        # Database-backed CustomerDeliverable sync (2026-07-08, parallel track).
        # This is real forward progress toward a proper per-billing-cycle
        # deliverable ledger — but its rows are NOT what gets returned below.
        # Reasons: (1) its deliverable_type taxonomy and row-id (a UUID) don't
        # match the semantic ids every existing consumer keys on (frontend
        # customer_dashboard.html, admin_customer_card, this module's own
        # _customer_status_notes/_monthly_summary, and every acceptance test)
        # — swapping the return shape here would silently break all of them;
        # (2) initializing it here used to run on every call to this function
        # (every dashboard load, every admin cockpit render, every hourly
        # sweep) — a mandatory DB round-trip through the sync engine's small
        # background-only pool (app/models/base.py, pool_size=3) that FK-
        # violated for every client without a DB `Client` row (self-serve
        # signups + Stripe customers live jsonl-only until they hit the UPI/
        # admin `ensure_subscription=True` path — see app/billing/usage.py's
        # _ensure_db_client), silently failing on every single request for
        # most customers with zero benefit since the rows were never read
        # back anyway (database-architect audit, 2026-07-08). Initialization
        # now happens once, at plan-activation time, in
        # app.billing.usage._create_subscription_row — right after the DB
        # Client row is guaranteed to exist — instead of on every read here.
        # Once the DB taxonomy is reconciled with the ids below, this can
        # become the source of truth for `deliverables` in one deliberate
        # change with its own migration/test pass — not a silent swap.

        # Integration readiness — so customer/admin know if real posting is blocked
        _social_engine_on = os.environ.get("SOCIAL_ENGINE", "0").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        _social_autopost_on = os.environ.get("SOCIAL_AUTOPOST", "0").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        _postiz_key_set = bool((os.environ.get("POSTIZ_API_KEY") or "").strip())
        _wa_auto_send = os.environ.get("WHATSAPP_AUTO_SEND", "0").strip().lower() in (
            "1",
            "true",
            "yes",
        )

        def _missing_social_integration() -> str:
            if not _social_engine_on:
                return "SOCIAL_ENGINE flag OFF — posts generated but auto-publishing nahi ho raha. Admin ko flag ON karna hoga."
            if not _social_autopost_on:
                return "SOCIAL_AUTOPOST OFF — Meta Graph posting MOCK hai. Meta app review + token ke baad ON karo."
            if not _postiz_key_set:
                return "Postiz API key set nahi hai. Multi-channel auto-publish ke liye POSTIZ_API_KEY set karo."
            return ""

        _whatsapp_blocked = (
            "WhatsApp auto-send OFF hai (WHATSAPP_AUTO_SEND=0). 1-click manual send only."
            if not _wa_auto_send
            else ""
        )

        # Per-deliverable next actions + integration labels
        deliverables = [
            _deliverable(
                *DELIVERABLES[0],
                "done" if setup["business"] else "pending",
                owner="Customer",
                next_action=(
                    "Setup Wizard me business details complete karo"
                    if not setup["business"]
                    else ""
                ),
            ),
            _deliverable(
                *DELIVERABLES[1],
                "done" if setup["brand"] else "pending",
                owner="Customer + AI",
                next_action="Logo text/colors/photo daalo" if not setup["brand"] else "",
            ),
            _deliverable(
                *DELIVERABLES[2],
                "done" if len(posters) >= 4 else ("in_progress" if posters else "pending"),
                proof_note=f"{len(posters)}/4 creatives ready",
                next_action="Admin → Generate Content dabao" if not posters else "",
                owner="AI",
            ),
            _deliverable(
                *DELIVERABLES[3],
                "done" if len(post_like) >= 12 else ("in_progress" if post_like else "pending"),
                proof_note=f"{len(post_like)}/12 posts ready",
                next_action=(
                    "Daily content job automated hai — abhi "
                    + ("kuch posts ready" if post_like else "generate hone ka wait")
                    if post_like
                    else ""
                ),
                owner="AI",
            ),
            _deliverable(
                *DELIVERABLES[4],
                (
                    "done"
                    if has_content_type("festival", "campaign")
                    or _manual_done(actions, "festival_ideas")
                    else "pending"
                ),
                next_action=(
                    "Festival calendar ke hisaab se AI auto-generate karega"
                    if _client_plan_paid(client)
                    else ""
                ),
                owner="AI",
            ),
            _deliverable(
                *DELIVERABLES[5],
                "done" if gbp_done else ("in_progress" if gbp_link else "pending"),
                proof_note=(
                    f"GBP audit score {int(gbp_audit.get('score') or 0)}/100" if gbp_audit else ""
                ),
                next_action=(
                    ""
                    if gbp_done
                    else "Reports → GBP Audit (0–100) complete karo — top-5 fixes milenge"
                ),
            ),
            _deliverable(
                *DELIVERABLES[6],
                (
                    "done"
                    if has_content_type("whatsapp") or _manual_done(actions, "whatsapp_pack")
                    else "pending"
                ),
                next_action=(
                    "Content generate hone ke baad WhatsApp pack ready hoga"
                    if _client_plan_paid(client) and not has_content_type("whatsapp")
                    else ""
                ),
                integration_required=_whatsapp_blocked,
            ),
            _deliverable(
                *DELIVERABLES[7],
                (
                    "done"
                    if has_content_type("review_reply") or _manual_done(actions, "review_replies")
                    else "pending"
                ),
                next_action=(
                    "AI review reply templates auto-generate honge"
                    if _client_plan_paid(client)
                    else ""
                ),
                owner="AI",
            ),
            _deliverable(
                *DELIVERABLES[8],
                (
                    "done"
                    if int(ledger.get("reports") or 0) > 0 or report_action or report_on_disk
                    else "pending"
                ),
                proof_note=str(
                    (report_action or {}).get("note")
                    or ("report file on disk" if report_on_disk else "")
                ),
                next_action=(
                    "Mahine ke end me auto-generate hoga — Admin Monthly Report button se bhi bana sakta hai"
                    if not report_action and not report_on_disk
                    else ""
                ),
            ),
            _deliverable(
                *DELIVERABLES[9],
                (
                    "done"
                    if published or proof_action or publish_action
                    else ("in_progress" if approved else "pending")
                ),
                proof_note=str((proof_action or publish_action or {}).get("note") or ""),
                integration_required=_missing_social_integration(),
                next_action=(
                    "Admin manual-proof/publish kare ya SOCIAL_ENGINE ON karo"
                    if not published and not proof_action and not publish_action
                    else ""
                ),
            ),
        ]
        complete = sum(1 for d in deliverables if d["status"] == "done")
        deliverable_pct = int(round(complete / max(1, len(deliverables)) * 100))

        if not _client_plan_paid(client):
            stage = "payment_received"
            next_action = "Payment confirm karo aur Product One plan assign karo."
        elif setup_pct < 60:
            stage = "onboarding_pending"
            next_action = "Customer se missing business/social details lo."
        elif setup_pct < 100:
            stage = "setup_in_progress"
            next_action = "Brand/social setup complete karvao."
        elif pending_approvals:
            stage = "approval_pending"
            next_action = f"{len(pending_approvals)} posts customer approval ka wait kar rahe hain."
        elif published or publish_action or proof_action:
            stage = "published"
            next_action = "Monthly report/proof bhejo."
        elif approved:
            stage = "scheduled"
            next_action = "Approved posts publish ya manual-upload proof add karo."
        elif items:
            stage = "content_ready"
            next_action = "Generated content customer ko approval ke liye bhejo."
        else:
            stage = "setup_in_progress" if setup_pct else "onboarding_pending"
            next_action = "Day-1 content pack generate karo."

        if (int(ledger.get("reports") or 0) > 0 or report_action) and stage not in (
            "approval_pending",
            "setup_in_progress",
            "onboarding_pending",
            "payment_received",
        ):
            stage = "report_sent"
            next_action = "Renewal ke liye monthly value recap share karo."
        if stage == "report_sent" and deliverable_pct >= 80:
            stage = "renewal_ready"
            next_action = "Renewal conversation ready hai."

        if failed_count:
            risk_flag = "automation_failed"
        elif setup_pct < 100 and _client_plan_paid(client):
            risk_flag = "customer_blocked"
        elif _client_plan_paid(client) and not items:
            risk_flag = "no_content"
        else:
            risk_flag = "ok"

        approvals_escalated = _escalate_approvals(pending_approvals)
        health = _customer_health(
            client=client,
            stage=stage,
            risk_flag=risk_flag,
            setup_pct=setup_pct,
            setup=setup,
            failed_count=failed_count,
            led_events=led_events,
            approvals_escalated=approvals_escalated,
            actions=actions,
        )

        return {
            "ok": True,
            "client_id": cid,
            "customer_name": client.get("business_name") or "Customer",
            "plan": client.get("plan") or "starter",
            "product": client.get("product") or "marketing",
            "stage": stage,
            "stage_label": STAGE_LABELS.get(stage, stage),
            "pipeline": [
                {"key": k, "label": STAGE_LABELS[k], "active": k == stage} for k in PIPELINE
            ],
            "setup_checks": setup,
            "setup_completion_pct": setup_pct,
            "deliverable_completion_pct": deliverable_pct,
            "deliverables": deliverables,
            "pending_customer_inputs": [k for k, v in setup.items() if not v],
            "pending_admin_actions": _pending_admin_actions(
                stage, risk_flag, pending_approvals, items
            ),
            "customer_status_notes": _customer_status_notes(stage, risk_flag, deliverables, setup),
            "monthly_summary": _monthly_summary(
                deliverables, setup_pct, deliverable_pct, failed_count, len(pending_approvals)
            ),
            "content_generated": len(items),
            "posts_waiting_for_approval": len(pending_approvals),
            "posts_scheduled": len(approved),
            "posts_published": len(published) + int(ledger.get("posts_published") or 0),
            "failed_automations": failed_count,
            "next_action": next_action,
            "owner": _owner_from_actions(actions) or "Sumit",
            "last_automation_status": _last_status(led_events, actions),
            "due_date": _due_date(client),
            "risk_flag": risk_flag,
            "health_status": health["status"],
            "health_score": health["score"],
            "health_reasons": health["reasons"],
            "sla_hours_remaining": health["sla_hours_remaining"],
            "approval_escalation": approvals_escalated,
            "stale_approvals_24h": sum(
                1 for a in approvals_escalated if a["escalation"] == "stale_24h"
            ),
            "urgent_approvals_48h": sum(
                1
                for a in approvals_escalated
                if a["escalation"] in ("urgent_48h", "admin_manual_action")
            ),
            "automation_events": _automation_events_from_sources(cid, client, led_events, actions),
        }
    except Exception as exc:
        logger.warning("customer_delivery_status failed (%s): %s", cid, exc)
        return {
            "ok": False,
            "client_id": cid,
            "deliverables": [],
            "stage": "onboarding_pending",
            "health_status": "yellow",
            "health_score": 50,
            "health_reasons": ["state_error"],
            "sla_hours_remaining": None,
            "approval_escalation": [],
            "stale_approvals_24h": 0,
            "urgent_approvals_48h": 0,
        }


def _pending_admin_actions(
    stage: str, risk: str, pending_approvals: list[dict[str, Any]], items: list[dict[str, Any]]
) -> list[str]:
    out: list[str] = []
    if risk == "automation_failed":
        out.append("Retry failed automation ya manual delivery proof add karo.")
    if stage in ("payment_received", "onboarding_pending", "setup_in_progress"):
        out.append("Customer reminder bhejo.")
    if not items:
        out.append("Missing content generate karo.")
    if pending_approvals:
        out.append("Customer approval follow-up ya admin approve-on-behalf.")
    if stage == "scheduled":
        out.append("Manual publish / proof upload.")
    if stage in ("published", "report_sent"):
        out.append("Monthly report send karo.")
    return out[:5]


def _customer_status_notes(
    stage: str,
    risk: str,
    deliverables: list[dict[str, Any]],
    setup: dict[str, bool],
) -> list[dict[str, str]]:
    notes: list[dict[str, str]] = []
    if risk == "automation_failed":
        notes.append(
            {
                "type": "manual_fallback",
                "title": "Manual delivery in progress",
                "message": "Ek delivery step automatic nahi hua, isliye team manual proof ke saath complete kar rahi hai.",
            }
        )
    if risk == "customer_blocked":
        missing = [k.replace("_", " ") for k, v in setup.items() if not v]
        notes.append(
            {
                "type": "customer_input_needed",
                "title": "Setup details pending",
                "message": "Pending details: "
                + ", ".join(missing[:4])
                + ". Ye milte hi delivery fast ho jayegi.",
            }
        )
    pending_titles = [
        str(d.get("title") or "")
        for d in deliverables
        if d.get("status") in ("pending", "in_progress")
    ]
    if pending_titles and stage not in ("published", "report_sent", "renewal_ready"):
        notes.append(
            {
                "type": "next_deliverables",
                "title": "Next deliverables",
                "message": ", ".join(pending_titles[:3]),
            }
        )
    if not notes:
        notes.append(
            {
                "type": "on_track",
                "title": "Delivery on track",
                "message": "Aapke marketing deliverables progress me hain aur proof yahin update hota rahega.",
            }
        )
    return notes[:4]


def _monthly_summary(
    deliverables: list[dict[str, Any]],
    setup_pct: int,
    deliverable_pct: int,
    failed_count: int,
    pending_approvals: int,
) -> dict[str, Any]:
    completed = [d for d in deliverables if d.get("status") == "done"]
    pending = [d for d in deliverables if d.get("status") != "done"]
    next_month = []
    if pending:
        next_month.extend(str(d.get("title") or "") for d in pending[:3])
    if pending_approvals:
        next_month.append("Pending approvals close karna")
    if failed_count:
        next_month.append("Manual publishing fallback complete karna")
    if not next_month and deliverable_pct >= 80:
        next_month.append("Renewal value recap + fresh content batch")
    return {
        "setup_completion_pct": setup_pct,
        "deliverable_completion_pct": deliverable_pct,
        "completed_count": len(completed),
        "pending_count": len(pending),
        "completed_titles": [str(d.get("title") or "") for d in completed[:8]],
        "pending_titles": [str(d.get("title") or "") for d in pending[:8]],
        "next_month_plan": next_month[:5],
    }


def _owner_from_actions(actions: list[dict[str, Any]]) -> str:
    for ev in actions:
        if ev.get("owner"):
            return str(ev.get("owner"))[:80]
    return ""


def _last_status(ledger_events: list[dict[str, Any]], actions: list[dict[str, Any]]) -> str:
    merged = []
    merged.extend(actions or [])
    merged.extend(ledger_events or [])
    merged.sort(key=lambda r: str(r.get("at") or r.get("started_at") or ""), reverse=True)
    if not merged:
        return "No delivery event yet"
    ev = merged[0]
    status = str(ev.get("status") or ev.get("event") or "success")
    label = str(
        ev.get("workflow_name")
        or ev.get("label")
        or ACTION_LABELS.get(str(ev.get("action") or ""), "Delivery update")
    )
    return f"{label}: {status}"


def _due_date(client: dict[str, Any]) -> str:
    raw = str(client.get("created_at") or "")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        dt = datetime.now(timezone.utc)
    return (dt + timedelta(days=7)).date().isoformat()


def _automation_events_from_sources(
    cid: str,
    client: dict[str, Any],
    ledger_events: list[dict[str, Any]],
    actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ev in ledger_events:
        event = str(ev.get("event") or "")
        status = "failed" if event in ("automation_failed", "post_failed") else "success"
        if event == "post_draft_created":
            status = "pending"
        if event == "post_approved":
            status = "manual_required"
        out.append(
            {
                "customer_id": cid,
                "customer_name": client.get("business_name") or "Customer",
                "workflow_id": str(ev.get("event") or "delivery"),
                "workflow_name": str(ev.get("label") or "Delivery update"),
                "trigger_source": str(ev.get("actor") or "system"),
                "status": status,
                "started_at": ev.get("at") or "",
                "completed_at": ev.get("at") or "",
                "error_message": ev.get("detail") if status == "failed" else "",
                "retry_count": 0,
                "next_retry_at": "",
                "next_action": _event_next_action(status, ev),
                "related_deliverable_id": _related_deliverable(event),
            }
        )
    for ev in actions:
        status = str(ev.get("status") or "success")
        out.append(
            {
                "customer_id": cid,
                "customer_name": client.get("business_name") or "Customer",
                "workflow_id": str(ev.get("workflow_id") or ev.get("action") or "manual"),
                "workflow_name": str(
                    ev.get("workflow_name")
                    or ACTION_LABELS.get(str(ev.get("action") or ""), "Manual action")
                ),
                "trigger_source": str(ev.get("trigger_source") or "admin"),
                "status": status,
                "started_at": ev.get("started_at") or ev.get("at") or "",
                "completed_at": ev.get("completed_at") or ev.get("at") or "",
                "error_message": ev.get("error_message") or "",
                "retry_count": int(ev.get("retry_count") or 0),
                "next_retry_at": ev.get("next_retry_at") or "",
                "next_action": ev.get("next_action") or _event_next_action(status, ev),
                "related_deliverable_id": ev.get("deliverable_id") or "",
            }
        )
    out.sort(key=lambda r: str(r.get("started_at") or r.get("completed_at") or ""), reverse=True)
    return out[:120]


def _related_deliverable(event: str) -> str:
    return {
        "marketing_calendar_generated": "social_posts",
        "post_draft_created": "social_posts",
        "post_approved": "proof",
        "post_published": "proof",
        "post_failed": "proof",
        "weekly_report_generated": "monthly_report",
        "onboarding_completed": "business_profile",
    }.get(event, "")


def _event_next_action(status: str, ev: dict[str, Any]) -> str:
    if status == "failed":
        return "Retry karo ya manual delivery task banao."
    if status == "manual_required":
        return "Admin manual upload/proof complete kare."
    if status == "pending":
        return "Customer approval ya admin review pending."
    if status == "skipped":
        return "Reason check karo; zarurat ho to manual fallback."
    return "No action needed."


def admin_customer_card(client: dict[str, Any]) -> dict[str, Any]:
    cid = str(client.get("id") or "")
    state = customer_delivery_status(cid, client)
    return {
        "id": cid,
        "customer_name": state.get("customer_name"),
        "plan": state.get("plan"),
        "product": state.get("product"),
        "current_delivery_stage": state.get("stage"),
        "stage_label": state.get("stage_label"),
        "setup_completion_pct": state.get("setup_completion_pct"),
        "deliverable_completion_pct": state.get("deliverable_completion_pct"),
        "next_action": state.get("next_action"),
        "owner": state.get("owner"),
        "last_automation_status": state.get("last_automation_status"),
        "due_date": state.get("due_date"),
        "risk_flag": state.get("risk_flag"),
        "health_status": state.get("health_status") or "green",
        "health_score": state.get("health_score") if state.get("health_score") is not None else 100,
        "health_reasons": state.get("health_reasons") or [],
        "sla_hours_remaining": state.get("sla_hours_remaining"),
        "approval_escalation": state.get("approval_escalation") or [],
        "stale_approvals_24h": state.get("stale_approvals_24h") or 0,
        "urgent_approvals_48h": state.get("urgent_approvals_48h") or 0,
        "pending_customer_inputs": state.get("pending_customer_inputs") or [],
        "pending_admin_actions": state.get("pending_admin_actions") or [],
        "content_generated": state.get("content_generated") or 0,
        "posts_waiting_for_approval": state.get("posts_waiting_for_approval") or 0,
        "posts_scheduled": state.get("posts_scheduled") or 0,
        "posts_published": state.get("posts_published") or 0,
        "failed_automations": state.get("failed_automations") or 0,
        "open_customer_workspace_url": f"/app/clients?client_id={cid}",
        "deliverables": state.get("deliverables") or [],
        # Rich health object the Delivery Cockpit frontend prefers over the flat
        # health_status/score/reasons fallback.
        "health": _admin_health(state),
    }


def _admin_health(state: dict[str, Any]) -> dict[str, Any]:
    """Translate flat health status/score/reasons into the shape the admin
    Delivery Cockpit frontend renders: state, tone, label_hi, reason,
    next_action_hint."""
    status = str(state.get("health_status") or "green").lower()
    score = int(state.get("health_score") or 100)
    reasons = list(state.get("health_reasons") or [])
    next_action = str(state.get("next_action") or "")

    label_hi = "On track"
    if status == "red":
        label_hi = "Immediate action"
    elif status == "yellow":
        label_hi = "Needs attention"
    elif status == "green":
        label_hi = "On track"

    tone = status if status in ("red", "yellow", "green") else "muted"
    reason_text = reasons[0] if reasons else ""

    if reason_text == "automation_failed":
        reason_text = "Automation fail hui — manual fallback chahiye"
    elif reason_text == "blank_timeline":
        reason_text = "Abhi koi customer-visible deliverable nahi bana"
    elif reason_text == "no_deliverable_24h":
        reason_text = "24h+ se koi delivery event nahi"
    elif reason_text == "approval_critical_stale":
        reason_text = "Approval 72h+ se pending"
    elif reason_text == "setup_incomplete":
        reason_text = "Setup details pending"
    elif reason_text == "pending_approval":
        reason_text = "Customer approval ka wait"
    elif reason_text == "approval_stale":
        reason_text = "Approval stale ho gaya"
    elif reason_text == "manual_publish_mode":
        reason_text = "Manual publish mode hai"

    if not next_action and status == "red":
        next_action = "Admin manual action lo — automation fail/block hai"
    elif not next_action and status == "yellow":
        next_action = "Customer ko follow-up karo ya approval push karo"

    return {
        "state": status,
        "tone": tone,
        "label_hi": label_hi,
        "reason": reason_text,
        "next_action_hint": next_action,
        "score": score,
        "reasons": reasons,
    }


def _cockpit_client_mrr(c: dict[str, Any]) -> int:
    """Active client monthly ₹ — lightweight, never raises."""
    try:
        status = str(c.get("status") or "").strip().lower()
        if status not in ("active", "trial"):
            return 0
        plan = str(c.get("plan") or "starter").strip().lower()
        from app.api.admin_dashboard_builders import _client_mrr

        return _client_mrr(c)
    except Exception:
        return 0


def delivery_cockpit() -> dict[str, Any]:
    try:
        from app.marketing import clients_store

        raw = clients_store.list_clients(status="active")
    except Exception:
        raw = []

    # ADR-121b: deduplicate by client id — marketing_clients.jsonl can have
    # duplicate id rows (e.g. leadgenai-self written twice) or near-duplicate
    # entries (Sharma Solar ×3 from a rapid-fire test run). First-seen wins
    # (list is newest-first from list_clients).
    seen_ids: set[str] = set()
    clients: list[dict[str, Any]] = []
    for c in raw:
        cid = str(c.get("id") or "").strip()
        if cid and cid in seen_ids:
            continue
        seen_ids.add(cid)
        clients.append(c)

    cards = [admin_customer_card(c) for c in clients]
    by_stage: dict[str, int] = dict.fromkeys(PIPELINE, 0)
    for c in cards:
        st = str(c.get("current_delivery_stage") or "")
        by_stage[st] = by_stage.get(st, 0) + 1

    # Customer Health Agent requirement: "admin dashboard must sort red customers
    # first" — worst health + lowest score first so admin understands risk in
    # the first screen, not after scrolling.
    _health_order = {"red": 0, "yellow": 1, "green": 2}
    cards.sort(
        key=lambda c: (
            _health_order.get(str(c.get("health_status") or "green"), 2),
            int(c.get("health_score") if c.get("health_score") is not None else 100),
        )
    )

    # Revenue MRR breakdown — ADR-121b: gate on _has_paid_evidence() so MRR
    # matches dashboard KPI (was: cockpit counted test/self-brand clients →
    # ₹7,997 vs KPI ₹1,999 — same _has_paid_evidence miss as ADR-101).
    mrr_total = 0
    by_plan: dict[str, dict[str, int]] = {}
    paying = 0
    try:
        from app.api.admin_dashboard_builders import _has_paid_evidence

        for c in clients:
            price = _cockpit_client_mrr(c)
            paid = _has_paid_evidence(c)
            plan_name = str(c.get("plan") or "starter").title()
            cur = by_plan.setdefault(plan_name, {"count": 0, "mrr": 0})
            cur["count"] += 1
            if paid:
                mrr_total += price
                cur["mrr"] += price
            if price > 0 and paid:
                paying += 1
    except Exception as e:
        logger.debug("delivery_cockpit revenue compute failed: %s", e)

    return {
        "ok": True,
        "generated_at": _now(),
        "pipeline": [
            {"key": k, "label": STAGE_LABELS[k], "count": by_stage.get(k, 0)} for k in PIPELINE
        ],
        "revenue": {
            "mrr_total": mrr_total,
            "paying_customers": paying,
            "by_plan": dict(
                sorted(by_plan.items(), key=lambda x: (-int(x[1].get("mrr") or 0), x[0]))
            ),
        },
        "summary": {
            "new_paid_customers": sum(
                1
                for c in cards
                if c.get("current_delivery_stage") in ("payment_received", "onboarding_pending")
            ),
            "pending_customer_inputs": sum(1 for c in cards if c.get("pending_customer_inputs")),
            "pending_admin_actions": sum(1 for c in cards if c.get("pending_admin_actions")),
            "content_generated": sum(int(c.get("content_generated") or 0) for c in cards),
            "posts_waiting_for_approval": sum(
                int(c.get("posts_waiting_for_approval") or 0) for c in cards
            ),
            "posts_scheduled": sum(int(c.get("posts_scheduled") or 0) for c in cards),
            "posts_published": sum(int(c.get("posts_published") or 0) for c in cards),
            "failed_automations": sum(int(c.get("failed_automations") or 0) for c in cards),
            "customers_at_risk": sum(1 for c in cards if c.get("risk_flag") != "ok"),
            "renewal_ready": sum(
                1 for c in cards if c.get("current_delivery_stage") == "renewal_ready"
            ),
            "red_customers": sum(1 for c in cards if c.get("health_status") == "red"),
            "yellow_customers": sum(1 for c in cards if c.get("health_status") == "yellow"),
            "green_customers": sum(1 for c in cards if c.get("health_status") == "green"),
            "stale_approvals_24h": sum(int(c.get("stale_approvals_24h") or 0) for c in cards),
            "urgent_approvals_48h": sum(int(c.get("urgent_approvals_48h") or 0) for c in cards),
        },
        "customers": cards,
        "integration_health": _safe_integration_readiness(),
        "db_audit": _safe_customer_deliverable_db_audit(cards),
        # Read-only paid-customer missed/at-risk rollup (nikhil / delivery_assurance).
        # Never mutates delivery state; cockpit stays useful even if scan fails.
        "assurance": _safe_delivery_assurance_summary(),
    }


def _safe_delivery_assurance_summary() -> dict[str, Any]:
    """Never-raise wrapper around delivery_assurance.missed_deliverables_summary."""
    try:
        from app.marketing import delivery_assurance

        return delivery_assurance.missed_deliverables_summary()
    except Exception as exc:
        return {
            "generated_at": None,
            "checked": 0,
            "missed": 0,
            "at_risk": 0,
            "customers": [],
            "error": str(exc)[:160],
        }


def _safe_customer_deliverable_db_audit(cards: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        return customer_deliverable_db_audit(cards)
    except Exception as exc:
        return {
            "ok": False,
            "checked_customers": 0,
            "checked_deliverables": 0,
            "missing_rows": 0,
            "stale_db_rows": 0,
            "ahead_db_rows": 0,
            "mismatches": [],
            "read_path_ready": False,
            "error": str(exc)[:150],
        }


def _safe_integration_readiness() -> dict[str, Any]:
    try:
        return integration_readiness()
    except Exception as exc:
        return {
            "ok": False,
            "integrations": [],
            "scheduler": {},
            "affected_customers_total": 0,
            "error": str(exc)[:150],
        }


def automation_events(filter_key: str = "", client_id: str = "") -> list[dict[str, Any]]:
    try:
        from app.marketing import clients_store

        clients = (
            [clients_store.get_client(client_id)]
            if client_id
            else clients_store.list_clients(status="active")
        )
    except Exception:
        clients = []
    rows: list[dict[str, Any]] = []
    for c in clients:
        if not c:
            continue
        state = customer_delivery_status(str(c.get("id") or ""), c)
        rows.extend(state.get("automation_events") or [])
    rows.sort(key=lambda r: str(r.get("started_at") or ""), reverse=True)
    if filter_key:
        rows = [r for r in rows if _matches_filter(r, filter_key)]
    return rows[:300]


_KNOWN_LOG_FILTERS = {
    "failed_today",
    "manual_required",
    "manual_action_required",  # alias — same meaning, used by the acceptance test/spec wording
    "customer_blocked",
    "ready_to_publish",
    "report_pending",
    "payment_received_setup_incomplete",
}


def _matches_filter(row: dict[str, Any], key: str) -> bool:
    k = str(key or "").strip().lower()
    if not k or k == "all":
        return True
    status = str(row.get("status") or "").lower()
    action = str(row.get("next_action") or "").lower()
    rid = str(row.get("related_deliverable_id") or "").lower()
    if k == "failed_today":
        return (
            status == "failed"
            and str(row.get("started_at") or "")[:10]
            == datetime.now(timezone.utc).date().isoformat()
        )
    if k in ("manual_required", "manual_action_required"):
        return status == "manual_required"
    if k == "customer_blocked":
        return "customer" in action or "connect" in action
    if k == "ready_to_publish":
        return status in ("manual_required", "success") and rid == "proof"
    if k == "report_pending":
        return rid == "monthly_report" and status != "success"
    if k == "payment_received_setup_incomplete":
        return "setup" in action or "onboarding" in str(row.get("workflow_name") or "").lower()
    # Unknown filter key: fail closed (empty results) rather than silently
    # returning every row — a typo'd filter must never look like "no filter".
    return False


async def record_manual_action(
    client_id: str,
    action: str,
    *,
    deliverable_id: str = "",
    note: str = "",
    owner: str = "",
    status: str = "success",
    workflow_id: str = "",
    workflow_name: str = "",
    trigger_source: str = "admin",
) -> dict[str, Any]:
    """Admin action endpoint backend. Calls existing systems where possible."""
    cid = str(client_id or "").strip()
    act = str(action or "").strip().lower()
    if not cid:
        return {"ok": False, "error": "client_id required"}
    started = _now()
    result: dict[str, Any] = {"ok": True}
    err = ""
    try:
        if act == "generate_content":
            from app.marketing import auto_content, clients_store

            c = clients_store.get_client(cid) or {}
            result["generated"] = await auto_content.seed_client_content(c)
            deliverable_id = deliverable_id or "social_posts"
        elif act == "approve_pending":
            from app.marketing import content_approval

            approved = 0
            for row in content_approval.pending(cid):
                out = content_approval.decide_by_id(str(row.get("id") or ""), "approve")
                if out.get("ok"):
                    approved += 1
            result["approved"] = approved
            deliverable_id = deliverable_id or "proof"
        elif act == "monthly_report":
            from app.marketing import client_report

            result["report"] = await client_report.build_report(cid, send=False)
            deliverable_id = deliverable_id or "monthly_report"
        elif act in (
            "publish_manual",
            "manual_task_done",
            "retry_failed",
            "send_reminder",
            "assign_owner",
        ):
            result["manual"] = True
            if act == "publish_manual":
                deliverable_id = deliverable_id or "proof"
        else:
            return {"ok": False, "error": "unknown action"}
    except Exception as exc:
        err = str(exc)[:300]
        status = "failed"
        result = {"ok": False, "error": err}

    rec = {
        "id": uuid.uuid4().hex[:12],
        "at": started,
        "started_at": started,
        "completed_at": _now(),
        "client_id": cid,
        "action": act,
        "workflow_id": workflow_id or act,
        "workflow_name": workflow_name or ACTION_LABELS.get(act, act.replace("_", " ").title()),
        "trigger_source": trigger_source or "admin",
        "status": status,
        "error_message": err,
        "retry_count": 1 if act == "retry_failed" else 0,
        "next_retry_at": "",
        "next_action": (
            "Check result and continue delivery."
            if status == "success"
            else "Retry again or use manual fallback."
        ),
        "deliverable_id": deliverable_id,
        "note": note[:500],
        "owner": owner[:80],
    }
    try:
        _append_event(cid, rec)
        from app.marketing import delivery_ledger

        delivery_ledger.log_event(
            cid,
            "admin_manual_action",
            detail=rec["workflow_name"],
            meta={"action": act, "deliverable_id": deliverable_id, "status": status},
        )
    except Exception:
        pass
    try:
        db_status = ""
        if status == "failed" or act == "retry_failed":
            db_status = "failed"
        elif act == "generate_content":
            db_status = "pending_approval"
        elif act == "approve_pending":
            db_status = "approved"
        elif act in ("publish_manual", "manual_task_done", "monthly_report"):
            db_status = "delivered"
        elif act in ("send_reminder", "assign_owner"):
            db_status = "waiting_customer"
        if db_status and deliverable_id:
            sync_customer_deliverable_status(
                cid,
                deliverable_id,
                db_status,
                evidence_payload={
                    "action": act,
                    "workflow_id": rec["workflow_id"],
                    "status": status,
                    "result": result,
                },
                note=note,
                owner=owner or rec["owner"],
                error_message=err,
            )
    except Exception:
        pass
    return {**result, "event": rec}


async def run_workflow(
    client_id: str,
    workflow_id: str,
    *,
    note: str = "",
    owner: str = "",
) -> dict[str, Any]:
    """Run a named Product One workflow or record a safe manual fallback.

    This is intentionally conservative: WhatsApp/email reminders are recorded as
    prepared manual tasks, not auto-sent messages.
    """
    wid = str(workflow_id or "").strip().lower()
    workflow = _WORKFLOW_BY_ID.get(wid)
    if not workflow:
        return {"ok": False, "error": "unknown workflow"}
    out = await record_manual_action(
        client_id,
        str(workflow["action"]),
        deliverable_id=str(workflow["deliverable_id"]),
        note=note or f"{workflow['name']} prepared.",
        owner=owner,
        workflow_id=str(workflow["id"]),
        workflow_name=str(workflow["name"]),
        trigger_source=str(workflow["trigger_source"]),
    )
    return {**out, "workflow": workflow}


async def run_health_and_recovery_sweep() -> dict[str, Any]:
    """Scheduled Customer Health + Approval Reminder + SLA Recovery sweep
    (team_scheduler job `product_one_health`, hourly). Combines 3 of the
    Product 1 Customer Deliverability agents into one pass over active paid
    clients because each needs the same per-client state computed once —
    running 3 separate hourly client-list scans would triple ledger/content
    reads for no behavioural benefit (council decision 2026-07-08, see
    memory/decisions.md ADR).

    Safety (never weakened): does NOT send WhatsApp/email/any customer
    message. Only (a) writes idempotent ledger events (day- or
    approval-id-keyed, so re-running every hour never duplicates) and
    (b) may trigger ONE already-existing, already-safe recovery action
    (`generate_content` via `record_manual_action`, same as an admin clicking
    "Generate content" in the cockpit) at most once per customer per day,
    only when a paid customer has zero content after the 24h SLA window.
    Never raises — every customer is isolated in its own try/except so one
    bad record can't block the rest of the sweep.
    """
    out: dict[str, Any] = {
        "ok": True,
        "checked": 0,
        "sla_breached": 0,
        "sla_recovered": 0,
        "approvals_reminded": 0,
        "recovered_content": 0,
        "errors": [],
    }
    try:
        from app.marketing import clients_store, delivery_ledger
    except Exception as exc:
        return {**out, "ok": False, "errors": [str(exc)[:200]]}

    try:
        clients = clients_store.list_clients(status="active")
    except Exception as exc:
        return {**out, "ok": False, "errors": [str(exc)[:200]]}

    today = datetime.now(timezone.utc).date().isoformat()
    for client in clients:
        cid = str(client.get("id") or "")
        if not cid or not _client_plan_paid(client):
            continue
        out["checked"] += 1
        try:
            # Pre-ledger customers (signed up before the ledger existed) must
            # not be scored on a blank timeline they never had a chance to
            # fill — reuse the existing backfill primitive (ADR-035/036),
            # do not reimplement it.
            delivery_ledger.ensure_backfilled(cid)
            state = customer_delivery_status(cid, client)
            status = state.get("health_status")
            reasons = state.get("health_reasons") or []

            if status == "red":
                if delivery_ledger.log_event(
                    cid,
                    "sla_breached",
                    detail=", ".join(reasons)[:200],
                    meta={"reasons": reasons, "health_score": state.get("health_score")},
                    actor="product_one_health",
                    key=f"sla_breach:{today}",
                ):
                    out["sla_breached"] += 1

                # SLA Recovery: only the specific, safe, already-existing
                # "no content yet" case. Approval / automation-failure reasons
                # need a human, not more auto-generation — left to admin.
                if ("blank_timeline" in reasons or "no_deliverable_24h" in reasons) and int(
                    state.get("content_generated") or 0
                ) == 0:
                    already_today = any(
                        ev.get("action") == "generate_content"
                        and str(ev.get("at") or "")[:10] == today
                        for ev in manual_events(cid, limit=50)
                    )
                    if not already_today:
                        try:
                            await record_manual_action(
                                cid,
                                "generate_content",
                                note="SLA Recovery Agent: day-1 content pack auto-generated (24h+ with none).",
                                owner="SLA Recovery Agent",
                                trigger_source="sla_recovery",
                            )
                            out["recovered_content"] += 1
                        except Exception as exc:
                            out["errors"].append(f"{cid}:recovery:{str(exc)[:120]}")
            elif status == "green":
                # Transition-based (not level-based) so a healthy customer
                # doesn't get a fresh "recovered" event every green hour —
                # only fires the hour health actually flips back from red.
                recent = delivery_ledger.timeline(cid, limit=1, customer_only=False)
                if recent and recent[0].get("event") == "sla_breached":
                    if delivery_ledger.log_event(
                        cid,
                        "sla_recovered",
                        detail="Health back to green",
                        actor="product_one_health",
                        key=f"sla_recover:{today}",
                    ):
                        out["sla_recovered"] += 1

            for a in state.get("approval_escalation") or []:
                if a.get("escalation") in (
                    "stale_24h",
                    "urgent_48h",
                    "admin_manual_action",
                ) and a.get("id"):
                    if delivery_ledger.log_event(
                        cid,
                        "approval_reminded",
                        detail=f"Approval {a['id']} open {a['hours_open']}h ({a['escalation']})",
                        meta={
                            "approval_id": a["id"],
                            "escalation": a["escalation"],
                            "hours_open": a["hours_open"],
                        },
                        actor="product_one_health",
                        key=f"appr_remind:{a['id']}:{a['escalation']}",
                    ):
                        out["approvals_reminded"] += 1
        except Exception as exc:
            out["errors"].append(f"{cid}:{str(exc)[:150]}")
            continue

    # Delivery-assurance observability (read-only, additive — 2026-07-20): emit the
    # periodic missed/at-risk heartbeat + counts so the hourly sweep leaves a
    # visible, evidence-backed trace on the team feed (owner: nikhil). Reuses the
    # delivery_assurance aggregator (canonical id + ledger evidence) — no sends, no
    # state mutation. Fully defensive: a failure here never changes the sweep's own
    # recovery result.
    try:
        from app.marketing import delivery_assurance

        _assur = delivery_assurance.scan_missed_deliverables(limit=200)
        out["assurance_missed"] = int(_assur.get("missed_count") or 0)
        out["assurance_at_risk"] = int(_assur.get("at_risk_count") or 0)
    except Exception as exc:  # pragma: no cover - defensive
        out["errors"].append(f"assurance:{str(exc)[:120]}")

    return out


# --------------------------------------------------------------------------- #
# Integration Health Agent (2026-07-08) — maps PLATFORM integration failures
# and scheduler/queue health to the SPECIFIC Product 1 paid customers they
# affect, instead of a generic "integration down" admin message. Reuses the
# existing low-level primitives (`integration_health.snapshot`, which already
# counts real failures for smtp/email_api/imap/vobiz today, and
# `automation_health.health`, which already tracks overdue jobs + Celery
# queue backlog) — this module only adds the customer-mapping layer on top,
# it does not re-implement failure counting.
# --------------------------------------------------------------------------- #
_INTEGRATION_FAIL_THRESHOLD = 3  # ignore one-off blips; only map "affecting customers" past this

# name (matches app/platform/integration_health.py KNOWN) -> (customer-safe
# reason if this ever needs to reach a customer view, admin-technical reason,
# impact scope). scope: "all_paid" | "voice_product" | "ops_only".
_INTEGRATION_IMPACT: dict[str, tuple[str, str, str]] = {
    "smtp": (
        "Aapki weekly report/email update thoda delay ho sakta hai.",
        "SMTP email delivery failing",
        "all_paid",
    ),
    "email_api": (
        "Aapki weekly report/email update thoda delay ho sakta hai.",
        "Email API failing",
        "all_paid",
    ),
    "imap": (
        "",
        "IMAP reply-triage failing (internal ops signal, not customer-facing)",
        "ops_only",
    ),
    "vobiz": (
        "Aapke voice calls me technical dikkat aa rahi hai — team dekh rahi hai.",
        "Vobiz telephony failing",
        "voice_product",
    ),
    "whatsapp": (
        "Aapka WhatsApp content draft thoda delay ho sakta hai.",
        "WhatsApp integration failing",
        "all_paid",
    ),
    "pollinations": (
        "Aapke poster/creative images thoda delay ho sakte hain.",
        "Pollinations image-gen failing",
        "all_paid",
    ),
    "qdrant": ("", "Qdrant RAG lookup failing (content quality degrade, not blocking)", "ops_only"),
    "places": ("", "Google Places prospecting failing (not a customer-delivery issue)", "ops_only"),
    "stripe": ("", "Stripe removed 2026-07-10 — payments via UPI only", "ops_only"),
}

_RECOMMENDED_FIX: dict[str, str] = {
    "smtp": "Hostinger SMTP credentials/quota check karo (.env SMTP_*).",
    "email_api": "Email API key/quota check karo.",
    "imap": "IMAP creds/connection check karo (reply-triage impact only).",
    "vobiz": "Vobiz SIP trunk/credentials check karo.",
    "whatsapp": "WhatsApp Cloud/WAHA token or QR re-connect karo.",
    "pollinations": "Pollinations API status check karo (free-tier rate-limit ho sakta).",
    "qdrant": "Qdrant container/connection check karo.",
    "places": "Google Places API key/quota check karo.",
    "stripe": "Stripe removed 2026-07-10 — payments via UPI only.",
}


def _affected_clients_for_scope(
    scope: str, paid_clients: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if scope == "voice_product":
        return [
            c for c in paid_clients if str(c.get("product") or "").lower() in ("voice", "combo")
        ]
    if scope == "all_paid":
        return list(paid_clients)
    return []  # ops_only — real signal, but not a Product 1 customer-delivery impact


def integration_readiness(hours: int = 6) -> dict[str, Any]:
    """Integration Health Agent: platform integration failures + scheduler/queue
    health → the exact Product 1 paid customers affected + a human reason +
    recommended fix. Never raises. Logs a (deduped, internal-only)
    `integration_failed` ledger event per affected customer per integration
    per day — never for `ops_only`-scoped integrations, since those don't
    actually touch customer delivery.
    """
    out: dict[str, Any] = {
        "ok": True,
        "generated_at": _now(),
        "integrations": [],
        "scheduler": {},
        "affected_customers_total": 0,
    }
    snap: dict[str, Any] = {"integrations": {}}
    try:
        from app.platform import integration_health

        snap = integration_health.snapshot(hours=hours) or snap
    except Exception as exc:
        out["errors"] = [str(exc)[:150]]

    ah: dict[str, Any] = {}
    try:
        from app.platform import automation_health

        ah = automation_health.health() or {}
    except Exception:
        ah = {}

    try:
        from app.marketing import clients_store

        paid_clients = [
            c for c in (clients_store.list_clients(status="active") or []) if _client_plan_paid(c)
        ]
    except Exception:
        paid_clients = []

    affected_ids: set[str] = set()
    today = datetime.now(timezone.utc).date().isoformat()

    for name, counts in (snap.get("integrations") or {}).items():
        try:
            fails = int(counts.get("fail") or 0)
        except Exception:
            fails = 0
        if fails < _INTEGRATION_FAIL_THRESHOLD:
            continue
        customer_reason, admin_reason, scope = _INTEGRATION_IMPACT.get(
            name, ("", f"Integration '{name}' failing", "ops_only")
        )
        affected = _affected_clients_for_scope(scope, paid_clients)
        for c in affected:
            cid = str(c.get("id") or "")
            if cid:
                affected_ids.add(cid)
                try:
                    from app.marketing import delivery_ledger

                    delivery_ledger.log_event(
                        cid,
                        "integration_failed",
                        detail=admin_reason,
                        meta={"integration": name, "fail_count": fails},
                        actor="integration_health",
                        key=f"integ_fail:{name}:{today}",
                    )
                except Exception:
                    pass
        out["integrations"].append(
            {
                "integration": name,
                "fail_count": fails,
                "fail_rate": counts.get("fail_rate"),
                "last_error": counts.get("last_error"),
                "admin_reason": admin_reason,
                "customer_reason": customer_reason,
                "scope": scope,
                "affected_customer_ids": [str(c.get("id") or "") for c in affected],
                "affected_customer_count": len(affected),
                "recommended_fix": _RECOMMENDED_FIX.get(
                    name, "Integration logs check karo (`GET /api/growth/infra/integrations`)."
                ),
            }
        )

    overdue = list(ah.get("overdue") or [])
    queue_backlogged = bool(ah.get("queue_backlogged"))
    if overdue or queue_backlogged:
        for c in paid_clients:
            cid = str(c.get("id") or "")
            if cid:
                affected_ids.add(cid)
        reason = (
            f"Content generation delayed — scheduled job(s) overdue: {', '.join(overdue[:5])}"
            if overdue
            else "Content generation delayed because the heavy worker queue isn't consuming"
        )
        out["scheduler"] = {
            "overdue_jobs": overdue,
            "queue_backlogged": queue_backlogged,
            "queue": ah.get("queue") or {},
            "admin_reason": reason,
            "affected_customer_count": len(paid_clients),
        }

    out["affected_customers_total"] = len(affected_ids)
    out["ok"] = not out["integrations"] and not (overdue or queue_backlogged)
    return out


__all__ = [
    "PIPELINE",
    "STAGE_LABELS",
    "DELIVERABLES",
    "WORKFLOWS",
    "customer_delivery_status",
    "sync_customer_deliverable_status",
    "customer_deliverable_db_audit",
    "admin_customer_card",
    "delivery_cockpit",
    "automation_events",
    "record_manual_action",
    "run_workflow",
    "manual_events",
    "run_health_and_recovery_sweep",
    "integration_readiness",
]
