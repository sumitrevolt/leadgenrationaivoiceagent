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
    return Path(os.environ.get("DIAL_TEST_MODE_CONFIG", "data/dial_test_mode.json"))


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


def check(to: str, call_type: str = "transactional") -> tuple[bool, str]:
    """(allowed, reason). Promotional + test-mode + not-allowlisted => blocked."""
    try:
        if (call_type or "").strip().lower() != "promotional":
            return True, "non_promotional"
        if not test_mode():
            return True, "test_mode_off"
        n = _last10(to)
        if n and n in allowlist():
            return True, "allowlisted"
        return False, "dial_test_mode: promotional calls sirf allowlist numbers pe (owner mandate 2026-07-05)"
    except Exception as e:  # pragma: no cover — never block transactional on error
        logger.warning(f"[dial_gate] check error ({e}) — promotional=block, else allow")
        return (call_type or "").strip().lower() != "promotional", f"gate_error:{e}"


__all__ = ["test_mode", "allowlist", "check"]
