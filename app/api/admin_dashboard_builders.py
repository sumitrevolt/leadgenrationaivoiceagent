"""Admin dashboard data-assembly helpers — collect live stats, build real clients/agents/
kpis/charts/health from files + DB, automation snapshot, MRR/plan-price utilities.

Extracted from app/api/admin_dashboard.py (2026-06-20 refactor). Re-exported by
admin_dashboard.py so external importers (tests / others) keep working.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timezone
from typing import Any

from app.api.admin_dashboard_models import (
    Agent,
    CallsPerDay,
    Campaign,
    Charts,
    Client,
    DashboardResponse,
    Health,
    KPIs,
    LeadsByNiche,
    RevenueCostSeries,
)

logger = logging.getLogger(__name__)

# Restored in the 2026-06-20 godfile split (was lost when extracted from
# admin_dashboard.py). Without it _read_inquiries() and _build_real() raised
# NameError (caught upstream) → the admin dashboard silently fell back to all-zeros.
_INQUIRIES_FILE = os.path.join("data", "inquiries.jsonl")


def _read_inquiries() -> list[dict]:
    """data/inquiries.jsonl rows (parse-safe; corrupt/missing → [])."""
    rows: list[dict] = []
    try:
        if not os.path.isfile(_INQUIRIES_FILE):
            return rows
        with open(_INQUIRIES_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if isinstance(rec, dict):
                        rows.append(rec)
                except Exception:
                    continue
    except Exception as e:
        logger.debug("admin_dashboard: read inquiries failed: %s", e)
    return rows


def _is_today_iso(ts: object) -> bool:
    """True if an ISO timestamp string falls on today's (UTC) date."""
    s = str(ts or "").strip()
    if not s:
        return False
    try:
        if s.endswith("Z"):
            s = s[:-1]
        dt = datetime.fromisoformat(s)
        return dt.date() == datetime.utcnow().date()
    except Exception:
        return False


def _plan_price(plan: str) -> int:
    """Marketing plan key → monthly ₹ from packages (fallback = starter price).

    include_trial=True so plan="trial" resolves to its real ₹0 price instead
    of falling through to the "unknown plan" min-nonzero-price fallback (found
    2026-07-07 building Command Center — was silently attributing ₹1,999 MRR
    to every free-trial signup in revenue-trend/revenue-analytics too)."""
    try:
        from app.marketing.packages import get_packages, get_starter_price_inr

        key = (plan or "starter").strip().lower()
        for p in get_packages(include_trial=True):
            if str(p.get("key", "")).lower() == key:
                return int(p.get("price_inr_month") or 0)
        # default to the cheapest tier price (canonical starter from packages)
        prices = [int(p.get("price_inr_month") or 0) for p in get_packages(include_trial=True)]
        return min([x for x in prices if x > 0] or [get_starter_price_inr()])
    except Exception:
        return 999


def _client_product(c: dict) -> str:
    """Resolve product lane — delegates to clients_store (single source of truth)."""
    try:
        from app.marketing.clients_store import resolve_product

        return resolve_product(c)
    except Exception:
        return "marketing"


def _has_paid_evidence(c: dict) -> bool:
    """Does an immutable invoice actually back this client? (ADR-095 helper, reused.)

    Thin seam over `customer_delivery.has_paid_evidence` so revenue aggregation and
    the dead-man alert share ONE definition of "paid" instead of drifting apart —
    drift is exactly what produced ADR-101. Fail-OPEN on error (keep the estimate;
    never make real revenue vanish because a lookup hiccuped).
    """
    try:
        from app.marketing.customer_delivery import has_paid_evidence

        return bool(has_paid_evidence(c))
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("mrr paid-evidence lookup failed (fail-open): %s", exc)
        return True


def _paid_mrr_total(clients: list[dict]) -> int:
    """Sum of monthly ₹ across clients that have real payment evidence.

    ADR-101: `estimated_mrr` used to sum every `status == "active"` client, so the
    headline number counted the synthetic `Test Biz` (plan=growth, zero invoices)
    and `leadgenai-self` (own internal tenant) as revenue — ₹8.0K reported vs ₹1,999
    real, a 4x overstatement contradicted by the Revenue Analytics panel on the SAME
    page. A plan is SELECTED at signup before money moves, so plan+status is
    eligibility, NOT payment. `has_paid_evidence()` (ADR-095) is the existing,
    invoice-backed, self-brand-excluding, fail-OPEN definition — reuse it here.
    """
    return sum(_client_mrr(c) for c in clients if _has_paid_evidence(c))


def _client_mrr(c: dict) -> int:
    """Active client monthly ₹ — product-aware (marketing / voice / combo plans).

    NOTE: this is PRICE-of-plan, not proof-of-payment. Callers aggregating revenue
    must gate on `_has_paid_evidence()` (see `_paid_mrr_total`) — ADR-101.
    """
    if str(c.get("status") or "active").strip().lower() != "active":
        return 0
    plan = str(c.get("plan") or "starter")
    prod = _client_product(c)
    try:
        if prod == "voice":
            from app.marketing.voice_packages import voice_plan_price

            p = voice_plan_price(plan)
            if p:
                return p
        if prod == "combo":
            from app.marketing.combo_packages import combo_plan_price

            p = combo_plan_price(plan)
            if p:
                return p
    except Exception:
        pass
    return _plan_price(plan)


