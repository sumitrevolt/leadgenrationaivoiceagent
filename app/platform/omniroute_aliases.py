"""Read-only alias resolver for OmniRoute combo identifiers.

WHY THIS EXISTS
---------------
The 24x7 architecture freeze (`docs/architecture/24X7_ARCHITECTURE_RECORD.md`,
PHASE 1 §5) requires a single canonical combo naming scheme: ``leadsgen combo N``
(N = 1..14). The desktop-layer manifest ``config/desktop_apps/combo_distribution.yaml``
and various legacy call sites still use human-readable aliases
(``leadgen-free-first``, ``hermes-sales``, ``kimi-coding``, ``vps-01/02``,
``claude-code``, ...). Those legacy names are **NOT** a routing authority — task
routing lives in ``app/platform/omniroute_client._TASK_ROUTES`` (by task type) and,
as the 24x7 safe default, in ``app/voice_agent/free_ai.py`` (degraded-safe). This
module only normalises a legacy alias to its canonical integer so dashboards and
logs speak one language.

DESIGN RULES
------------
* A canonical ``leadsgen combo N`` (1..14) always resolves to itself.
* A known legacy alias maps to a canonical integer (display-only, best-effort).
* An unknown ref resolves to ``None`` — fail-closed, never silently invented.
* This module performs NO network I/O and holds NO secrets.
"""

from __future__ import annotations

import re

from typing import Optional

_CANONICAL_RE = re.compile(r"^leadsgen combo (\d+)$", re.IGNORECASE)

# Curated legacy → canonical-integer map. These are the 18 gateway names pruned to
# the 14 production-critical combos (per the combo_distribution.yaml council note).
# Mapping is display/consistency only; if a name is absent it resolves to None.
LEGACY_ALIASES: dict[str, int] = {
    # leadgen-* product combos
    "leadgen-free-first": 1,
    "leadgen-swara-live": 6,
    "leadgen-swara-flagship": 6,
    "leadgen-project-best": 12,
    # hermes-* agent combos
    "hermes-owner": 5,
    "hermes-sales": 9,
    "hermes-engineer": 3,
    "hermes-voice": 6,
    "hermes-marketing": 7,
    "hermes-ops": 5,
    "hermes-qa": 4,
    "hermes-research": 3,
    "hermes-finance": 5,
    # dev / desktop-only lanes
    "kimi-coding": 2,
    "vps-01": 13,
    "vps-02": 14,
    "claude-code": 1,
    # bare numbers some call sites used historically
    "combo-1": 1,
    "combo-2": 2,
    "combo-3": 3,
    "combo-4": 4,
    "combo-5": 5,
    "combo-6": 6,
    "combo-7": 7,
    "combo-8": 8,
    "combo-9": 9,
    "combo-10": 10,
    "combo-11": 11,
    "combo-12": 12,
    "combo-13": 13,
    "combo-14": 14,
}

TOTAL_COMBOS = 14


def canonical_combo_name(index: int) -> str:
    """Return the canonical ``leadsgen combo N`` string for an integer 1..14."""
    if not (1 <= int(index) <= TOTAL_COMBOS):
        raise ValueError(f"combo index out of range: {index}")
    return f"leadsgen combo {int(index)}"


def resolve_combo_index(ref: str) -> Optional[int]:
    """Resolve any combo reference to its canonical integer 1..14, or None.

    Accepts canonical strings (``leadsgen combo 6``), bare integers/strings
    (``6``), and known legacy aliases. Unknown refs return None (fail-closed).
    """
    if ref is None:
        return None
    text = str(ref).strip()
    if not text:
        return None

    m = _CANONICAL_RE.match(text)
    if m:
        idx = int(m.group(1))
        return idx if 1 <= idx <= TOTAL_COMBOS else None

    # bare integer
    if text.isdigit():
        idx = int(text)
        return idx if 1 <= idx <= TOTAL_COMBOS else None

    key = text.lower()
    if key in LEGACY_ALIASES:
        return LEGACY_ALIASES[key]
    return None


def resolve_combo_ref(ref: str) -> Optional[str]:
    """Resolve any combo reference to its canonical ``leadsgen combo N`` string.

    Returns None when the ref cannot be mapped (caller must not invent a combo).
    """
    idx = resolve_combo_index(ref)
    if idx is None:
        return None
    return canonical_combo_name(idx)


def is_legacy_alias(ref: str) -> bool:
    """True when ``ref`` is a legacy alias (not already canonical form)."""
    if not ref:
        return False
    return not _CANONICAL_RE.match(str(ref).strip()) and str(ref).strip().lower() in LEGACY_ALIASES


__all__ = [
    "LEGACY_ALIASES",
    "TOTAL_COMBOS",
    "canonical_combo_name",
    "resolve_combo_index",
    "resolve_combo_ref",
    "is_legacy_alias",
]
