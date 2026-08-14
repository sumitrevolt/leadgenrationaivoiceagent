"""Billing / Entitlement Assurance — read-only entitlement-drift detection (GREEN lane).

WHY (2026-07-20, Agent-OS assurance slice — Revenue Ops / Nikhil domain): the
billing primitives all exist (``gst_invoice`` immutable Rule-46 ledger,
``packages`` public-pricing truth, ``clients_store`` tenant records, the
``subscription`` plan catalog) but nobody composes them into the one question
Revenue Ops actually needs answered: *"which paying tenants have an
entitlement that their billing record does NOT back up — and where's the proof?"*
A plan is SELECTED at signup BEFORE any money moves (that is exactly how a
never-invoiced "Test Biz" once masqueraded as a paying customer), so plan name
alone is not payment proof. This module cross-checks plan ↔ invoice ↔
subscription state and surfaces the mismatches — WITHOUT ever touching money.

This mirrors ``app/marketing/delivery_assurance.py`` (same shape, same safety
contract) but for the highest-sensitivity domain: billing.

SAFETY CONTRACT (enforced by tests):
  - PURE READ + BILLING-SAFE. Calls ONLY read functions
    (``gst_invoice._read``, ``clients_store.list_clients``,
    ``packages.get_public_packages``, ``subscription.PRICING_PLANS``,
    ``customer_delivery.is_paid_client`` / ``is_delivered``). NEVER creates or
    voids an invoice, NEVER changes a subscription/plan/status, NEVER sends
    anything, NEVER mutates a client record. Detection only.
  - TENANT-SAFE. Every id is normalised through
    ``clients_store.canonical_client_id`` (resolves the billing/login alias ->
    marketing id, e.g. d79d690f61b3 -> jiya-makeover) so an invoice under a
    legacy/recreated billing id still credits the right tenant and a customer is
    never mis-attributed or double-counted.
  - NEVER RAISES. Every client is best-effort; one bad record cannot sink the
    scan. Any failure degrades to a shaped result (``status='error'``).
  - VOICE-FREE. Imports no telephony / STT / TTS / call-runtime module; strictly
    billing + marketing-domain (out of scope: the voice calling stack).

OBSERVABILITY: a scan emits ONE ``team.log_event`` under ``nikhil`` (Revenue Ops)
— a paid tenant with no invoice / an entitlement drift is a revenue-leak or
compliance risk, which is nikhil's lane — so the run is visible on the existing
team activity feed with a real owner (no new persona invented). Escalation
target for a flagged item is the owner (human).

Lane: GREEN (read-only detection + report). Autonomy: L0/L1 (observe + recommend).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Observability owner for entitlement-assurance runs. Revenue Ops owns "paid
# tenant not backed by billing evidence = revenue leak / entitlement drift".
# Kept as a module constant so the attribution is explicit and testable (NOT a
# new persona — one of the existing roster).
_OWNER_MEMBER = "nikhil"

# Plan values that are NOT a real paid plan (mirrors
# customer_delivery._PAID_PLACEHOLDER_PLANS — single behaviour, no drift).
_PLACEHOLDER_PLANS = frozenset({"", "free", "trial", "none", "pending"})

# Statuses where being non-active is EXPECTED (intentional churn) — a historical
# invoice on such a tenant is normal, so it is NOT flagged as a mismatch.
_TERMINAL_STATUSES = frozenset({"cancelled", "canceled", "churned", "dead", "deleted", "expired"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _canonical_id(cid: str) -> str:
    """Normalise any id/alias to the marketing client id. Never raises."""
    try:
        from app.marketing import clients_store

        return str(clients_store.canonical_client_id(cid) or cid or "").strip()
    except Exception:
        return str(cid or "").strip()


def _billing_clients() -> list[dict[str, Any]]:
    """All tenant records (every status — inactive-with-invoice mismatch needs
    non-active tenants too). Read-only. Never raises."""
    try:
        from app.marketing import clients_store

        return list(clients_store.list_clients())
    except Exception as exc:
        logger.warning("entitlement_assurance _billing_clients err: %s", exc)
        return []


def _invoice_index(rows: list[dict[str, Any]] | None = None) -> dict[str, list[dict[str, Any]]]:
    """Build ``client-id -> live (non-void) invoice rows`` from the immutable
    Rule-46 ledger. Keyed by BOTH the raw invoice ``client_id`` and its canonical
    marketing id, so an invoice under a legacy/recreated billing id still resolves
    to the tenant. Voided invoices are excluded (append-only ``kind:"void"``
    markers). Pure READ (``gst_invoice._read``). Never raises."""
    idx: dict[str, list[dict[str, Any]]] = {}
    try:
        if rows is None:
            from app.billing import gst_invoice

            rows = gst_invoice._read()
        rows = rows or []
        voided = {
            str(r.get("voids")).strip()
            for r in rows
            if isinstance(r, dict) and r.get("kind") == "void" and r.get("voids")
        }
        for r in rows:
            if not isinstance(r, dict) or r.get("kind") == "void":
                continue
            num = str(r.get("number") or "").strip()
            if num and num in voided:
                continue  # voided invoice — number consumed but excluded from truth
            raw = str(r.get("client_id") or "").strip()
            if not raw:
                continue
            keys = {raw}
            canon = _canonical_id(raw)
            if canon:
                keys.add(canon)
            for k in keys:
                idx.setdefault(k, []).append(r)
    except Exception as exc:
        logger.warning("entitlement_assurance _invoice_index err: %s", exc)
    return idx


def _identity_ids(client: dict[str, Any], cid: str) -> set[str]:
    """All ids that legitimately belong to this tenant (canonical + own +
    billing aliases, each canonicalised). Used to match invoices tenant-safely."""
    ids: set[str] = {cid, str((client or {}).get("id") or "").strip()}
    for a in (client or {}).get("billing_client_ids") or []:
        s = str(a or "").strip()
        if s:
            ids.add(s)
            c = _canonical_id(s)
            if c:
                ids.add(c)
    ids.discard("")
    return ids


def _client_invoices(
    client: dict[str, Any], cid: str, idx: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Live invoices belonging to this tenant identity (de-duped by number)."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in _identity_ids(client, cid):
        for r in idx.get(key, []):
            marker = str(r.get("number") or "") or str(id(r))
            if marker in seen:
                continue
            seen.add(marker)
            out.append(r)
    return out


def _compact_invoice(inv: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": (inv or {}).get("number"),
        "date": (inv or {}).get("date"),
        "gross_inr": (inv or {}).get("gross_inr"),
        "plan": (inv or {}).get("plan"),
    }


def _plan_catalog() -> dict[str, dict[str, Any]]:
    """Merged plan catalog: ``plan_key -> {price_inr, has_features, source}``.

    Sources (read-only, defensive): ``packages`` public pricing (truth) +
    ``packages`` full list (legacy/hidden Growth) + ``subscription.PRICING_PLANS``
    (voice/combo/data plan ids). Used to decide plan-known and whether a plan
    actually carries entitlement features. Never raises — partial catalog on any
    source failure."""
    cat: dict[str, dict[str, Any]] = {}
    try:
        from app.marketing import packages

        for getter, src in (
            (getattr(packages, "get_public_packages", None), "packages_public"),
            (getattr(packages, "get_packages", None), "packages_all"),
        ):
            if not callable(getter):
                continue
            try:
                for p in getter() or []:
                    key = str((p or {}).get("key") or "").strip().lower()
                    if not key or key in cat:
                        continue
                    cat[key] = {
                        "price_inr": (p or {}).get("price_inr_month"),
                        "has_features": bool(
                            (p or {}).get("features") or (p or {}).get("feature_groups")
                        ),
                        "source": src,
                    }
            except Exception as exc:
                logger.debug("entitlement_assurance packages catalog skip (%s): %s", src, exc)
    except Exception as exc:
        logger.debug("entitlement_assurance packages import skip: %s", exc)

    try:
        from app.billing import subscription

        plans = getattr(subscription, "PRICING_PLANS", {}) or {}
        for key, plan in plans.items():
            k = str(key or "").strip().lower()
            if not k or k in cat:
                continue
            price = getattr(plan, "monthly_price", None)
            try:
                price_val = float(price) if price is not None else None
            except Exception:
                price_val = None
            cat[k] = {
                "price_inr": price_val,
                "has_features": bool(getattr(plan, "features", None)),
                "source": "subscription",
            }
    except Exception as exc:
        logger.debug("entitlement_assurance subscription catalog skip: %s", exc)
    return cat


def assess_client_entitlement(
    client: dict[str, Any],
    invoice_index: dict[str, list[dict[str, Any]]] | None = None,
    catalog: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Structured, tenant-safe, evidence-backed entitlement assessment for ONE
    tenant. Pure READ. Never raises — returns a shaped record even on partial
    failure (so one bad tenant can't break the aggregate scan).

    Detects (read-only):
      - ``paid_no_invoice``      : active paid plan, ZERO live invoice evidence.
      - ``invoice_subscription_mismatch`` : has invoice(s) but subscription is
        non-active (and not intentionally churned).
      - ``unknown_plan``         : active paid plan not present in the plan catalog.
      - ``entitlement_drift``    : active paid plan whose features are NOT reflected
        in delivered state (reuses ``customer_delivery.is_delivered``).
    """
    if invoice_index is None:
        invoice_index = _invoice_index()
    if catalog is None:
        catalog = _plan_catalog()

    raw_id = str((client or {}).get("id") or "").strip()
    cid = _canonical_id(raw_id) or raw_id
    plan = str((client or {}).get("plan") or "").strip().lower()
    status = str((client or {}).get("status") or "").strip().lower()

    rec: dict[str, Any] = {
        "canonical_id": cid,
        "raw_id": raw_id,
        "billing_ids": list((client or {}).get("billing_client_ids") or []),
        "business_name": (client or {}).get("business_name"),
        "plan": plan,
        "status": status,
        "has_invoice": False,
        "invoice_count": 0,
        "last_invoice": None,
        "plan_known": False,
        "plan_priced_inr": None,
        "delivered": False,
        "paid_no_invoice": False,
        "invoice_subscription_mismatch": False,
        "unknown_plan": False,
        "entitlement_drift": False,
        "flagged": False,
        "severity": "ok",
        "reasons": [],
        "escalation": "owner",
    }
    reasons: list[str] = []

    # invoice evidence (immutable Rule-46 ledger, canonicalised) — read-only
    try:
        invoices = _client_invoices(client, cid, invoice_index)
        rec["has_invoice"] = bool(invoices)
        rec["invoice_count"] = len(invoices)
        if invoices:
            rec["last_invoice"] = _compact_invoice(invoices[-1])
    except Exception as exc:
        logger.debug("entitlement_assurance invoice-match skip (%s): %s", cid, exc)

    # plan catalog lookup (known? priced? carries entitlement features?)
    meta = catalog.get(plan) if plan else None
    rec["plan_known"] = meta is not None
    if meta:
        rec["plan_priced_inr"] = meta.get("price_inr")
    plan_has_features = bool(meta and meta.get("has_features"))

    # eligibility + delivered read signal (pure functions — no I/O, no mutation)
    is_active = status == "active"
    is_paid_plan = bool(plan) and plan not in _PLACEHOLDER_PLANS
    active_paid = is_active and is_paid_plan
    try:
        from app.marketing import customer_delivery

        rec["delivered"] = bool(customer_delivery.is_delivered(client))
        # is_paid_client also excludes the self-brand record + placeholder plans
        active_paid = bool(customer_delivery.is_paid_client(client))
    except Exception as exc:
        logger.debug("entitlement_assurance signal skip (%s): %s", cid, exc)

    # --- detection (read-only) --- #
    if active_paid and not rec["has_invoice"]:
        rec["paid_no_invoice"] = True
        reasons.append("paid_no_invoice")
    if rec["has_invoice"] and not is_active and status not in _TERMINAL_STATUSES:
        rec["invoice_subscription_mismatch"] = True
        reasons.append(f"invoice_without_active_subscription:{status or 'unknown'}")
    if active_paid and not rec["plan_known"]:
        rec["unknown_plan"] = True
        reasons.append(f"unknown_plan:{plan}")
    if active_paid and rec["plan_known"] and plan_has_features and not rec["delivered"]:
        rec["entitlement_drift"] = True
        reasons.append("entitlement_features_not_delivered")

    # de-dup reasons, keep order
    seen: set[str] = set()
    rec["reasons"] = [r for r in reasons if not (r in seen or seen.add(r))]
    rec["flagged"] = bool(rec["reasons"])
    if rec["paid_no_invoice"]:
        rec["severity"] = "critical"
    elif rec["flagged"]:
        rec["severity"] = "at_risk"
    return rec


