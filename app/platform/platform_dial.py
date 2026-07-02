"""platform_dial config — daily self-sale AI cold-call batch knobs (Swara).

Env pehle (explicit 0/1 = final kill-switch), warna bind-mounted
``data/platform_dial.json`` fallback — upi_config pattern: container recreate
ke bina toggle ho sakta (data/ bind-mount har container me live hai) aur
docker-cp-drift wale containers me bhi kaam karta jahan naya .env var
recreate ke bina inject nahi ho sakta. Never raises.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_DEFAULT_LIMIT = 15


def _cfg_path() -> Path:
    return Path(os.environ.get("PLATFORM_DIAL_CONFIG", "data/platform_dial.json"))


def _file_cfg() -> dict:
    try:
        data = json.loads(_cfg_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def enabled() -> bool:
    """Env explicit ho to wahi final (0 = hard kill-switch); warna data-file."""
    v = os.environ.get("PLATFORM_DIAL_DAILY", "").strip().lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no"):
        return False
    return bool(_file_cfg().get("enabled"))


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
    """"all" = poora harvested pool; ya ek specific niche key."""
    raw = (os.environ.get("PLATFORM_DIAL_NICHE", "") or "").strip()
    if not raw:
        raw = str(_file_cfg().get("niche") or "").strip()
    return raw or "all"
