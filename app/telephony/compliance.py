"""
Compliance Gate — the ONE chokepoint every outbound call must pass (India TCCCPR/TRAI).
=======================================================================================

India's TCCCPR (TRAI) rules for automated/commercial voice calls:
  * DND scrub        — promotional calls to NDNC/DND numbers are illegal.
  * Calling window   — promotional 10:00–19:00 IST (service/transactional wider).
  * 140-series + DLT — promotional calls need a registered 140 caller-id and a
                       DLT-approved principal entity.
  * AI disclosure    — the call must disclose it is an automated/AI call.
Violations carry penalties up to ₹10 lakh, so this gate is **fail-safe**: a
promotional call that cannot be proven compliant is BLOCKED by default.

Two call types:
  * PROMOTIONAL  (cold outreach)  -> strict: DND + window + DLT/140 all enforced.
  * TRANSACTIONAL(consented/known)-> lenient: only a sane calling window.

Design: import-safe, never raises. On an internal error it fails SAFE
(promotional -> block, transactional -> allow). Config is read from env each
call (so the VPS can flip DLT_APPROVED / the allowlist without a code deploy).

Config (env, all optional with safe defaults):
  COMPLIANCE_ENABLED      "1" (default) | "0" to bypass the gate (logs a warning)
  COMPLIANCE_ALLOWLIST    comma list of own/consented/test numbers -> always allowed
  DLT_APPROVED            "1" once your DLT principal-entity approval is live
  COMPLIANCE_PROMO_START  promotional window start, "HH:MM" IST (default 10:00)
  COMPLIANCE_PROMO_END    promotional window end,   "HH:MM" IST (default 19:00)
  COMPLIANCE_TXN_START    transactional window start (default 09:00)
  COMPLIANCE_TXN_END      transactional window end   (default 21:00)
  DND_FAIL_OPEN           "1" to treat a failed DND lookup as "not on DND"
                         (use when Exotel KYC is pending and you accept the risk)
  (caller-id is read from settings.vobiz_caller_id, else VOBIZ_CALLER_ID env)

Usage:
    from app.telephony.compliance import get_compliance_gate, CallType

    decision = await get_compliance_gate().check(phone, CallType.PROMOTIONAL)
    if not decision.allowed:
        ...  # do NOT dial; decision.reasons explains why
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from enum import Enum
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# India Standard Time (UTC+5:30) — no tz database dependency.
IST = timezone(timedelta(hours=5, minutes=30))


class CallType(str, Enum):
    PROMOTIONAL = "promotional"  # cold outreach — strict rules
    TRANSACTIONAL = "transactional"  # consented / known number — lenient


@dataclass
class ComplianceDecision:
    """Result of a compliance check. ``allowed`` decides whether to dial."""

    allowed: bool
    call_type: str
    phone: str
    reasons: list[str] = field(default_factory=list)  # why blocked (or notes)
    checks: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "call_type": self.call_type,
            "phone": self.phone,
            "reasons": list(self.reasons),
            "checks": dict(self.checks),
        }


def _digits(phone: str) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit())


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name, "") or "").strip() or default


def _parse_hhmm(value: str, default: time) -> time:
    """Parse 'HH' or 'HH:MM' (24h) -> time; bad value -> default (never raises)."""
    try:
        v = (value or "").strip()
        if not v:
            return default
        parts = v.split(":")
        hh = int(parts[0])
        mm = int(parts[1]) if len(parts) > 1 else 0
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return time(hh, mm)
    except Exception:
        pass
    return default


class ComplianceGate:
    """Single pre-dial gate. ``check()`` returns a ComplianceDecision; never raises."""

    def __init__(self, dnd_checker: Any = None) -> None:
        self._dnd = dnd_checker  # injected/lazy DNDChecker
        self._dnd_tried = False

    # ----------------------------- config ----------------------------- #
    @staticmethod
    def _enabled() -> bool:
        return _env("COMPLIANCE_ENABLED", "1") not in ("0", "false", "no", "off")

    @staticmethod
    def _dlt_approved() -> bool:
        return _env("DLT_APPROVED", "0") in ("1", "true", "yes", "on")

    @staticmethod
    def _allowlist() -> set:
        raw = _env("COMPLIANCE_ALLOWLIST", "")
        out = set()
        # Split ONLY on , and ; — never on spaces (a number may contain spaces,
        # e.g. "+91 98765 43210"); _digits() then strips spaces/+/dashes.
        for tok in raw.replace(";", ",").split(","):
            d = _digits(tok)
            if len(d) >= 10:
                out.add(d[-10:])  # compare on the last 10 digits (ignore +91/91)
        return out

    @staticmethod
    def _caller_id() -> str:
        try:
            from app.config import settings

            cid = (getattr(settings, "vobiz_caller_id", "") or "").strip()
            if cid:
                return cid
        except Exception:
            pass
        return _env("VOBIZ_CALLER_ID", "")

    def _window(self, call_type: CallType) -> tuple:
        if call_type == CallType.PROMOTIONAL:
            start = _parse_hhmm(_env("COMPLIANCE_PROMO_START"), time(10, 0))
            end = _parse_hhmm(_env("COMPLIANCE_PROMO_END"), time(19, 0))
        else:
            start = _parse_hhmm(_env("COMPLIANCE_TXN_START"), time(9, 0))
            end = _parse_hhmm(_env("COMPLIANCE_TXN_END"), time(21, 0))
        return start, end

    # ------------------------------ DND ------------------------------- #
    def _get_dnd(self) -> Any:
        if self._dnd is not None or self._dnd_tried:
            return self._dnd
        self._dnd_tried = True
        try:
            from app.utils.dnd_checker import DNDChecker

            self._dnd = DNDChecker()
        except Exception as e:
            logger.debug(f"compliance: DNDChecker unavailable ({e}).")
            self._dnd = None
        return self._dnd

    async def _is_dnd(self, phone: str) -> bool | None:
        """True/False if verifiable, None if it could not be checked.
        When DND_FAIL_OPEN=1 and the lookup fails/unverified, returns False
        (caller accepts the risk — e.g. Exotel KYC pending)."""
        _fail_open = _env("DND_FAIL_OPEN", "0") in ("1", "true", "yes")
        checker = self._get_dnd()
        if checker is None:
            return False if _fail_open else None
        try:
            res = await checker.check_single(phone)
            # FAIL-CLOSED by default: unverified lookup treated as unknown → block.
            # DND_FAIL_OPEN=1 overrides: treat unverified as "not on DND".
            if not getattr(res, "verified", True):
                return False if _fail_open else None
            return bool(getattr(res, "is_dnd", False))
        except Exception as e:
            logger.debug(f"compliance: DND check failed for {phone} ({e}).")
            return False if _fail_open else None

    # ----------------------------- check ------------------------------ #
    async def check(
        self,
        phone: str,
        call_type: CallType = CallType.PROMOTIONAL,
        now: datetime | None = None,
    ) -> ComplianceDecision:
        """Run every applicable rule. Returns a ComplianceDecision (never raises)."""
        try:
            ct = call_type if isinstance(call_type, CallType) else CallType(str(call_type))
        except Exception:
            ct = CallType.PROMOTIONAL
        phone_d = _digits(phone)
        reasons: list[str] = []
        checks: dict[str, Any] = {"call_type": ct.value}

        try:
            # 0) kill switch (explicit opt-out; logs so it is never silent).
            if not self._enabled():
                logger.warning("⚠️ ComplianceGate DISABLED (COMPLIANCE_ENABLED=0) — allowing call.")
                return ComplianceDecision(
                    True, ct.value, phone, ["compliance_disabled"], {"enabled": False}
                )

            # 1) phone sanity (E.164-ish: 10–15 digits).
            checks["digits"] = len(phone_d)
            if not (10 <= len(phone_d) <= 15):
                reasons.append("invalid_number")
                return ComplianceDecision(False, ct.value, phone, reasons, checks)

            # 2) allowlist — own / consented / test numbers always pass.
            if phone_d[-10:] in self._allowlist():
                checks["allowlisted"] = True
                return ComplianceDecision(True, ct.value, phone, ["allowlisted"], checks)

            # 2.5) opt-out suppression (TCCCPR: revoked consent > sab kuch for promo).
            #      Transactional pe block nahi (user ne khud callback manga ho sakta),
            #      sirf note. Defensive: ledger error = no change.
            try:
                from app.telephony.consent_ledger import is_suppressed

                if is_suppressed(phone_d):
                    checks["suppressed"] = True
                    if ct == CallType.PROMOTIONAL:
                        reasons.append("opted_out")
                        return ComplianceDecision(False, ct.value, phone, reasons, checks)
            except Exception:
                pass

            # 3) calling-hours window (IST).
            now_ist = now or datetime.now(IST)
            if now_ist.tzinfo is None:
                now_ist = now_ist.replace(tzinfo=IST)
            now_ist = now_ist.astimezone(IST)
            start, end = self._window(ct)
            within = start <= now_ist.time() <= end
            checks["now_ist"] = now_ist.strftime("%H:%M")
            checks["window"] = f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"
            checks["within_hours"] = within
            if not within:
                reasons.append(f"outside_calling_hours[{checks['window']} IST]")

            # 4) promotional-only: DND scrub + DLT/140.
            if ct == CallType.PROMOTIONAL:
                dnd = await self._is_dnd(phone)
                checks["dnd"] = dnd
                if dnd is True:
                    reasons.append("on_dnd_registry")
                elif dnd is None:
                    # FAIL-CLOSED (TCCCPR): we could NOT prove the number is off the
                    # DND registry -> block the promotional call rather than risk a
                    # penalty (up to ₹10L). Configure Exotel creds to verify + allow.
                    checks["dnd_note"] = "lookup_failed"
                    reasons.append("dnd_lookup_failed")

                if not self._dlt_approved():
                    reasons.append("dlt_not_approved[set DLT_APPROVED=1 after approval]")
                if not self._caller_id():
                    reasons.append("no_140_caller_id[set VOBIZ_CALLER_ID]")

            allowed = not reasons
            if not allowed:
                logger.warning(
                    f"🚫 ComplianceGate BLOCKED {ct.value} call to ***{phone_d[-4:]}: "
                    f"{', '.join(reasons)}"
                )
            return ComplianceDecision(allowed, ct.value, phone, reasons, checks)

        except Exception as e:
            # Fail SAFE: promo blocked, transactional allowed.
            logger.warning(
                f"compliance: gate error ({e}); failing {'closed' if ct==CallType.PROMOTIONAL else 'open'}."
            )
            safe = ct != CallType.PROMOTIONAL
            return ComplianceDecision(safe, ct.value, phone, [f"gate_error:{e}"], checks)


# ---------------------------------------------------------------------- #
# Process-wide singleton
# ---------------------------------------------------------------------- #
_gate: ComplianceGate | None = None


def get_compliance_gate() -> ComplianceGate:
    """Return the process-wide ComplianceGate singleton (lazy init)."""
    global _gate
    if _gate is None:
        _gate = ComplianceGate()
    return _gate


__all__ = ["ComplianceGate", "ComplianceDecision", "CallType", "get_compliance_gate", "IST"]