def _clients_by_product(clients: list[dict]) -> dict[str, int]:
    """Count clients per product lane."""
    out = {"marketing": 0, "voice": 0, "combo": 0}
    for c in clients:
        key = _client_product(c)
        out[key] = out.get(key, 0) + 1
    return out


def _age_hours(created_at: object) -> float | None:
    """Hours since an ISO `created_at` (handles `Z` and `+00:00`; naive → UTC).
    Returns None when missing/unparseable — callers then SKIP age-based states
    (so command-center fixtures without created_at don't break). Never raises."""
    s = str(created_at or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
        return delta.total_seconds() / 3600.0
    except Exception:
        return None


# next_action enum (exactly one of these per customer) → Hinglish UI hint.
_NEXT_ACTION_HINTS: dict[str, str] = {
    "open_setup": "Setup kholo — onboarding poora karwao",
    "generate_campaign": "Pehla campaign generate karwao",
    "approve_content": "Pending content approve karwao",
    "investigate_failure": "Delivery ruk gayi — turant dekho",
    "none": "Sab theek — koi action nahi",
}


def delivery_health(
    client: dict[str, Any],
    summary: dict[str, Any],
    pending_approvals: int,
    recent: dict[str, Any],
) -> dict[str, Any]:
    """Compute a single delivery-health STATE for one customer. Pure + never-raises
    (any error → safe "unknown" dict).

    Precedence (first match wins) — TUNED for reachability (see below):
      1. at_risk        — active & paid & setup_done & posts_created>0 AND
                          (no value event in last 7d  OR  any failure in last 24h)
      2. not_started    — not setup_done AND zero ledger events
      3. blocked        — not setup_done AND created_at older than 24h (setup stuck)
      4. not_started    — (remaining not-setup-done: <24h / has events → still early)
      5. setup_ready    — setup_done but posts_created == 0 (first campaign pending)
      6. pending_approval — pending approvals > 0
      7. live           — posts_approved > posts_published (approved/queued, unpublished)
      8. delivered      — a value event within the last 7 days
      fallback          — "unknown" (never fires for real records)

    Two deliberate deviations from the raw spec, both to keep every state REACHABLE:
      * at_risk is scoped to `setup_done AND posts_created>0`. The literal
        "active+paid AND no-value-7d" would swallow not_started/blocked/setup_ready
        (they all lack recent value) since at_risk trumps everything below.
      * `live` uses ONLY `posts_approved > posts_published`; the spec's
        "OR value in 7d" alternative is dropped because it is identical to
        `delivered` and, checked first, would make `delivered` unreachable.
      Consequence: for a setup_done+posts>0 customer, "not at_risk" implies value
      landed in the 7d window, so `delivered` is the correct terminal state.
    """
    try:
        setup_done = bool(client.get("setup_done"))
        plan = str(client.get("plan") or "starter").strip().lower()
        status = str(client.get("status") or "active").strip().lower()
        paid = plan != "trial"
        active = status == "active"

        events_total = int(summary.get("events_total") or 0)
        posts_created = int(summary.get("posts_created") or 0)
        posts_approved = int(summary.get("posts_approved") or 0)
        posts_published = int(summary.get("posts_published") or 0)
        pending = int(pending_approvals or 0)

        value_7d = bool(recent.get("value_events_in_window"))
        failures_24h = int(recent.get("failures_24h") or 0)

        def _out(state: str, label_hi: str, reason: str, action: str, tone: str) -> dict[str, Any]:
            return {
                "state": state,
                "label_hi": label_hi,
                "reason": reason,
                "next_action": action,
                "next_action_hint": _NEXT_ACTION_HINTS.get(action, ""),
                "tone": tone,
            }

        # 1. AT RISK — established (set-up, producing) account that went quiet/broke.
        if (
            active
            and paid
            and setup_done
            and posts_created > 0
            and (not value_7d or failures_24h > 0)
        ):
            if failures_24h > 0:
                reason = f"{failures_24h} delivery failure(s) pichhle 24h me"
            else:
                reason = "7 din se koi value-event nahi (delivery ruki)"
            return _out("at_risk", "Risk pe", reason, "investigate_failure", "err")

        # 2. NOT STARTED — nothing has happened yet at all.
        if not setup_done and events_total == 0:
            return _out(
                "not_started",
                "Shuru nahi hua",
                "Abhi tak koi activity nahi — setup baaki",
                "open_setup",
                "warn",
            )

        # 3. BLOCKED — setup incomplete and it's been stuck >24h.
        age = _age_hours(client.get("created_at"))
        if not setup_done and age is not None and age > 24:
            return _out(
                "blocked", "Setup ruka", "Setup 24h+ se adhoora — investigate", "open_setup", "err"
            )

        # 4. NOT STARTED (early) — still not set up, but recent / has some events.
        if not setup_done:
            return _out(
                "not_started",
                "Shuru nahi hua",
                "Setup chal raha — abhi poora nahi hua",
                "open_setup",
                "warn",
            )

        # 5. SETUP READY — onboarded but first campaign not generated.
        if posts_created == 0:
            return _out(
                "setup_ready",
                "Campaign baaki",
                "Setup ho gaya — pehla campaign generate karo",
                "generate_campaign",
                "warn",
            )

        # 6. PENDING APPROVAL — waiting on the customer to approve drafts.
        if pending > 0:
            return _out(
                "pending_approval",
                "Approval baaki",
                f"{pending} content approval pending",
                "approve_content",
                "warn",
            )

        # 7. LIVE — approved/queued content not yet published (rollout in flight).
        if posts_approved > posts_published:
            return _out(
                "live",
                "Live chal raha",
                "Content approve/queue ho gaya — publish hone waala",
                "none",
                "ok",
            )

        # 8. DELIVERED — value landed within the last 7 days.
        if value_7d:
            return _out(
                "delivered", "Value mil rahi", "Pichhle 7 din me value deliver hui", "none", "ok"
            )

        return _out("unknown", "—", "State compute nahi ho paayi", "none", "muted")
    except Exception as e:  # pragma: no cover — defensive, never break the rollup
        logger.debug("delivery_health failed: %s", e)
        return {
            "state": "unknown",
            "label_hi": "—",
            "reason": "",
            "next_action": "none",
            "next_action_hint": "",
            "tone": "muted",
        }


def _build_command_center() -> dict[str, Any]:
    """Business-outcome front door for admin (Customer Delivery OS Phase 2) —
    total/paying/stuck-in-setup/receiving-value/failed-automation customers +
    pending approvals + revenue. Composes list_clients + delivery_ledger.summary
    + content_approval.pending + _client_mrr — deliberately NOT a new
    independent aggregator (2026-07-07 backlog flagged 3 duplicate ones
    already; this reuses, it doesn't add a 4th). Never raises."""
    from app.marketing import clients_store, content_approval, delivery_ledger, product_one_delivery

    try:
        clients = clients_store.list_clients(status="active")
    except Exception as e:
        logger.warning("command_center: list_clients failed: %s", e)
        clients = []

    # Fetched ONCE and bucketed in-memory below — per-client
    # content_approval.pending(cid) calls would be a second per-customer file
    # scan stacked on the ledger-summary scan in the loop below.
    approvals_by_client: dict[str, int] = {}
    try:
        for a in content_approval.pending():
            cid = str(a.get("client_id") or "")
            if cid:
                approvals_by_client[cid] = approvals_by_client.get(cid, 0) + 1
    except Exception as e:
        logger.debug("command_center: pending approvals failed: %s", e)

    paying = 0
    stuck_in_setup = 0
    receiving_value = 0
    failed_automation = 0
    at_risk_count = 0
    benefit_this_week = 0
    mrr_total = 0
    by_plan: dict[str, dict[str, int]] = {}
    by_product = {"marketing": 0, "voice": 0, "combo": 0}
    per_customer: list[dict[str, Any]] = []

    for c in clients:
        cid = str(c.get("id") or "")
        plan = str(c.get("plan") or "starter").strip().lower()
        # A selected plan is not a payment. Keep this Command Center rollup on
        # the same immutable invoice-backed definition as Delivery Cockpit;
        # otherwise the admin shell can show "Paying 3 / MRR ₹0" for trial or
        # synthetic tenants that have never paid.
        paid = _has_paid_evidence(c)
        if paid:
            paying += 1
        if not bool(c.get("setup_done")):
            stuck_in_setup += 1

        try:
            # Pre-ledger customers ka history backfill (idempotent, one-time per
            # customer via marker) taaki "receiving value" count sach bole.
            delivery_ledger.ensure_backfilled(cid)
            s = delivery_ledger.summary(cid)
        except Exception as e:
            logger.debug("command_center: ledger summary failed for %s: %s", cid, e)
            s = {}
        # Time-WINDOWED counts (last 7d / 24h) for delivery-health + at-risk — a
        # separate additive read (summary() is all-time only). Never raises.
        try:
            recent = delivery_ledger.recent_counts(cid)
        except Exception as e:
            logger.debug("command_center: recent_counts failed for %s: %s", cid, e)
            recent = {}
        value_delivered = bool(s.get("value_delivered"))
        # automation_failed (account/setup stuck) + post_failed (one publish
        # attempt failed) are both real "something needs attention" signals —
        # summed so a customer whose ONLY issue is a failed post still surfaces
        # here (found while wiring post_failed in the Marketing Calendar loop).
        automation_failures = int(s.get("automation_failures") or 0) + int(
            s.get("posts_failed") or 0
        )
        if value_delivered:
            receiving_value += 1
        if automation_failures > 0:
            failed_automation += 1

        # Computed delivery-health STATE (7-state, precedence-ordered) + at-risk +
        # this-week-benefit rollups. Additive — existing scalars above unchanged.
        health = delivery_health(c, s, approvals_by_client.get(cid, 0), recent)
        if health.get("state") == "at_risk":
            at_risk_count += 1
        if bool(recent.get("value_events_in_window")):
            benefit_this_week += 1  # clients are already status="active"

        mrr = _client_mrr(c) if paid else 0
        mrr_total += mrr
        bucket = by_plan.setdefault(plan, {"count": 0, "mrr": 0})
        bucket["count"] += 1
        bucket["mrr"] += mrr

        prod = _client_product(c)
        if prod in by_product:
            by_product[prod] += 1

        per_customer.append(
            {
                "id": cid,
                "business_name": c.get("business_name") or "",
                "plan": plan,
                "product": prod,
                "mrr": mrr,
                "setup_done": bool(c.get("setup_done")),
                "value_delivered": value_delivered,
                "automation_failures": automation_failures,
                "pending_approvals": approvals_by_client.get(cid, 0),
                **product_one_delivery.admin_customer_card(c),
                "health": health,
            }
        )

    return {
        "ok": True,
        "generated_at": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
        "summary": {
            "total_customers": len(clients),
            "paying_customers": paying,
            "stuck_in_setup": stuck_in_setup,
            "receiving_value": receiving_value,
            "failed_automation_count": failed_automation,
            "pending_approvals_total": sum(approvals_by_client.values()),
            "at_risk_count": at_risk_count,
            "benefit_this_week": benefit_this_week,
        },
        "revenue": {"mrr_total": mrr_total, "by_plan": by_plan},
        "by_product": by_product,
        "per_customer": per_customer,
    }


def _sync_db():
    """Sync SQLAlchemy session (admin aggregates only)."""
    try:
        from app.models import base as _b

        _b._get_sync_engine()
        if _b._SessionLocal is None:
            return None
        return _b._SessionLocal()
    except Exception:
        return None


def _emails_sent_today() -> int:
    """Sum `sent` from today's Rohan outreach/followup agent_events."""
    import json

    db = _sync_db()
    if db is None:
        return 0
    total = 0
    try:
        from app.models.agent_event import AgentEvent

        rows = (
            db.query(AgentEvent)
            .filter(
                AgentEvent.member == "rohan",
                AgentEvent.action.in_(["email_outreach_run", "email_followup"]),
            )
            .order_by(AgentEvent.created_at.desc())
            .limit(40)
            .all()
        )
        for r in rows:
            if r.created_at and not _is_today_iso(r.created_at.isoformat()):
                continue
            try:
                meta = json.loads(r.meta_json or "{}")
                total += int(meta.get("sent") or 0)
            except Exception:
                pass
    except Exception as e:
        logger.debug("admin_dashboard: emails_sent_today failed: %s", e)
    finally:
        db.close()
    return total


def _real_calls_today() -> int:
    """Completed/initiated phone calls today (call_logs table)."""
    from datetime import time

    db = _sync_db()
    if db is None:
        return 0
    try:
        from app.models.call_log import CallLog

        start = datetime.combine(datetime.utcnow().date(), time.min)
        return int(db.query(CallLog).filter(CallLog.initiated_at >= start).count() or 0)
    except Exception as e:
        logger.debug("admin_dashboard: real_calls_today failed: %s", e)
        return 0
    finally:
        db.close()


def _automation_snapshot() -> tuple[list[dict], str, dict]:
    """Job heartbeats + queue depth for admin hourly timeline."""
    try:
        from app.platform.automation_health import health
        from app.platform.today_overview import JOB_INFO

        h = health()
        jobs = list(h.get("jobs") or [])
        order = [
            "blog",
            "content",
            "digest",
            "prospect",
            "email_outreach",
            "reply_triage",
            "ops",
            "watchdog",
            "onboard",
            "growth",
            "qa",
            "trainer",
        ]

        def _sort_key(j: dict) -> tuple:
            key = str(j.get("job") or "")
            try:
                return (order.index(key), j.get("last_run") or "")
            except ValueError:
                return (99, j.get("last_run") or "")

        jobs.sort(key=_sort_key)
        timeline: list[dict] = []
        for j in jobs[:16]:
            key = str(j.get("job") or "")
            info = JOB_INFO.get(key, {})
            timeline.append(
                {
                    "job": key,
                    "label": info.get("label") or key.replace("_", " ").title(),
                    "kya": info.get("kya") or "",
                    "last_run": j.get("last_run"),
                    "status": j.get("status") or "unknown",
                    "duration_s": j.get("duration_s"),
                }
            )
        return timeline, str(h.get("status") or "unknown"), dict(h.get("queue") or {})
    except Exception as e:
        logger.debug("admin_dashboard: automation_snapshot failed: %s", e)
        return [], "unknown", {}


def _collect_live_stats() -> dict:
    """The single source of truth for REAL platform numbers. Best-effort."""
    stats: dict = {
        "total_prospects": 0,
        "prospects_by_status": {},
        "prospects_with_email": 0,
        "inquiries_total": 0,
        "inquiries_today": 0,
        "marketing_clients": 0,
        "marketing_clients_active": 0,
        "emails_sent": 0,
        "emails_sent_today": 0,
        "emails_pending": 0,
        "blog_articles": 0,
        "content_items_generated": 0,
        "agent_actions_today": 0,
        "agent_errors_today": 0,
        "active_staff": 0,
        "calls_today": 0,
        "real_calls_today": 0,
        "automation_status": "unknown",
        "celery_queue": 0,
        "dlq_count": 0,
        "job_timeline": [],
        "ops_headline": "",
        "ops_problems": [],
        "staff_snapshot": [],
        "estimated_mrr": 0,
        "clients_by_product": {"marketing": 0, "voice": 0, "combo": 0},
        "clients_active_by_product": {"marketing": 0, "voice": 0, "combo": 0},
        "mrr_by_product": {"marketing": 0, "voice": 0, "combo": 0},
    }

    # --- prospects ---
    prospects: list[dict] = []
    try:
        from app.platform import prospector

        prospects = prospector.list_prospects(limit=500)
        stats["total_prospects"] = len(prospects)
        by_status: dict[str, int] = {}
        with_email = 0
        for p in prospects:
            st = str(p.get("status") or "ready").lower()
            by_status[st] = by_status.get(st, 0) + 1
            if str(p.get("email") or "").strip():
                with_email += 1
        stats["prospects_by_status"] = by_status
        stats["prospects_with_email"] = with_email
    except Exception as e:
        logger.debug("admin_dashboard: prospects failed: %s", e)

    # --- inquiries ---
    try:
        inqs = _read_inquiries()
        stats["inquiries_total"] = len(inqs)
        stats["inquiries_today"] = sum(
            1 for r in inqs if _is_today_iso(r.get("created_at") or r.get("at") or r.get("ts"))
        )
    except Exception as e:
        logger.debug("admin_dashboard: inquiries failed: %s", e)

    # --- marketing clients ---
    clients: list[dict] = []
    try:
        from app.marketing import clients_store

        # ADR-121b: deduplicate by id — JSONL can have duplicate rows
        _seen: set[str] = set()
        for _c in clients_store.list_clients():
            _cid = str(_c.get("id") or "").strip()
            if _cid and _cid in _seen:
                continue
            _seen.add(_cid)
            clients.append(_c)
        stats["marketing_clients"] = len(clients)  # legacy key = total clients (all products)
        active = [c for c in clients if str(c.get("status") or "").lower() == "active"]
        stats["marketing_clients_active"] = len(active)
        stats["clients_by_product"] = _clients_by_product(clients)
        stats["clients_active_by_product"] = _clients_by_product(active)
        # ADR-101: revenue counts money, not intentions. Gate every lane on real
        # invoice evidence so a synthetic/self-brand tenant cannot inflate MRR
        # (was: ₹8.0K reported vs ₹1,999 real — Test Biz + leadgenai-self counted).
        mrr_by: dict[str, int] = {"marketing": 0, "voice": 0, "combo": 0}
        for c in active:
            if not _has_paid_evidence(c):
                continue
            lane = _client_product(c)
            mrr_by[lane] = mrr_by.get(lane, 0) + _client_mrr(c)
        stats["mrr_by_product"] = mrr_by
        stats["estimated_mrr"] = sum(mrr_by.values())
    except Exception as e:
        logger.debug("admin_dashboard: clients failed: %s", e)

    # --- email outreach ---
    try:
        from app.platform.auto_outreach import outreach_stats

        o = outreach_stats()
        stats["emails_sent"] = int(o.get("emailed") or 0)
        stats["emails_pending"] = int(o.get("pending") or 0)
    except Exception as e:
        logger.debug("admin_dashboard: outreach_stats failed: %s", e)

    # --- blog articles ---
    try:
        from app.marketing import seo_blog

        stats["blog_articles"] = len(seo_blog.list_articles(limit=500))
    except Exception as e:
        logger.debug("admin_dashboard: blog failed: %s", e)

    # --- content queue items (across all marketing clients) ---
    try:
        from app.marketing import auto_content

        total_items = 0
        for c in clients:
            cid = str(c.get("id") or "")
            if not cid:
                continue
            try:
                total_items += len(auto_content.list_queue(cid, limit=500))
            except Exception:
                continue
        stats["content_items_generated"] = total_items
    except Exception as e:
        logger.debug("admin_dashboard: content_queue failed: %s", e)

    # --- AI staff activity (agent_events) ---
    try:
        from app.platform.team import team_status

        ts = team_status()
        totals = ts.get("totals", {}) if isinstance(ts, dict) else {}
        stats["agent_actions_today"] = int(totals.get("actions_today") or 0)
        stats["agent_errors_today"] = int(totals.get("errors_today") or 0)
        stats["active_staff"] = int(totals.get("active_members") or 0)
    except Exception as e:
        logger.debug("admin_dashboard: team_status failed: %s", e)

    # --- today's outreach + real telephony + job timeline ---
    try:
        stats["emails_sent_today"] = _emails_sent_today()
    except Exception as e:
        logger.debug("admin_dashboard: emails_sent_today hook failed: %s", e)
    try:
        stats["real_calls_today"] = _real_calls_today()
        stats["calls_today"] = stats["real_calls_today"]
    except Exception as e:
        logger.debug("admin_dashboard: real_calls_today hook failed: %s", e)
    try:
        timeline, auto_status, queue = _automation_snapshot()
        stats["job_timeline"] = timeline
        stats["automation_status"] = auto_status
        stats["celery_queue"] = int(queue.get("celery") or 0)
        stats["dlq_count"] = int(queue.get("dlq") or 0)
    except Exception as e:
        logger.debug("admin_dashboard: automation_snapshot hook failed: %s", e)

    # --- today overview glue (Aaj kya hua — same as /app/automation) ---
    try:
        from app.platform.today_overview import build as today_build

        ov = today_build()
        stats["ops_headline"] = str(ov.get("headline") or "")
        stats["ops_problems"] = list(ov.get("problems") or [])[:6]
        stats["staff_snapshot"] = list(ov.get("staff") or [])[:12]
    except Exception as e:
        logger.debug("admin_dashboard: today_overview hook failed: %s", e)
        stats.setdefault("ops_headline", "")
        stats.setdefault("ops_problems", [])
        stats.setdefault("staff_snapshot", [])

    return stats


def _inquiry_count_for_client(c: dict) -> int:
    """Count inquiries.jsonl rows matched to this client record."""
    cid = str(c.get("id") or "").strip().lower()
    slug = str(c.get("slug") or "").strip().lower()
    biz = str(c.get("business_name") or "").strip().lower()
    phone_d = "".join(ch for ch in str(c.get("phone") or "") if ch.isdigit())[-10:]
    n = 0
    for r in _read_inquiries():
        r_slug = str(r.get("source_slug") or "").strip().lower()
        r_cid = str(r.get("client_id") or "").strip().lower()
        r_biz = str(r.get("business_name") or "").strip().lower()
        r_ph = "".join(ch for ch in str(r.get("phone") or "") if ch.isdigit())[-10:]
        if slug and r_slug == slug:
            n += 1
        elif cid and r_cid == cid:
            n += 1
        elif biz and r_biz == biz:
            n += 1
        elif phone_d and r_ph and r_ph == phone_d:
            n += 1
    return n


def _real_clients() -> list[Client]:
    """Real marketing clients → Client rows (empty list if none). No samples."""
    out: list[Client] = []
    try:
        from app.marketing import clients_store

        for c in clients_store.list_clients():
            plan = str(c.get("plan") or "starter")
            status = str(c.get("status") or "active")
            product = _client_product(c)
            mrr = _client_mrr(c)
            plan_label = plan.replace("_", " ").title()
            out.append(
                Client(
                    client_id=str(c.get("id") or ""),
                    company=str(c.get("business_name") or "Client"),
                    niche=str(c.get("niche") or "-"),
                    product=product,
                    plan=plan_label,
                    leads_delivered=_inquiry_count_for_client(c),
                    status=status,
                    mrr=mrr,
                )
            )
    except Exception as e:
        logger.debug("admin_dashboard: _real_clients failed: %s", e)
    return out


def _real_agents() -> list[Agent]:
    """Real AI staff (team.STAFF) → Agent cards with today's action counts."""
    out: list[Agent] = []
    try:
        from app.platform.team import team_status

        ts = team_status()
        members = ts.get("members", []) if isinstance(ts, dict) else []
        # working = green pulse; active (aaj kaam kiya) = scraping/blue; offline = grey idle.
        # data/scraper roles ka active = "scraping" (blue), baaki = "calling" (green-ish).
        _scraper_roles = {"dev", "rohan"}
        for m in members:
            la = m.get("last_activity") or {}
            action = str(la.get("action") or "")
            detail = str(la.get("detail") or m.get("title") or "-")[:60]
            mins = m.get("last_active_mins")
            when = ""
            if isinstance(mins, int | float):
                when = (
                    "abhi"
                    if mins < 2
                    else (f"{int(mins)}m pehle" if mins < 60 else f"{int(mins // 60)}h pehle")
                )
            line = (f"{detail} · {when}" if when else detail)[:72]
            errs = int(m.get("today_errors") or 0)
            state = str(m.get("state") or "offline")
            key = str(m.get("key") or "")
            if errs > 0:
                ui_status = "error"
            elif state == "working":
                ui_status = "scraping" if key in _scraper_roles else "calling"
            elif state == "active":
                ui_status = "scraping" if key in _scraper_roles else "calling"
            else:
                ui_status = "idle"
            out.append(
                Agent(
                    id=str(m.get("emoji") or "🤖") + " " + str(m.get("title") or "Staff"),
                    name=str(m.get("name") or "Agent"),
                    current_client=str(line or m.get("title") or "-"),
                    status=ui_status,
                    calls_made=int(m.get("today_actions") or 0),
                    leads_found=errs,
                )
            )
    except Exception as e:
        logger.debug("admin_dashboard: _real_agents failed: %s", e)
    return out


def _real_kpis(live: dict) -> KPIs:
    """Map REAL aggregates onto the KPI keys the HTML expects."""
    active_clients = int(live.get("marketing_clients_active") or 0)
    mrr = int(live.get("estimated_mrr") or 0)
    return KPIs(
        total_clients=int(live.get("marketing_clients") or 0),
        active_campaigns=active_clients,  # active clients = "running" engagements
        calls_today=int(live.get("real_calls_today") or live.get("calls_today") or 0),
        qualified_leads_month=int(live.get("inquiries_total") or 0),
        revenue_month=mrr,
        telephony_cost_month=0,
        net_margin_pct=100.0 if mrr else 0.0,
    )


def _real_charts(live: dict) -> Charts:
    """Charts from real data; empty-but-valid when there's nothing yet."""
    by_status = live.get("prospects_by_status") or {}
    if by_status:
        items = sorted(by_status.items(), key=lambda kv: kv[1], reverse=True)
        niche_labels = [k.title() for k, _ in items]
        niche_values = [int(v) for _, v in items]
    else:
        niche_labels, niche_values = ["No data"], [0]

    # "Pipeline" snapshot bars: prospects / inquiries / clients / emails / blog
    rev_labels = ["Prospects", "Inquiries", "Clients", "Emails", "Blog"]
    rev_revenue = [
        int(live.get("total_prospects") or 0),
        int(live.get("inquiries_total") or 0),
        int(live.get("marketing_clients") or 0),
        int(live.get("emails_sent") or 0),
        int(live.get("blog_articles") or 0),
    ]
    rev_cost = [0, 0, 0, int(live.get("emails_pending") or 0), 0]

    return Charts(
        revenue_cost=RevenueCostSeries(labels=rev_labels, revenue=rev_revenue, cost=rev_cost),
        leads_by_niche=LeadsByNiche(labels=niche_labels, values=niche_values),
        calls_per_day=CallsPerDay(
            labels=["Staff actions", "Phone calls", "Emails aaj", "Active staff"],
            values=[
                int(live.get("agent_actions_today") or 0),
                int(live.get("real_calls_today") or live.get("calls_today") or 0),
                int(live.get("emails_sent_today") or 0),
                int(live.get("active_staff") or 0),
            ],
        ),
    )


def _build_real() -> DashboardResponse:
    """Build the dashboard ENTIRELY from real platform data. Never raises."""
    live = _collect_live_stats()
    now = datetime.utcnow()
    live["generated_at"] = now.replace(tzinfo=timezone.utc).isoformat()
    return DashboardResponse(
        is_sample_data=False,
        generated_at=now.replace(tzinfo=timezone.utc).isoformat(),
        kpis=_real_kpis(live),
        clients=_real_clients(),
        agents=_real_agents(),
        campaigns=[],  # no fake campaigns — real campaigns wired when DB has them
        health=_real_health(),
        charts=_real_charts(live),
        live=live,
    )


def _real_health() -> Health:
    """Real-ish health: API up, DB checked, telephony/scrapers by config."""
    db_ok = "up"
    try:
        from app.models import base as _b

        _b._get_sync_engine()
        db_ok = "up" if _b._SessionLocal is not None else "down"
    except Exception:
        db_ok = "down"
    telephony = "down"
    scrapers = "up"  # OSM Overpass always available (no key needed)
    try:
        from app.config import settings

        if (getattr(settings, "vobiz_auth_id", "") or "") or (
            getattr(settings, "VOBIZ_AUTH_ID", "") or ""
        ):
            telephony = "up"
        if getattr(settings, "google_maps_api_key", "") or getattr(
            settings, "GOOGLE_MAPS_API_KEY", ""
        ):
            scrapers = "up"
    except Exception:
        pass
    return Health(api="up", db=db_ok, telephony=telephony, scrapers=scrapers)


# ----------------------------------------------------------------------------
# (Removed) Hardcoded SAMPLE builders — the dashboard now serves REAL data only.
# The SunVolt/Prestige/etc. fake clients, fake agents, fake campaigns and fake
# charts have been deleted on purpose. See _build_real() above for the live
# pipeline. _build_from_db() below is kept for DB-backed deployments (real).
# ----------------------------------------------------------------------------


# ----------------------------------------------------------------------------
# DB-backed builder (real data). Import-safe: DB imports are local + guarded so
# this module still mounts when DB deps/connection are missing.
# ----------------------------------------------------------------------------
def _build_from_db() -> DashboardResponse | None:
    """
    Aggregate the admin dashboard from the real relational DB (clients /
    campaigns / agents / calls / billing tables). Returns None when the DB is
    unavailable OR has no clients — the caller then serves the file-based REAL
    aggregates instead (never sample data).
    """
    try:
        from collections import defaultdict

        from app.models.agent import Agent as AgentModel
        from app.models.base import get_db_session
        from app.models.billing_record import BillingRecord, BillingRecordType
        from app.models.call_log import CallLog as CallLogModel
        from app.models.campaign import Campaign as CampaignModel
        from app.models.client import Client as ClientModel
        from app.models.lead import Lead as LeadModel
        from app.models.lead import LeadStatus
    except Exception as e:
        logger.warning("admin_dashboard: DB models unavailable, using sample (%s)", e)
        return None

    try:
        with get_db_session() as db:
            client_rows = db.query(ClientModel).all()
            if not client_rows:
                return None

            campaign_rows = db.query(CampaignModel).all()
            agent_rows = db.query(AgentModel).all()

            now = datetime.utcnow()
            today = now.date()

            # ----- clients panel + MRR -----
            # Lead counts in ONE GROUP BY (was N+1: a COUNT per client saturated the
            # small sync pool at scale — DL-001 council fix 2026-06-26).
            from sqlalchemy import func as _sqlfunc

            _lead_counts = dict(
                db.query(LeadModel.assigned_to, _sqlfunc.count(LeadModel.id))
                .group_by(LeadModel.assigned_to)
                .all()
            )
            clients: list[Client] = []
            total_mrr = 0
            for c in client_rows:
                leads_delivered = int(_lead_counts.get(c.id, 0))
                mrr = int((c.monthly_amount or 0) / 100)
                total_mrr += mrr if (c.status and c.status.value == "active") else 0
                clients.append(
                    Client(
                        client_id=str(c.id or ""),
                        company=c.business_name or "Unknown",
                        niche=c.industry or "-",
                        plan=(c.plan.value.title() if c.plan else "Starter"),
                        leads_delivered=leads_delivered,
                        status=(c.status.value if c.status else "active"),
                        mrr=mrr,
                    )
                )

            # ----- agents panel -----
            agents: list[Agent] = []
            for a in agent_rows:
                agents.append(
                    Agent(
                        id=a.agent_code or str(a.id)[:8],
                        name=a.name or "Agent",
                        current_client=a.current_client_name or "-",
                        status=(a.status.value if a.status else "idle"),
                        calls_made=a.calls_made or 0,
                        leads_found=a.leads_found or 0,
                    )
                )

            # ----- campaigns panel -----
            campaigns: list[Campaign] = []
            active_campaigns = 0
            for cp in campaign_rows:
                st = cp.status.value if cp.status else "draft"
                if st in ("running", "scheduled"):
                    active_campaigns += 1
                ui_status = "active" if st == "running" else st
                campaigns.append(
                    Campaign(
                        campaign=cp.name or "Campaign",
                        client=cp.client_name or "-",
                        niche=cp.niche or "-",
                        sources=[],
                        calls_done=cp.leads_called or 0,
                        calls_target=cp.target_lead_count or 0,
                        leads=cp.leads_qualified or 0,
                        status=ui_status,
                    )
                )

            # ----- KPIs -----
            calls_today = (
                db.query(CallLogModel)
                .filter(CallLogModel.initiated_at >= datetime(today.year, today.month, today.day))
                .count()
            )
            qualified_month = (
                db.query(LeadModel)
                .filter(
                    LeadModel.created_at >= datetime(now.year, now.month, 1),
                    LeadModel.status.in_(
                        [LeadStatus.QUALIFIED, LeadStatus.APPOINTMENT, LeadStatus.CONVERTED]
                    ),
                )
                .count()
            )

            # revenue + telephony cost this month (from billing records, in paise)
            br = (
                db.query(BillingRecord)
                .filter(
                    BillingRecord.period_year == now.year,
                    BillingRecord.period_month == now.month,
                )
                .all()
            )
            revenue_month = sum(
                (r.amount or 0) for r in br if r.record_type != BillingRecordType.TELEPHONY
            )
            telephony_cost_month = sum((r.cost or 0) for r in br) + sum(
                (c.call_cost or 0)
                for c in db.query(CallLogModel)
                .filter(CallLogModel.initiated_at >= datetime(now.year, now.month, 1))
                .all()
            )
            revenue_inr = int(revenue_month / 100) or total_mrr
            cost_inr = int(telephony_cost_month / 100)
            net_margin = (
                round(((revenue_inr - cost_inr) / revenue_inr) * 100, 1) if revenue_inr else 0.0
            )

            kpis = KPIs(
                total_clients=len(client_rows),
                active_campaigns=active_campaigns,
                calls_today=calls_today,
                qualified_leads_month=qualified_month,
                revenue_month=revenue_inr,
                telephony_cost_month=cost_inr,
                net_margin_pct=net_margin,
            )

            # ----- charts -----
            # leads by niche
            niche_counts: dict = defaultdict(int)
            for l in db.query(LeadModel).all():
                niche_counts[(l.niche or "Other").title()] += 1
            niche_items = sorted(niche_counts.items(), key=lambda kv: kv[1], reverse=True)
            leads_by_niche = LeadsByNiche(
                labels=[k for k, _ in niche_items] or ["Other"],
                values=[v for _, v in niche_items] or [0],
            )

            # calls per day (last 7 days)
            from datetime import timedelta

            day_labels, day_values = [], []
            for i in range(6, -1, -1):
                d = today - timedelta(days=i)
                start = datetime(d.year, d.month, d.day)
                end = start + timedelta(days=1)
                cnt = (
                    db.query(CallLogModel)
                    .filter(
                        CallLogModel.initiated_at >= start,
                        CallLogModel.initiated_at < end,
                    )
                    .count()
                )
                day_labels.append(d.strftime("%a"))
                day_values.append(cnt)
            calls_per_day = CallsPerDay(labels=day_labels, values=day_values)

            # revenue vs cost by month (last 6 months from billing records)
            rc_labels, rc_rev, rc_cost = [], [], []
            for i in range(5, -1, -1):
                m = now.month - i
                y = now.year
                while m <= 0:
                    m += 12
                    y -= 1
                month_br = list(
                    db.query(BillingRecord)
                    .filter(
                        BillingRecord.period_year == y,
                        BillingRecord.period_month == m,
                    )
                    .all()
                )
                rev = int(
                    sum(
                        (r.amount or 0)
                        for r in month_br
                        if r.record_type != BillingRecordType.TELEPHONY
                    )
                    / 100
                )
                cst = int(sum((r.cost or 0) for r in month_br) / 100)
                rc_labels.append(datetime(y, m, 1).strftime("%b"))
                rc_rev.append(rev)
                rc_cost.append(cst)
            revenue_cost = RevenueCostSeries(labels=rc_labels, revenue=rc_rev, cost=rc_cost)

            charts = Charts(
                revenue_cost=revenue_cost,
                leads_by_niche=leads_by_niche,
                calls_per_day=calls_per_day,
            )

            health = Health(api="up", db="up", telephony="up", scrapers="up")

            return DashboardResponse(
                is_sample_data=False,
                generated_at=now.isoformat() + "Z",
                kpis=kpis,
                clients=clients,
                agents=agents,
                campaigns=campaigns,
                health=health,
                charts=charts,
            )
    except Exception as e:
        logger.warning("admin_dashboard: DB query failed, using file aggregates (%s)", e)
        return None
