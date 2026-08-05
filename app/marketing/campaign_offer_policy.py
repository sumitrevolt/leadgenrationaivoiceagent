"""campaign_offer_policy.py — immutable commercial policy for outbound campaigns.

Issue #240. Before this, nothing connected a live outbound message to a sellable
package. `_draft` received only business name / subject / body / intent / niche,
so any package it picked would have been a guess — which is exactly why the
interested-reply footer ships no `am=` amount today.

WHY THIS IS NOT ATTACHED TO ``app/api/campaigns.py``
---------------------------------------------------
That module's ``CampaignCreate`` is a LEAD-GENERATION campaign — ``niche``,
``target_cities``, ``target_lead_count``, ``daily_call_limit``. It carries no
package, price or currency, and the live email path never touches it:

    grep -c "api.campaigns\\|campaign_id" app/platform/auto_outreach.py  ->  0

The seam that actually exists in production is the PROSPECT RECORD. At send time
``auto_outreach`` stamps it with ``emailed_at`` and, when a copy variant was
chosen, ``campaign_variant_id``. That stamp is the only durable link between a
sent message and the prospect who received it, so commercial provenance is
resolved from there.

WHAT THIS DELIBERATELY REFUSES TO DO
------------------------------------
Package selection is a commercial decision, never an inference. This module will
not derive a package from niche, business name, reply intent, email wording, the
cheapest plan, or an LLM's opinion. An LLM may extract candidate FACTS; only the
deterministic rules here may turn facts into a package, and the result must be a
code the policy explicitly allows AND that the canonical catalogue prices.

Historical generic cold email never pitched a specific package, so it is modelled
honestly as a DISCOVERY campaign: interested replies return
``NEEDS_QUALIFICATION`` and must ask a question rather than quote a price.
Pretending otherwise would re-create the Starter-blind bug that would quote
₹1,999 to a Combo (₹5,999) or Voice (₹4,999+) prospect.

IMMUTABILITY
------------
A policy version is frozen once written. Editing appends a NEW version; the old
row keeps its commercial meaning so a message already in flight is never
re-priced retroactively. Resolution prefers the newest ACTIVE version.

Pure logic + append-only store. No network, no LLM. Never raises.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STORE_PATH = os.path.join("data", "campaign_offer_policies.jsonl")

STATUS_ACTIVE = "active"
STATUS_RETIRED = "retired"

#: Qualification outcomes.
PACKAGE_SELECTED = "PACKAGE_SELECTED"
NEEDS_QUALIFICATION = "NEEDS_QUALIFICATION"
NOT_ELIGIBLE = "NOT_ELIGIBLE"
EXCEPTION_REQUIRED = "EXCEPTION_REQUIRED"

#: Machine-readable fail-closed reasons (Owner OS exception codes).
POLICY_NOT_FOUND = "POLICY_NOT_FOUND"
POLICY_RETIRED = "POLICY_RETIRED"
PACKAGE_UNRESOLVED = "PACKAGE_UNRESOLVED"
PACKAGE_NOT_ALLOWED = "PACKAGE_NOT_ALLOWED"
PRICE_UNAVAILABLE = "PRICE_UNAVAILABLE"

#: A discovery campaign pitched no package — it must qualify, never quote.
FAMILY_DISCOVERY = "discovery"

__all__ = [
    "EXCEPTION_REQUIRED",
    "FAMILY_DISCOVERY",
    "NEEDS_QUALIFICATION",
    "NOT_ELIGIBLE",
    "PACKAGE_SELECTED",
    "STATUS_ACTIVE",
    "STATUS_RETIRED",
    "list_policies",
    "put_policy",
    "qualify",
    "resolve_policy",
    "resolve_for_prospect",
    "retire_policy",
]


def _store() -> str:
    return _STORE_PATH


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
    """Atomic rewrite. Callers holding the lock must not re-enter locked_rewrite."""
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
        logger.warning("[policy] write failed: %s", e)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False


def _price_of(package_code: str) -> int | None:
    """Canonical catalogue price. None = unknown/unpriced -> fail closed.

    Never duplicates prices here; `packages.py` stays the single source.
    """
    code = (package_code or "").strip().lower()
    if not code:
        return None
    try:
        from app.marketing import packages as pkgs

        for p in list(getattr(pkgs, "PACKAGES", []) or []):
            if str(p.get("key") or "").strip().lower() == code:
                price = int(p.get("price_inr_month") or 0)
                return price if price > 0 else None
    except Exception as e:
        logger.warning("[policy] package lookup failed: %s", e)
        return None
    try:
        from app.marketing import voice_packages as vp

        if vp.is_voice_plan(code):
            price = int(vp.voice_plan_price(code) or 0)
            return price if price > 0 else None
    except Exception:
        pass
    return None


def put_policy(
    policy_id: str,
    *,
    product_family: str,
    allowed_package_codes: list[str] | None = None,
    default_package_code: str = "",
    outreach_sequence_id: str = "",
    template_id: str = "",
    message_variant: str = "",
    currency: str = "INR",
    offer_validity_days: int = 30,
    created_by: str = "system",
) -> dict[str, Any] | None:
    """Append a NEW immutable version of ``policy_id``. Never mutates history."""
    pid = (policy_id or "").strip()
    if not pid or not (product_family or "").strip():
        return None

    allowed = [str(c).strip().lower() for c in (allowed_package_codes or []) if str(c).strip()]
    default = (default_package_code or "").strip().lower()
    if default and default not in allowed:
        logger.warning("[policy] default %r not in allowed list — refusing", default)
        return None

    try:
        from app.utils.file_lock import file_lock

        with file_lock(_store()) as locked:
            if not locked:
                return None
            rows = _read()
            version = 1 + sum(1 for r in rows if r.get("policy_id") == pid)
            rec: dict[str, Any] = {
                "policy_id": pid,
                "policy_version": version,
                "outreach_sequence_id": (outreach_sequence_id or "").strip(),
                "template_id": (template_id or "").strip(),
                "message_variant": (message_variant or "").strip(),
                "product_family": (product_family or "").strip().lower(),
                "allowed_package_codes": allowed,
                "default_package_code": default,
                "currency": (currency or "INR").strip().upper(),
                "offer_validity_days": max(1, int(offer_validity_days or 30)),
                "status": STATUS_ACTIVE,
                "effective_from": _now(),
                "retired_at": None,
                "created_by": created_by,
            }
            rows.append(rec)
            return dict(rec) if _write_all(rows) else None
    except Exception as e:
        logger.warning("[policy] put_policy failed: %s", e)
        return None


def retire_policy(policy_id: str, *, by: str = "system") -> bool:
    """Retire every active version of a policy. Retired policies cannot issue."""
    pid = (policy_id or "").strip()
    if not pid:
        return False
    try:
        from app.utils.file_lock import file_lock

        with file_lock(_store()) as locked:
            if not locked:
                return False
            rows = _read()
            hit = False
            for r in rows:
                if r.get("policy_id") == pid and r.get("status") == STATUS_ACTIVE:
                    r["status"] = STATUS_RETIRED
                    r["retired_at"] = _now()
                    r["retired_by"] = by
                    hit = True
            return bool(hit and _write_all(rows))
    except Exception as e:
        logger.warning("[policy] retire failed: %s", e)
        return False


def resolve_policy(
    *, policy_id: str = "", message_variant: str = "", outreach_sequence_id: str = ""
) -> dict[str, Any] | None:
    """Newest ACTIVE version matching the given scope. None = fail closed.

    A retired-only policy resolves to None on purpose: it must not issue new
    offers, and callers must treat None as "do not quote".
    """
    rows = [r for r in _read() if r.get("status") == STATUS_ACTIVE]
    pid = (policy_id or "").strip()
    variant = (message_variant or "").strip()
    seq = (outreach_sequence_id or "").strip()

    if pid:
        rows = [r for r in rows if r.get("policy_id") == pid]
    elif variant:
        rows = [r for r in rows if str(r.get("message_variant") or "") == variant]
    elif seq:
        rows = [r for r in rows if str(r.get("outreach_sequence_id") or "") == seq]
    else:
        return None

    if not rows:
        return None
    rows.sort(key=lambda r: int(r.get("policy_version") or 0), reverse=True)
    return dict(rows[0])


def resolve_for_prospect(prospect: dict[str, Any] | None) -> dict[str, Any] | None:
    """Resolve policy from the LIVE provenance stamp on the prospect record.

    ``auto_outreach`` writes ``campaign_variant_id`` at send time; that is the
    only durable send->prospect link in production today. A prospect with no
    stamp (all historical generic cold email) resolves to None, which callers
    must treat as discovery -> qualify, never as a licence to quote.
    """
    variant = str((prospect or {}).get("campaign_variant_id") or "").strip()
    if not variant:
        return None
    return resolve_policy(message_variant=variant)


def qualify(policy: dict[str, Any] | None, facts: dict[str, Any] | None = None) -> dict[str, Any]:
    """Deterministically turn (policy, structured facts) into a package outcome.

    Returns ``{"outcome", "package_code", "amount", "currency", "reason"}``.
    Facts may be LLM-extracted; the decision is not. Anything unresolved is a
    question to the prospect or an exception — NEVER a fallback price.
    """
    f = {k: v for k, v in (facts or {}).items() if v not in (None, "")}

    if not policy:
        return _outcome(NEEDS_QUALIFICATION, reason=POLICY_NOT_FOUND)
    if policy.get("status") != STATUS_ACTIVE:
        return _outcome(EXCEPTION_REQUIRED, reason=POLICY_RETIRED)

    family = str(policy.get("product_family") or "").lower()
    allowed = [str(c).lower() for c in (policy.get("allowed_package_codes") or [])]
    currency = str(policy.get("currency") or "INR")

    # A discovery campaign pitched nothing — it must ask, never quote.
    if family == FAMILY_DISCOVERY and not f.get("requested_package"):
        return _outcome(NEEDS_QUALIFICATION, reason="DISCOVERY_CAMPAIGN", currency=currency)

    candidate = str(f.get("requested_package") or "").strip().lower()
    if not candidate and len(allowed) == 1:
        candidate = allowed[0]
    if not candidate:
        candidate = str(policy.get("default_package_code") or "").strip().lower()
    if not candidate:
        return _outcome(NEEDS_QUALIFICATION, reason=PACKAGE_UNRESOLVED, currency=currency)

    if allowed and candidate not in allowed:
        return _outcome(EXCEPTION_REQUIRED, reason=PACKAGE_NOT_ALLOWED, currency=currency)

    price = _price_of(candidate)
    if price is None:
        return _outcome(EXCEPTION_REQUIRED, reason=PRICE_UNAVAILABLE, currency=currency)

    return _outcome(
        PACKAGE_SELECTED, package_code=candidate, amount=price, currency=currency, reason="ok"
    )


def _outcome(
    outcome: str,
    *,
    package_code: str = "",
    amount: int | None = None,
    currency: str = "INR",
    reason: str = "",
) -> dict[str, Any]:
    return {
        "outcome": outcome,
        "package_code": package_code,
        "amount": amount,
        "currency": currency,
        "reason": reason,
    }


def list_policies(policy_id: str = "", limit: int = 200) -> list[dict[str, Any]]:
    """Policy versions, newest first."""
    pid = (policy_id or "").strip()
    rows = [r for r in _read() if not pid or r.get("policy_id") == pid]
    rows.sort(
        key=lambda r: (str(r.get("policy_id")), int(r.get("policy_version") or 0)), reverse=True
    )
    return rows[: max(1, min(int(limit or 200), 1000))]
