"""Quarantine seeded fixture tenants that are still `active` in production.

`scripts/seed_demo_data.py` creates 10 Postgres `clients` with
`contact{i}@{company}.example.com` and `status = ACTIVE if i % 4 else
choice(ACTIVE, PAUSED)` — which is exactly the 7-active / 3-paused split found in
production on 2026-08-06. It has no teardown; its own `--force` is a blanket
`delete()` across CallLog/Lead/BillingRecord/Campaign/Agent/Client that would
take real data with it. `scripts/setup_smoke.py` does the same to the JSONL store
via `clients_store.add_client("Sharma Solar", ...)` against the real file.

Ongoing harm while they stay active:
  * `app/tasks/reporting.py:100` collects `Client.status == ACTIVE` as scheduled
    report recipients — the fixture `@example.com` addresses are in that list.
    (`admin_dashboard.py` and `approval_notifier.py` both blocklist
    `@example.com` defensively; `reporting.py` does not.)
  * MRR rollups keyed on active status count their fake `monthly_amount`
    (up to 3_500_000) against a real MRR of ₹1,999.

WHY `cancelled` AND NOT `inactive` OR `paused`
----------------------------------------------
The two stores have different, non-overlapping status vocabularies:

  Postgres  `ClientStatus` enum -> trial | active | paused | cancelled | expired
            (`native_enum=False` + `values_callable`, so an unknown string
            raises `LookupError` at flush)
  JSONL     free-form str, no validation at all (`clients_store.set_status`)

`inactive` is the worst of both: illegal in Postgres, and unrecognised by
`entitlement_assurance._TERMINAL_STATUSES`, so every invoiced tenant flipped to
it raises `invoice_without_active_subscription`. `paused` — what the existing
admin UI toggle writes — is legal in Postgres but *also* non-terminal, so it
raises the same finding. Each fixture carries 12 seeded `billing_records`, so
this is not hypothetical.

`cancelled` is the only value that is a legal Postgres enum member AND in
`_TERMINAL_STATUSES`. It also clears the finding for the 3 fixtures already
sitting on `paused`.

SAFETY
------
Read-only by default (`dry_run=True`), gated behind `TENANT_QUARANTINE` (OFF),
bounded, CSV backup written before any mutation with abort-on-backup-failure,
and idempotent. **Never deletes anything** — no client row, and explicitly no
`invoices` / `subscriptions` / `billing_records` / `call_logs`, which stay as
the audit trail. A status flip changes no row identity, so no FK is affected.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# RFC 2606 reserved domains. Matched on the DOMAIN, not as a substring of the
# whole address: the seeded emails are `contact{i}@{company}.example.com`, so a
# naive `"@example.com" in email` check is False for every single one of them —
# the `@` sits before `perfect`, not before `example.com`. That bug would have
# made this whole module a silent no-op (0 candidates, looks safe, does nothing).
#
# NOTE: `app/api/admin_dashboard.py:1139` and `app/platform/approval_notifier.py:160`
# both guard with `to.endswith("@example.com")`, which has exactly this flaw and
# therefore does NOT block the seeded fixture addresses. Out of scope here, but
# it means those two "defensive" blocklists are not actually covering this data.
FIXTURE_EMAIL_DOMAINS = ("example.com", "example.org", "example.net")

# Terminal in BOTH vocabularies. See module docstring for why not inactive/paused.
QUARANTINE_STATUS = "cancelled"

# Never touched, whatever else matches. `platform` is the internal self-tenant
# that owns own-brand content and must keep running.
PROTECTED_CLIENT_IDS = frozenset({"platform", "leadgenai-self"})


def quarantine_enabled() -> bool:
    """`TENANT_QUARANTINE` gate — unset/0 = INERT (report-only, default)."""
    return os.environ.get("TENANT_QUARANTINE", "").strip().lower() in ("1", "true", "yes", "on")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _write_backup(rows: list[dict[str, Any]]) -> str:
    """Resolve + write the pre-mutation backup in ONE place. Returns the path.

    Resolve and write are deliberately not split. CI's runtime-data debt ratchet
    classifies a write by the path expression at the `open()` site: straight
    from `resolve_store_path` it is CANONICAL, via a helper's return value it
    reads as an undeclared mutable path and fails the gate. A hardcoded
    `data/backups` is genuinely wrong here anyway — several stores were cut over
    to `/var/lib/leadgen/runtime/` and the stale `data/` copies were left in the
    checkout, so a backup written there could land where nothing reads it.

    Store is `customers.identity`: this is a snapshot of customer identity rows
    taken immediately before they are mutated, so it belongs to that store's
    family rather than a new manifest entry.
    """
    from app.platform import runtime_data_authority as _auth

    target = (
        _auth.resolve_store_path(
            store_id="customers.identity",
            legacy_path=Path("data") / "marketing_clients.jsonl",
            target_segments=("customers", "marketing_clients.jsonl"),
        ).parent
        / f"tenant_quarantine_{_now().strftime('%Y%m%d_%H%M%S')}.csv"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["id", "business_name", "contact_email", "status", "monthly_amount"]
        )
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return str(target)


def _looks_like_fixture(email: str) -> bool:
    """True only for an RFC-2606 reserved DOMAIN.

    `contact5@perfect.example.com` -> domain `perfect.example.com` -> matches on
    the `.example.com` suffix. `d79d690f61b3@upi.local` -> `upi.local` -> no
    match, which is the property that protects every real UPI customer.
    """
    e = (email or "").strip().lower()
    if "@" not in e:
        return False
    domain = e.rsplit("@", 1)[-1].strip()
    if not domain:
        return False
    return any(domain == d or domain.endswith("." + d) for d in FIXTURE_EMAIL_DOMAINS)


def _has_live_subscription(db, cid: str) -> bool:
    """Any subscription not in a terminal state = a real tenant. Fail CLOSED:
    if we cannot tell, we treat it as live and refuse to quarantine."""
    try:
        from app.models.payment import Subscription

        rows = db.query(Subscription.status).filter(Subscription.client_id == cid).all()
        for (st,) in rows:
            s = str(getattr(st, "value", st) or "").strip().lower()
            if s not in ("cancelled", "canceled", "expired", "ended"):
                return True
        return False
    except Exception as e:
        logger.warning("[quarantine] subscription check failed for %s — refusing: %s", cid, e)
        return True


def _has_billing_alias(cid: str) -> bool:
    """A linked marketing record means a real tenant identity. Fail CLOSED."""
    try:
        from app.marketing import clients_store

        rec = clients_store.resolve_client(cid)
        if not rec:
            return False
        return bool(rec.get("billing_client_ids"))
    except Exception as e:
        logger.warning("[quarantine] alias check failed for %s — refusing: %s", cid, e)
        return True


def find_fixture_tenants() -> dict[str, Any]:
    """READ-ONLY. Classify every Postgres client as fixture / protected / real.

    Returns candidates plus the reason each non-candidate was refused, so the
    decision is auditable before anything is flipped. Never raises.
    """
    out: dict[str, Any] = {
        "candidates": [],
        "refused": [],
        "at": _now().isoformat(),
        "quarantine_status": QUARANTINE_STATUS,
    }
    try:
        from app.models.base import get_db_session
        from app.models.client import Client

        with get_db_session() as db:
            for c in db.query(Client).all():
                cid = str(c.id or "")
                email = str(c.contact_email or "")
                status = str(getattr(c.status, "value", c.status) or "")
                row = {
                    "id": cid,
                    "business_name": str(c.business_name or ""),
                    "contact_email": email,
                    "status": status,
                    "monthly_amount": c.monthly_amount,
                }
                if cid in PROTECTED_CLIENT_IDS:
                    out["refused"].append({**row, "reason": "protected_id"})
                    continue
                if not _looks_like_fixture(email):
                    out["refused"].append({**row, "reason": "not_a_fixture_email"})
                    continue
                if status == QUARANTINE_STATUS:
                    out["refused"].append({**row, "reason": "already_quarantined"})
                    continue
                if _has_live_subscription(db, cid):
                    out["refused"].append({**row, "reason": "has_live_subscription"})
                    continue
                if _has_billing_alias(cid):
                    out["refused"].append({**row, "reason": "has_billing_alias"})
                    continue
                out["candidates"].append(row)
    except Exception as e:
        logger.warning("[quarantine] find_fixture_tenants failed: %s", e)
        out["error"] = str(e)[:200]
    return out


def quarantine_fixture_tenants(limit: int = 50, dry_run: bool = True) -> dict[str, Any]:
    """Flip fixture tenants to `cancelled` in Postgres AND the JSONL store.

    Deletes nothing. `billing_records`, `call_logs`, `subscriptions` and
    `invoices` are left untouched on purpose — they are the audit trail, and a
    status flip does not change row identity so no FK is affected.

    `dry_run=True` reports what it WOULD do and mutates nothing. Never raises.
    Mutating (`dry_run=False`) requires `TENANT_QUARANTINE=1` — otherwise refuse.
    """
    scan = find_fixture_tenants()
    cands = list(scan.get("candidates") or [])[: max(0, int(limit))]
    out: dict[str, Any] = {
        "scanned": len(scan.get("candidates") or []),
        "selected": len(cands),
        "pg_updated": 0,
        "jsonl_updated": 0,
        "dry_run": bool(dry_run),
        "backup": "",
        "status_applied": QUARANTINE_STATUS,
        "refused": scan.get("refused", []),
        "at": _now().isoformat(),
        "flag_enabled": quarantine_enabled(),
    }
    if not cands:
        return out
    if dry_run:
        out["would_quarantine"] = cands
        return out
    if not quarantine_enabled():
        out["error"] = "TENANT_QUARANTINE_off"
        out["would_quarantine"] = cands
        return out

    # Backup BEFORE mutating — the previous status is not recoverable from the
    # row once overwritten.
    try:
        out["backup"] = _write_backup(cands)
    except Exception as be:
        out["error"] = f"backup_failed: {str(be)[:120]}"
        return out

    try:
        from app.models.base import get_db_session
        from app.models.client import Client, ClientStatus

        with get_db_session() as db:
            for r in cands:
                row = db.query(Client).filter(Client.id == r["id"]).first()
                if row is None:
                    continue
                cur = str(getattr(row.status, "value", row.status) or "")
                if cur == QUARANTINE_STATUS:  # idempotent
                    continue
                row.status = ClientStatus.CANCELLED
                out["pg_updated"] += 1
            db.commit()
    except Exception as e:
        logger.warning("[quarantine] postgres flip failed: %s", e)
        out["error"] = str(e)[:200]

    # JSONL store is best-effort and separate: most fixtures exist only in
    # Postgres, so a miss here is normal and must not fail the run.
    try:
        from app.marketing import clients_store

        for r in cands:
            try:
                if clients_store.get_client(r["id"]):
                    if clients_store.set_status(r["id"], QUARANTINE_STATUS):
                        out["jsonl_updated"] += 1
            except Exception:
                continue
    except Exception as e:
        logger.debug("[quarantine] jsonl flip skipped: %s", e)

    return out
