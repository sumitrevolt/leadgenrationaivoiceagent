"""dial_gate — PROMOTIONAL outbound test-mode allowlist (USER-MANDATE 2026-07-05).

KYUN: 05-Jul ke platform_dial batch me real Vobiz paisa jala aur agent company
IVR/bots ko "interested" mark kar raha tha. User ka mandate: jab tak quality
prove na ho, promotional/cold AI calls SIRF approved (company/test) numbers pe.

DESIGN (platform_dial.py / upi_config pattern — env pehle, warna bind-mounted
data-file; container recreate ke bina toggle):
- ``DIAL_TEST_MODE`` env explicit 0/1 = final; warna ``data/dial_test_mode.json``
  ``{"enabled": ...}``; DONO absent => **DEFAULT ON** (fail-CLOSED for
  promotional — cold-calling DLT bhi user-side pending hai, so conservative
  default is also the compliance-correct default).
- Allowlist = env ``DIAL_TEST_ALLOWLIST`` (comma-separated) + data-file
  ``numbers`` list, MERGED. Matching last-10-digits pe (E.164/+91/0-prefix sab
  normalize ho jate).
- SIRF ``promotional`` call_type gate hota hai — transactional (consented
  callback / test-call to owner) untouched.

Never raises. Import-safe.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _cfg_path() -> Path:
    """Resolved per call — the other half of the calling-safety config family.

    Same store id as `platform_dial.json`, so both files move together or not
    at all.
    """
    from app.platform import runtime_data_authority as _auth

    return _auth.resolve_store_path(
        store_id="telephony.calling_safety_config",
        legacy_path=Path("data/dial_test_mode.json"),
        target_segments=("telephony", "dial_test_mode.json"),
        override_env="DIAL_TEST_MODE_CONFIG",
    )


def _file_cfg() -> dict:
    try:
        data = json.loads(_cfg_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _last10(number: str) -> str:
    return re.sub(r"\D", "", str(number or ""))[-10:]


def test_mode() -> bool:
    """Env explicit ho to wahi final; warna data-file; dono absent = ON (fail-closed)."""
    v = os.environ.get("DIAL_TEST_MODE", "").strip().lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no"):
        return False
    cfg = _file_cfg()
    if "enabled" in cfg:
        return bool(cfg.get("enabled"))
    return True  # default: test-mode ON until owner explicitly disables


def allowlist() -> set[str]:
    """Approved numbers (last-10-digit form). Env + data-file merged."""
    nums: set[str] = set()
    for raw in (os.environ.get("DIAL_TEST_ALLOWLIST", "") or "").split(","):
        n = _last10(raw)
        if len(n) == 10:
            nums.add(n)
    for raw in _file_cfg().get("numbers") or []:
        n = _last10(raw)
        if len(n) == 10:
            nums.add(n)
    return nums


# --------------------------------------------------------------------------- #
# Phone-type gate + learned DID blocklist (COUNCIL DECISION 2026-07-06, ADR-027)
# KYUN: prospect store me 649 FIXED_LINE cloud-IVR DIDs (Livspace/HDFC blocks)
# "ready" the — 05-Jul batch ne unhe dial karke IVR-machines ko pitch kiya.
# MOBILE + FIXED_LINE_OR_MOBILE dialable (real hot lead FLOM type ka tha —
# hard-block nahi); FIXED_LINE/TOLL_FREE promotional-dial BLOCK (email-only
# route, prospect delete nahi hota). Learned blocklist = self-improving loop:
# call me IVR confirm hua -> call_feedback.py yahan likhta hai; prefix
# auto-block SIRF >= threshold (3) DISTINCT confirmed numbers pe (over-block
# guard, audit-trail file me). Sab env-gated + file-reversible. Never raises.
# --------------------------------------------------------------------------- #


def _blocklist_path() -> Path:
    """Reader half of the suppression store. Creates nothing.

    A missing blocklist is a legitimate state (no number has ever been
    suppressed), so resolution must not bring the file or its parent into
    existence — only a real write does that.
    """
    from app.platform import runtime_data_authority as _auth

    return _auth.resolve_store_path(
        store_id="telephony.dial_suppression",
        legacy_path=Path("data/dial_blocklist.json"),
        target_segments=("telephony", "dial_blocklist.json"),
        override_env="DIAL_BLOCKLIST_FILE",
    )


def _blocklist() -> dict:
    try:
        data = json.loads(_blocklist_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _phone_type_gate_on() -> bool:
    """PHONE_TYPE_GATE (default ON) — promotional dial pe FIXED_LINE/TOLL_FREE block."""
    return (os.environ.get("PHONE_TYPE_GATE", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _learned_blocklist_on() -> bool:
    """LEARNED_DID_BLOCKLIST (default ON) — IVR-confirmed numbers/prefixes block."""
    return (os.environ.get("LEARNED_DID_BLOCKLIST", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _prefix_threshold() -> int:
    """Kitne DISTINCT confirmed-IVR numbers ke baad poora 6-digit prefix block
    ho (default 3 — council/risk guard: over-fit se genuine mobiles na maren)."""
    try:
        return max(2, int(os.environ.get("LEARNED_BLOCK_THRESHOLD", "3")))
    except Exception:
        return 3


def phone_quality(number: str) -> str:
    """'mobile' | 'flom' | 'fixed' | 'tollfree' | 'invalid' | 'unknown'.

    libphonenumber (IN numbering plan) se; lib absent/error => 'unknown'
    (dialing ko lib-failure par brick mat karo — allowlist/test-mode gates
    apni jagah hain)."""
    try:
        import phonenumbers

        n = _last10(number)
        if len(n) != 10:
            return "invalid"
        num = phonenumbers.parse("+91" + n, "IN")
        if not phonenumbers.is_valid_number(num):
            return "invalid"
        t = phonenumbers.number_type(num)
        if t == phonenumbers.PhoneNumberType.MOBILE:
            return "mobile"
        if t == phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE:
            return "flom"
        if t == phonenumbers.PhoneNumberType.TOLL_FREE:
            return "tollfree"
        if t == phonenumbers.PhoneNumberType.FIXED_LINE:
            return "fixed"
        return "fixed"  # premium/VOIP/pager etc — promotional-dial ke liye NOT a person
    except Exception:
        return "unknown"


def learned_block_reason(number: str) -> str:
    """'' = clear; warna block-reason. data/dial_blocklist.json consult karta —
    exact IVR-confirmed number, ya prefix jiske >= threshold distinct hits."""
    try:
        if not _learned_blocklist_on():
            return ""
        n = _last10(number)
        if len(n) != 10:
            return ""
        bl = _blocklist()
        nums = bl.get("numbers") or {}
        if n in nums:
            return f"learned_block:number:{(nums[n] or {}).get('reason', 'ivr_confirmed')}"
        prefixes = bl.get("prefixes") or {}
        p = n[:6]
        rec = prefixes.get(p) or {}
        distinct = rec.get("numbers") or []
        if len(set(distinct)) >= _prefix_threshold():
            return f"learned_block:prefix:{p}({len(set(distinct))} confirmed IVR)"
        return ""
    except Exception:
        return ""


def check(to: str, call_type: str = "transactional") -> tuple[bool, str]:
    """(allowed, reason). Promotional gate-chain:
    allowlisted -> allow (owner override) · test-mode ON -> block ·
    learned IVR blocklist -> block · phone-type fixed/tollfree/invalid -> block."""
    try:
        if (call_type or "").strip().lower() != "promotional":
            return True, "non_promotional"
        n = _last10(to)
        if n and n in allowlist():
            return True, "allowlisted"
        if test_mode():
            return (
                False,
                "dial_test_mode: promotional calls sirf allowlist numbers pe (owner mandate 2026-07-05)",
            )
        lb = learned_block_reason(to)
        if lb:
            return False, f"dial_blocklist: {lb} (self-learned from call outcomes)"
        if _phone_type_gate_on():
            q = phone_quality(to)
            if q in ("fixed", "tollfree", "invalid"):
                return False, (
                    f"phone_type_gate: {q} number promotional-dial ke liye blocked "
                    "(IVR/DID — email-only route; council 2026-07-06)"
                )
        return True, "gates_passed"
    except Exception as e:  # pragma: no cover — never block transactional on error
        logger.warning(f"[dial_gate] check error ({e}) — promotional=block, else allow")
        return (call_type or "").strip().lower() != "promotional", f"gate_error:{e}"


__all__ = [
    "test_mode",
    "allowlist",
    "check",
    "phone_quality",
    "learned_block_reason",
]