def _sample(rec: dict[str, Any]) -> dict[str, Any]:
    """Compact admin-readable view of a flagged tenant (for issue samples)."""
    return {
        "id": rec["canonical_id"],
        "name": rec["business_name"],
        "plan": rec["plan"],
        "status": rec["status"],
        "has_invoice": rec["has_invoice"],
        "invoice_count": rec["invoice_count"],
        "severity": rec["severity"],
        "reasons": rec["reasons"][:4],
    }


def scan_entitlements(limit: int = 200) -> dict[str, Any]:
    """READ-ONLY aggregator: the structured, tenant-safe, evidence-backed list of
    billing/entitlement mismatches, grouped by issue type. AgentRunResult-shaped.

    NO billing mutation, NO invoice writes, NO subscription changes, NO sends.
    Emits one observability event (nikhil). Never raises — returns a shaped
    record with ``status='error'`` + error string on failure.
    """
    run_id = str(uuid.uuid4())
    started = _now()
    result: dict[str, Any] = {
        "run_id": run_id,
        "agent_id": "entitlement_assurance",
        "domain": "billing",
        "lane": "GREEN",
        "status": "success",
        "started_at": _iso(started),
        "completed_at": None,
        "latency_ms": 0,
        "checked": 0,
        "issues": [],
        "counts": {},
        "error": None,
    }
    buckets: dict[str, list[dict[str, Any]]] = {
        "paid_no_invoice": [],
        "invoice_without_active_subscription": [],
        "unknown_plan": [],
        "entitlement_drift": [],
    }
    try:
        clients = _billing_clients()
        idx = _invoice_index()
        catalog = _plan_catalog()
        checked = 0
        flagged_ids: set[str] = set()
        for c in clients[: max(1, int(limit))]:
            rec = assess_client_entitlement(c, idx, catalog)
            checked += 1
            if rec["paid_no_invoice"]:
                buckets["paid_no_invoice"].append(_sample(rec))
            if rec["invoice_subscription_mismatch"]:
                buckets["invoice_without_active_subscription"].append(_sample(rec))
            if rec["unknown_plan"]:
                buckets["unknown_plan"].append(_sample(rec))
            if rec["entitlement_drift"]:
                buckets["entitlement_drift"].append(_sample(rec))
            if rec["flagged"]:
                flagged_ids.add(rec["canonical_id"])
        result["checked"] = checked
        issues: list[dict[str, Any]] = [
            {"type": t, "count": len(lst), "sample": lst[:5]} for t, lst in buckets.items() if lst
        ]
        # critical (paid-no-invoice) first, then by count desc
        issues.sort(key=lambda i: (0 if i["type"] == "paid_no_invoice" else 1, -i["count"]))
        result["issues"] = issues
        result["counts"] = {
            "checked": checked,
            "flagged": len(flagged_ids),
            "paid_no_invoice": len(buckets["paid_no_invoice"]),
            "invoice_without_active_subscription": len(
                buckets["invoice_without_active_subscription"]
            ),
            "unknown_plan": len(buckets["unknown_plan"]),
            "entitlement_drift": len(buckets["entitlement_drift"]),
        }
    except Exception as exc:
        logger.warning("entitlement_assurance scan err: %s", exc)
        result["status"] = "error"
        result["error"] = str(exc)

    completed = _now()
    result["completed_at"] = _iso(completed)
    result["latency_ms"] = int((completed - started).total_seconds() * 1000)

    # observability — one team event under the revenue-ops owner (no new persona)
    try:
        from app.platform import team

        status = "ok" if result["status"] == "success" else "error"
        flagged = int(result.get("counts", {}).get("flagged", 0) or 0)
        if flagged:
            status = "warn"
        detail = (
            f"entitlement assurance: {len(buckets['paid_no_invoice'])} paid-no-invoice / "
            f"{flagged} flagged of {result['checked']} tenants"
        )
        team.log_event(
            _OWNER_MEMBER,
            "entitlement_scan",
            detail[:160],
            status=status,
            meta={
                "run_id": run_id,
                "flagged": flagged,
                "paid_no_invoice": len(buckets["paid_no_invoice"]),
                "checked": result["checked"],
            },
        )
    except Exception as exc:
        logger.debug("entitlement_assurance observability skip: %s", exc)

    return result


def entitlement_summary() -> dict[str, Any]:
    """Compact admin-readable summary (counts + issue-type rollup). Read-only."""
    scan = scan_entitlements()
    return {
        "generated_at": scan["completed_at"],
        "checked": scan["checked"],
        "status": scan["status"],
        "error": scan.get("error"),
        "counts": scan.get("counts", {}),
        "issues": [{"type": i["type"], "count": i["count"]} for i in scan.get("issues", [])],
    }


__all__ = [
    "assess_client_entitlement",
    "scan_entitlements",
    "entitlement_summary",
]
