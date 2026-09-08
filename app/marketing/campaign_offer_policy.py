"""campaign_offer_policy.py — immutable commercial policy for outbound campaigns.

Issue #240. Nothing connected a live outbound message to a sellable package, so
any package the reply path picked would be a guess — which is why the
interested-reply footer ships no ``am=``.

WHY NOT ``app/api/campaigns.py``
--------------------------------
That module's campaign is LEAD-GENERATION (``niche``, ``target_cities``,
``target_lead_count``, ``daily_call_limit``) — no package, price or currency —
and the live email path never touches it::

    grep -c "api.campaigns\\|campaign_id" app/platform/auto_outreach.py  ->  0

PROVENANCE MODEL (corrected after release review of #246)
---------------------------------------------------------
``campaign_variant_id`` may LOCATE a policy when choosing what to send. It must
never be the authority for a message already sent. Resolving a reply by
"variant -> newest active version" is retroactive repricing: append version 2
after version 1's message went out, and the old conversation silently acquires
commercial terms that did not exist when it was sent.

So the send path must pin ``(policy_id, policy_version)`` onto the outbound
record, and reply processing must use :func:`resolve_exact` — which returns the
exact historical row regardless of later versions or retirement. Retirement
blocks NEW sends; it never rewrites what an old message meant.

Prospects with no pinned stamp (all historical generic cold email) are
``HISTORICAL_DISCOVERY``: qualify, never quote.

IMMUTABILITY
------------
Definition rows are append-only and are NEVER mutated. Retirement is a separate
appended lifecycle event, so history stays reconstructable.

FAIL-CLOSED
-----------
Malformed rows, duplicate versions, ambiguous scope and unknown packages all
stop the money path rather than degrade it. A commercial authority that guesses
from partial data is worse than one that refuses.

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

KIND_POLICY = "policy"
KIND_RETIRED = "policy_retired"

STATUS_ACTIVE = "active"
STATUS_RETIRED = "retired"

PACKAGE_SELECTED = "PACKAGE_SELECTED"
NEEDS_QUALIFICATION = "NEEDS_QUALIFICATION"
NOT_ELIGIBLE = "NOT_ELIGIBLE"
EXCEPTION_REQUIRED = "EXCEPTION_REQUIRED"

POLICY_NOT_FOUND = "POLICY_NOT_FOUND"
POLICY_AMBIGUOUS = "POLICY_AMBIGUOUS"
POLICY_RETIRED = "POLICY_RETIRED"
POLICY_STORE_CORRUPT = "POLICY_STORE_CORRUPT"
PACKAGE_UNRESOLVED = "PACKAGE_UNRESOLVED"
PACKAGE_NOT_ALLOWED = "PACKAGE_NOT_ALLOWED"
PRICE_UNAVAILABLE = "PRICE_UNAVAILABLE"
HISTORICAL_DISCOVERY = "HISTORICAL_DISCOVERY"

FAMILY_DISCOVERY = "discovery"

POLICY_ID_RETIRED = "POLICY_ID_RETIRED"

_VALID_CURRENCIES = {"INR"}

#: Commercial families grounded in the catalogue, not invented:
#: packages.PACKAGES (starter/growth/advanced) = marketing;
#: voice_packages bands = voice; packages.TOPUP_PACKS = topup.
#: `discovery` is the honest label for outreach that pitched nothing.
_VALID_FAMILIES = {FAMILY_DISCOVERY, "marketing", "combo", "voice", "topup"}

_MAX_VALIDITY_DAYS = 365


class PolicyStoreCorrupt(Exception):
    """Raised internally when the authority cannot be trusted. Never escapes."""


__all__ = [
    "EXCEPTION_REQUIRED",
    "FAMILY_DISCOVERY",
    "HISTORICAL_DISCOVERY",
    "NEEDS_QUALIFICATION",
    "NOT_ELIGIBLE",
    "PACKAGE_SELECTED",
    "POLICY_AMBIGUOUS",
    "POLICY_ID_RETIRED",
    "POLICY_STORE_CORRUPT",
    "STATUS_ACTIVE",
    "STATUS_RETIRED",
    "list_policies",
    "put_policy",
    "qualify",
    "resolve_exact",
    "resolve_exact_with_reason",
    "resolve_for_prospect",
    "resolve_for_send",
    "retire_policy",
    "store_health",
]


def _store() -> str:
    return _STORE_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_strict() -> list[dict[str, Any]]:
    """Parse every row or refuse. A skipped row silently corrupts versioning."""
    rows: list[dict[str, Any]] = []
    path = _store()
    if not os.path.exists(path):
        return rows
    try:
        with open(path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except Exception as exc:
                    raise PolicyStoreCorrupt(f"line {lineno}: {exc}") from exc
                if not isinstance(obj, dict):
                    raise PolicyStoreCorrupt(f"line {lineno}: not an object")
                rows.append(obj)
    except PolicyStoreCorrupt:
        raise
    except Exception as exc:
        raise PolicyStoreCorrupt(str(exc)) from exc

    seen: set[tuple[str, int]] = set()
    policy_ids: set[str] = set()
    for r in rows:
        kind = r.get("kind")
        if kind == KIND_POLICY:
            key = _validate_policy_row(r)
            if key in seen:
                raise PolicyStoreCorrupt(f"duplicate (policy_id, version): {key}")
            seen.add(key)
            policy_ids.add(key[0])
        elif kind == KIND_RETIRED:
            _validate_retired_row(r)
        else:
            # An unrecognised kind is not "future data" — it is authority we
            # cannot interpret, on the money path. Refuse rather than ignore.
            raise PolicyStoreCorrupt(f"unknown row kind: {kind!r}")

    for r in rows:
        if r.get("kind") == KIND_RETIRED and str(r.get("policy_id")) not in policy_ids:
            raise PolicyStoreCorrupt(f"retirement references unknown policy: {r.get('policy_id')}")
    return rows


def _ts_ok(value: Any) -> bool:
    """Timezone-aware ISO timestamp."""
    try:
        dt = datetime.fromisoformat(str(value))
    except Exception:
        return False
    return dt.tzinfo is not None


def _validate_policy_row(r: dict[str, Any]) -> tuple[str, int]:
    """Full-schema check. A valid-JSON but malformed row must never resolve."""
    pid = r.get("policy_id")
    if not isinstance(pid, str) or not pid.strip():
        raise PolicyStoreCorrupt("policy_id must be a non-empty string")
    ver = r.get("policy_version")
    if not isinstance(ver, int) or isinstance(ver, bool) or ver < 1:
        raise PolicyStoreCorrupt(f"{pid}: policy_version must be a positive int")

    family = r.get("product_family")
    if family not in _VALID_FAMILIES:
        raise PolicyStoreCorrupt(f"{pid}: unrecognised product_family {family!r}")

    allowed = r.get("allowed_package_codes")
    if not isinstance(allowed, list) or any(
        not isinstance(c, str) or not c.strip() for c in allowed
    ):
        raise PolicyStoreCorrupt(f"{pid}: allowed_package_codes must be a list of strings")
    if len(set(allowed)) != len(allowed):
        raise PolicyStoreCorrupt(f"{pid}: duplicate package codes")
    if family != FAMILY_DISCOVERY and not allowed:
        raise PolicyStoreCorrupt(f"{pid}: sellable policy needs a non-empty allowlist")

    default = r.get("default_package_code", "")
    if not isinstance(default, str):
        raise PolicyStoreCorrupt(f"{pid}: default_package_code must be a string")
    if default and default not in allowed:
        raise PolicyStoreCorrupt(f"{pid}: default outside allowlist")

    if r.get("currency") not in _VALID_CURRENCIES:
        raise PolicyStoreCorrupt(f"{pid}: currency must be INR on the manual-UPI path")

    days = r.get("offer_validity_days")
    if not isinstance(days, int) or isinstance(days, bool) or not (1 <= days <= _MAX_VALIDITY_DAYS):
        raise PolicyStoreCorrupt(f"{pid}: offer_validity_days out of bounds")

    for field in ("message_variant", "outreach_sequence_id", "template_id"):
        if not isinstance(r.get(field, ""), str):
            raise PolicyStoreCorrupt(f"{pid}: {field} must be a string")

    if not _ts_ok(r.get("effective_from")):
        raise PolicyStoreCorrupt(f"{pid}: effective_from must be a tz-aware timestamp")
    created_by = r.get("created_by")
    if not isinstance(created_by, str) or not created_by.strip():
        raise PolicyStoreCorrupt(f"{pid}: created_by must be a non-empty string")

    return (pid, ver)


def _validate_retired_row(r: dict[str, Any]) -> None:
    pid = r.get("policy_id")
    if not isinstance(pid, str) or not pid.strip():
        raise PolicyStoreCorrupt("retirement: policy_id must be a non-empty string")
    if not _ts_ok(r.get("retired_at")):
        raise PolicyStoreCorrupt(f"retirement {pid}: retired_at must be tz-aware")
    by = r.get("retired_by")
    if not isinstance(by, str) or not by.strip():
        raise PolicyStoreCorrupt(f"retirement {pid}: retired_by must be non-empty")
    if not isinstance(r.get("reason", ""), str):
        raise PolicyStoreCorrupt(f"retirement {pid}: reason must be a string")


def store_health() -> dict[str, Any]:
    """``{"ok": bool, "reason": str}`` — cheap corruption probe for Owner OS."""
    try:
        _read_strict()
        return {"ok": True, "reason": ""}
    except PolicyStoreCorrupt as exc:
        return {"ok": False, "reason": POLICY_STORE_CORRUPT, "detail": str(exc)[:200]}


def _retired_ids(rows: list[dict[str, Any]]) -> set[str]:
    return {str(r.get("policy_id")) for r in rows if r.get("kind") == KIND_RETIRED}


def _definitions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("kind") == KIND_POLICY]


def _write_all(rows: list[dict[str, Any]]) -> bool:
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


def _price_of(package_code: str, family: str = "") -> int | None:
    """EXACT payable amount for ``package_code`` under ``family``. None = refuse.

    Deliberately NOT "find a price anywhere". A bare price lookup cannot tell
    marketing from combo from voice-annual from a top-up, and getting that wrong
    is an under/over-charge, not a cosmetic bug.

    Two hazards this closes, both real in the current catalogue:

    * ``voice_plan_price()`` documents itself as returning the MONTHLY EQUIVALENT
      even for annual plans ("annual plan pe bhi monthly equivalent deta hai").
      Freezing that into an order would quote Rs 4,999 for a Rs 49,990 annual
      commitment — a ~90% undercharge. Annual codes are refused here until a
      descriptor model carries `price_inr_year` as the payable amount.
    * a family/package mismatch (voice policy allowing `starter`, marketing
      policy allowing `voice_a_monthly`, topup policy allowing `advanced`) would
      otherwise price happily because the code exists *somewhere*.

    Free/pilot/trial (Rs 0) is refused too: a zero-amount UPI order is not a sale
    and must go through its own activation path.
    """
    code = (package_code or "").strip().lower()
    fam = (family or "").strip().lower()
    if not code:
        return None

    # Top-up packs are one-time charges in their own catalogue.
    try:
        from app.marketing import packages as pkgs

        for tp in list(getattr(pkgs, "TOPUP_PACKS", []) or []):
            if str(tp.get("key") or "").strip().lower() == code:
                if fam and fam != "topup":
                    return None
                price = int(tp.get("price_inr") or 0)
                return price if price > 0 else None
    except Exception as e:
        logger.warning("[policy] topup lookup failed: %s", e)
        return None

    # Marketing / combo subscriptions.
    try:
        from app.marketing import packages as pkgs

        for pk in list(getattr(pkgs, "PACKAGES", []) or []):
            if str(pk.get("key") or "").strip().lower() == code:
                if fam == "topup":
                    return None
                # `advanced` is Marketing + AI Voice — a COMBO, not plain
                # marketing. Family must say so or the offer misdescribes itself.
                expected = "combo" if code == "advanced" else "marketing"
                if fam and fam != expected:
                    return None
                price = int(pk.get("price_inr_month") or 0)
                return price if price > 0 else None
    except Exception as e:
        logger.warning("[policy] package lookup failed: %s", e)
        return None

    # Standalone voice plans.
    try:
        from app.marketing import voice_packages as vp

        if vp.is_voice_plan(code):
            if fam and fam != "voice":
                return None
            if code.endswith("_annual"):
                # voice_plan_price() would return the MONTHLY equivalent here.
                logger.warning(
                    "[policy] refusing annual voice code %r — needs annual payable", code
                )
                return None
            price = int(vp.voice_plan_price(code) or 0)
            return price if price > 0 else None  # pilot = 0 -> refused
    except Exception as e:
        logger.warning("[policy] voice package lookup failed: %s", e)
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
    """Append a NEW immutable version. Validates up-front; never mutates history.

    Returns None on any validation failure — an invalid policy must not be
    storable and then explode at reply time.
    """
    pid = (policy_id or "").strip()
    family = (product_family or "").strip().lower()
    if not pid or family not in _VALID_FAMILIES:
        return None

    cur = (currency or "INR").strip().upper()
    if cur not in _VALID_CURRENCIES:
        logger.warning("[policy] currency %r not allowed on the manual-UPI path", cur)
        return None
    if not (1 <= int(offer_validity_days or 0) <= 365):
        return None

    allowed = [str(c).strip().lower() for c in (allowed_package_codes or []) if str(c).strip()]
    default = (default_package_code or "").strip().lower()

    if family != FAMILY_DISCOVERY:
        # A sellable policy must name the packages it may quote, and each must
        # exist in the catalogue NOW — not be discovered missing at reply time.
        if not allowed:
            logger.warning("[policy] sellable policy needs a non-empty allowlist")
            return None
        for code in allowed:
            if _price_of(code, family) is None:
                logger.warning("[policy] allowed package %r is unknown/unpriced", code)
                return None
    if default and default not in allowed:
        return None

    try:
        from app.utils.file_lock import file_lock

        with file_lock(_store()) as locked:
            if not locked:
                return None
            try:
                rows = _read_strict()
            except PolicyStoreCorrupt as exc:
                logger.error("[policy] refusing write, store corrupt: %s", exc)
                return None

            # Retirement is permanent for a policy identity. Appending a version
            # to a retired id would write an apparently valid row that
            # resolve_for_send can never select — silently unreachable authority.
            # Replacement commercial activity uses a NEW policy_id.
            if pid in _retired_ids(rows):
                logger.warning("[policy] %s is retired — refusing new version", pid)
                return None

            versions = [
                int(r.get("policy_version") or 0)
                for r in _definitions(rows)
                if r.get("policy_id") == pid
            ]
            version = (max(versions) + 1) if versions else 1

            # Scope uniqueness: an active variant scope must map to ONE policy.
            variant = (message_variant or "").strip()
            if variant:
                retired = _retired_ids(rows)
                clash = {
                    str(r.get("policy_id"))
                    for r in _definitions(rows)
                    if str(r.get("message_variant") or "") == variant
                    and str(r.get("policy_id")) != pid
                    and str(r.get("policy_id")) not in retired
                }
                if clash:
                    logger.warning("[policy] variant %r already owned by %s", variant, clash)
                    return None

            rec: dict[str, Any] = {
                "kind": KIND_POLICY,
                "policy_id": pid,
                "policy_version": version,
                "outreach_sequence_id": (outreach_sequence_id or "").strip(),
                "template_id": (template_id or "").strip(),
                "message_variant": variant,
                "product_family": family,
                "allowed_package_codes": allowed,
                "default_package_code": default,
                "currency": cur,
                "offer_validity_days": int(offer_validity_days),
                "effective_from": _now(),
                "created_by": created_by,
            }
            rows.append(rec)
            return dict(rec) if _write_all(rows) else None
    except Exception as e:
        logger.warning("[policy] put_policy failed: %s", e)
        return None


def retire_policy(policy_id: str, *, by: str = "system", reason: str = "") -> bool:
    """Append a retirement EVENT. Definition rows are never rewritten.

    Retirement blocks new sends. It must not change what an already-sent message
    meant, so :func:`resolve_exact` keeps returning the historical version.
    """
    pid = (policy_id or "").strip()
    if not pid:
        return False
    try:
        from app.utils.file_lock import file_lock

        with file_lock(_store()) as locked:
            if not locked:
                return False
            try:
                rows = _read_strict()
            except PolicyStoreCorrupt as exc:
                logger.error("[policy] refusing retire, store corrupt: %s", exc)
                return False
            if not any(r.get("policy_id") == pid for r in _definitions(rows)):
                return False
            if pid in _retired_ids(rows):
                return True  # idempotent
            rows.append(
                {
                    "kind": KIND_RETIRED,
                    "policy_id": pid,
                    "retired_at": _now(),
                    "retired_by": by,
                    "reason": reason,
                }
            )
            return _write_all(rows)
    except Exception as e:
        logger.warning("[policy] retire failed: %s", e)
        return False


def resolve_exact_with_reason(
    policy_id: str, policy_version: Any
) -> tuple[dict[str, Any] | None, str]:
    """THE reply-time authority: exact historical row + machine-readable reason.

    Corruption must NOT be reported as "not found": Owner OS would be told to
    create a missing policy when the real problem is unreadable authority.
    """
    pid = (policy_id or "").strip()
    try:
        ver = int(policy_version)
    except Exception:
        return None, POLICY_NOT_FOUND
    if not pid or ver < 1:
        return None, POLICY_NOT_FOUND
    try:
        rows = _read_strict()
    except PolicyStoreCorrupt as exc:
        logger.error("[policy] resolve_exact refused, store corrupt: %s", exc)
        return None, POLICY_STORE_CORRUPT
    for r in _definitions(rows):
        if r.get("policy_id") == pid and int(r.get("policy_version") or 0) == ver:
            out = dict(r)
            out["status"] = STATUS_RETIRED if pid in _retired_ids(rows) else STATUS_ACTIVE
            return out, "ok"
    return None, POLICY_NOT_FOUND


def resolve_exact(policy_id: str, policy_version: Any) -> dict[str, Any] | None:
    """Convenience wrapper. Prefer :func:`resolve_exact_with_reason` on the money
    path so corruption is never mistaken for a missing policy."""
    return resolve_exact_with_reason(policy_id, policy_version)[0]


def resolve_for_send(
    *, policy_id: str = "", message_variant: str = "", outreach_sequence_id: str = ""
) -> tuple[dict[str, Any] | None, str]:
    """Pick the policy for a NEW send. ``(policy, reason)``; fail-closed.

    Ambiguity is an error, never "newest wins" — two policies claiming one
    variant is a configuration bug that must stop the send.
    """
    try:
        rows = _read_strict()
    except PolicyStoreCorrupt as exc:
        logger.error("[policy] resolve_for_send refused, store corrupt: %s", exc)
        return None, POLICY_STORE_CORRUPT

    retired = _retired_ids(rows)
    defs = [r for r in _definitions(rows) if str(r.get("policy_id")) not in retired]

    pid = (policy_id or "").strip()
    variant = (message_variant or "").strip()
    seq = (outreach_sequence_id or "").strip()
    if pid:
        defs = [r for r in defs if r.get("policy_id") == pid]
    elif variant:
        defs = [r for r in defs if str(r.get("message_variant") or "") == variant]
    elif seq:
        defs = [r for r in defs if str(r.get("outreach_sequence_id") or "") == seq]
    else:
        return None, POLICY_NOT_FOUND

    if not defs:
        return None, POLICY_NOT_FOUND
    if len({str(r.get("policy_id")) for r in defs}) > 1:
        return None, POLICY_AMBIGUOUS

    defs.sort(key=lambda r: int(r.get("policy_version") or 0), reverse=True)
    out = dict(defs[0])
    out["status"] = STATUS_ACTIVE
    return out, "ok"


def resolve_for_prospect(prospect: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str]:
    """Reply-time resolution from the PINNED stamp only. ``(policy, reason)``.

    ``campaign_variant_id`` is intentionally NOT used as a fallback here: it
    would reintroduce variant -> newest-active retroactive repricing. A prospect
    without a pinned version is historical discovery and must be qualified.
    """
    p = prospect or {}
    pid = str(p.get("campaign_offer_policy_id") or "").strip()
    ver = p.get("campaign_offer_policy_version")
    if not pid or ver in (None, ""):
        return None, HISTORICAL_DISCOVERY
    return resolve_exact_with_reason(pid, ver)


def qualify(policy: dict[str, Any] | None, facts: dict[str, Any] | None = None) -> dict[str, Any]:
    """Deterministically turn (policy, structured facts) into a package outcome.

    Facts may be LLM-extracted; the decision is not. Anything unresolved is a
    question or an exception — never a fallback price.
    """
    f = {k: v for k, v in (facts or {}).items() if v not in (None, "")}

    if not policy:
        return _outcome(NEEDS_QUALIFICATION, reason=POLICY_NOT_FOUND)

    family = str(policy.get("product_family") or "").lower()
    allowed = [str(c).lower() for c in (policy.get("allowed_package_codes") or [])]
    currency = str(policy.get("currency") or "INR")

    if policy.get("status") == STATUS_RETIRED:
        # Historical resolution still works, but a retired policy cannot quote.
        return _outcome(EXCEPTION_REQUIRED, reason=POLICY_RETIRED, currency=currency)

    # Discovery pitched nothing. A prospect naming a package is a FACT to
    # qualify against, never authorisation to sell an arbitrary catalogue item.
    if family == FAMILY_DISCOVERY:
        return _outcome(NEEDS_QUALIFICATION, reason="DISCOVERY_CAMPAIGN", currency=currency)

    # No allowlist => nothing is sellable. Empty must mean "none", not "any".
    if not allowed:
        return _outcome(EXCEPTION_REQUIRED, reason=PACKAGE_NOT_ALLOWED, currency=currency)

    candidate = str(f.get("requested_package") or "").strip().lower()
    if not candidate and len(allowed) == 1:
        candidate = allowed[0]
    if not candidate:
        candidate = str(policy.get("default_package_code") or "").strip().lower()
    if not candidate:
        return _outcome(NEEDS_QUALIFICATION, reason=PACKAGE_UNRESOLVED, currency=currency)

    if candidate not in allowed:
        return _outcome(EXCEPTION_REQUIRED, reason=PACKAGE_NOT_ALLOWED, currency=currency)

    price = _price_of(candidate, family)
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
    """Policy DEFINITION versions, newest first. Empty when the store is corrupt."""
    try:
        rows = _read_strict()
    except PolicyStoreCorrupt:
        return []
    pid = (policy_id or "").strip()
    defs = [r for r in _definitions(rows) if not pid or r.get("policy_id") == pid]
    defs.sort(
        key=lambda r: (str(r.get("policy_id")), int(r.get("policy_version") or 0)), reverse=True
    )
    return defs[: max(1, min(int(limit or 200), 1000))]
