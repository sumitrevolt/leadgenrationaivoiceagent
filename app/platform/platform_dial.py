"""platform_dial config — daily self-sale AI cold-call batch knobs (Swara).

Env pehle (explicit 0/1 = final kill-switch), warna bind-mounted
``data/platform_dial.json`` fallback — upi_config pattern: container recreate
ke bina toggle ho sakta (data/ bind-mount har container me live hai) aur
docker-cp-drift wale containers me bhi kaam karta jahan naya .env var
recreate ke bina inject nahi ho sakta. Never raises.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 15


def _cfg_path() -> Path:
    """Resolved per call — one half of the calling-safety config family.

    `platform_dial.json` and `dial_test_mode.json` share ONE store id, so the
    authority resolves both through the same mode and root by construction.
    One file canonical and the other legacy would mean the operator's dial kill
    and the test-mode allowlist disagreed about which deployment they belong to.
    """
    from app.platform import runtime_data_authority as _auth

    return _auth.resolve_store_path(
        store_id="telephony.calling_safety_config",
        legacy_path=Path("data/platform_dial.json"),
        target_segments=("telephony", "platform_dial.json"),
        override_env="PLATFORM_DIAL_CONFIG",
    )


def _file_cfg() -> dict:
    try:
        data = json.loads(_cfg_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def enabled() -> bool:
    """Env explicit ho to wahi final (0 = hard kill-switch); warna data-file.

    PLATFORM_DIAL_DAILY is a BOOLEAN switch. The per-run count lives in
    PLATFORM_DIAL_LIMIT (see ``dial_limit``). Those two names read as if they
    were the same knob, and on 2026-08-03 prod was found with
    ``PLATFORM_DIAL_DAILY=100``: the operator meant "100 calls a day", the value
    matched neither the true nor the false token, and the old code SILENTLY fell
    through to the data-file — which said disabled. Result: the campaign looked
    armed in ``.env`` (kill=0, DLT approved, cap 100) while the daily dial job
    reported ``mandate_paused`` and never ran.

    A count is therefore accepted as intent: any positive integer means ON, and
    ``0`` stays the hard kill-switch in both spellings. Anything genuinely
    unparseable is logged and falls back to the file rather than silently
    resolving to a value nobody chose.
    """
    v = os.environ.get("PLATFORM_DIAL_DAILY", "").strip().lower()
    if not v:
        return bool(_file_cfg().get("enabled"))
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    try:
        n = int(v)
    except ValueError:
        logger.warning(
            "[platform_dial] PLATFORM_DIAL_DAILY=%r is neither a boolean nor a "
            "number; falling back to the data-file. Set 1/0 to be explicit.",
            v,
        )
        return bool(_file_cfg().get("enabled"))
    # A numeric value is an operator saying "dial this many" -> ON (0 = off).
    if n > 0:
        logger.warning(
            "[platform_dial] PLATFORM_DIAL_DAILY=%s is a COUNT, but this flag is the "
            "on/off switch; the per-run cap is PLATFORM_DIAL_LIMIT. Treating as ON.",
            n,
        )
        return True
    return False


def dial_limit() -> int:
    raw = os.environ.get("PLATFORM_DIAL_LIMIT", "").strip()
    if not raw:
        raw = str(_file_cfg().get("limit") or "")
    try:
        n = int(raw or _DEFAULT_LIMIT)
    except Exception:
        n = _DEFAULT_LIMIT
    return max(1, min(n, 200))


def dial_niche() -> str:
    """ "all" = poora harvested pool; ya ek specific niche key."""
    raw = (os.environ.get("PLATFORM_DIAL_NICHE", "") or "").strip()
    if not raw:
        raw = str(_file_cfg().get("niche") or "").strip()
    return raw or "all"
