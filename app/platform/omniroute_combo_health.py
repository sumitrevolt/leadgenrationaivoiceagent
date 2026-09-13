"""Read-side health adapter for the 14 canonical OmniRoute combos (Owner Q5).

WHAT THIS IS — and what it deliberately is NOT
----------------------------------------------
It is **not** a prober. A prober already exists and is TEST-PROVEN:
``scripts/omniroute_combo_watchdog.py`` (wrapper) → real implementation under
``docs/openclaw/scripts/omniroute_combo_watchdog.py``, 4/4 hermetic tests per
``progress.md``. It probes each combo through the same ``/v1/responses`` path
the app uses and persists consecutive-failure counters to
``data/omniroute_combo_state.json`` (gitignored runtime data).

What was missing was the READ side: nothing could turn that state file into an
honest, render-safe payload for Owner Command Center module 5 ("kaunsa combo
chal raha hai / dead hai"). This module is that adapter. Re-probing here would
have created a second, competing truth — exactly the failure mode this
migration is meant to eliminate.

TWO COMBO NAMESPACES (real drift, reconciled here)
--------------------------------------------------
* ``app/platform/omniroute_client.py`` routes on ``leadsgen combo 1..14``.
* ``config/desktop_apps/combo_distribution.yaml`` names them
  ``leadgen-free-first``, ``hermes-engineer``, ... (14 friendly ids).

They are the SAME 14 combos — the seed script declares the friendly ids as
**aliases** of the canonical ones (``scripts/seed_omniroute_14combos.py``
``COMBOS_14``). ``resolve_combo()`` maps either namespace to the canonical id,
so a dashboard can accept whatever the caller happens to have.

TRUTH RULES (non-negotiable)
----------------------------
* Never fabricate. No state file → ``instrumented=False`` and every combo
  ``unknown``. The UI must render "not instrumented", not a green tile.
* A state file older than ``stale_after`` is reported stale, not fresh.
* No secrets. Emails/keys from the seed script are intentionally NOT mirrored
  here; only id + label + aliases.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

# Mirrors scripts/seed_omniroute_14combos.py COMBOS_14 (canonical, label, aliases).
# Order is meaningful: it is the canonical 1..14 order.
CANONICAL_COMBOS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("leadsgen combo 1", "Coding & Logic Primary", (
        "leadgen-coding-primary", "leadgen-free-first", "hermes-engineer",
        "claude-omni-coding-primary", "hermes-owner",
    )),
    ("leadsgen combo 2", "Coding Fast Lane", (
        "leadgen-coding-fast", "claude-code", "claude-omni-coding-fast",
    )),
    ("leadsgen combo 3", "Repo Architecture Deep Scan", (
        "leadgen-repo-analysis", "hermes-research", "claude-omni-repo-analysis",
    )),
    ("leadsgen combo 4", "Automated Test & QA", (
        "leadgen-test-generation", "hermes-qa", "claude-omni-test-generation",
    )),
    ("leadsgen combo 5", "Agent Workforce Operations", (
        "leadgen-agent-ops", "hermes-ops", "claude-omni-agent-ops",
        "hermes-sales", "hermes-finance",
    )),
    ("leadsgen combo 6", "Voice Realtime Fallback", (
        "leadgen-swara-live", "hermes-voice", "claude-omni-swara-live", "vps-01",
    )),
    ("leadsgen combo 7", "Marketing Content & Copy", (
        "leadgen-marketing-content", "hermes-marketing", "claude-omni-marketing-content",
    )),
    ("leadsgen combo 8", "Prospecting & Lead Enrichment", (
        "leadgen-prospect-enrich", "claude-omni-prospect-enrich",
    )),
    ("leadsgen combo 9", "Outreach Email & Follow-up", (
        "leadgen-outreach-email", "claude-omni-outreach-email",
    )),
    ("leadsgen combo 10", "SEO & SEM Keyword Clustering", (
        "leadgen-seo-keyword", "claude-omni-seo-keyword",
    )),
    ("leadsgen combo 11", "Dual Governor Code Review", (
        "leadgen-governor-review", "claude-omni-governor-review",
    )),
    ("leadsgen combo 12", "50-Model Master Flagship", (
        "leadgen-project-best", "claude-omni-project-best",
    )),
    ("leadsgen combo 13", "Free-first failover lane", ("leadgen-14th-combo", "vps-02")),
    ("leadsgen combo 14", "General purpose free-tier worker", ()),
)

EXPECTED_COMBO_COUNT = 14
DEFAULT_STRIKES = 3  # matches the watchdog's --strikes default
DEFAULT_STALE_AFTER_SECONDS = 900  # same staleness window as workforce watchdog

STATE_PATH = os.path.join("data", "omniroute_combo_state.json")

STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_DOWN = "down"
STATUS_UNKNOWN = "unknown"


def _alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for canonical, _label, aliases in CANONICAL_COMBOS:
        index[canonical.strip().lower()] = canonical
        for alias in aliases:
            index[alias.strip().lower()] = canonical
    return index


_ALIASES = _alias_index()


def resolve_combo(name: str) -> str | None:
    """Map either namespace to the canonical combo id; None when unknown.

    Unknown ids are returned as None rather than guessed — a typo must surface
    as "unknown combo", never silently attach to combo 1.
    """
    if not name:
        return None
    return _ALIASES.get(str(name).strip().lower())


def canonical_ids() -> list[str]:
    return [c[0] for c in CANONICAL_COMBOS]


def labels() -> dict[str, str]:
    return {c[0]: c[1] for c in CANONICAL_COMBOS}


def load_state(path: str | None = None) -> dict[str, Any]:
    """Read the watchdog's state file. Never raises; {} on any problem."""
    path = path or STATE_PATH
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def state_mtime(path: str | None = None) -> float | None:
    try:
        return os.path.getmtime(path or STATE_PATH)
    except OSError:
        return None


def classify_combo(record: Any, *, strikes: int = DEFAULT_STRIKES) -> str:
    """Map one watchdog record -> status.

    * no record at all, or a record with no ``fails`` key -> ``unknown``.
      An absent counter is NOT evidence of health — reading it as 0 would turn
      "never probed" into a green tile, which is exactly the fabrication this
      module exists to prevent. (Caught by test, not by review.)
    * fails == 0          -> ``ok``
    * 0 < fails < strikes -> ``degraded``
    * fails >= strikes    -> ``down``
    """
    if not isinstance(record, dict):
        return STATUS_UNKNOWN
    if "fails" not in record:
        return STATUS_UNKNOWN
    try:
        fails = int(record["fails"] or 0)
    except (TypeError, ValueError):
        return STATUS_UNKNOWN
    if fails <= 0:
        return STATUS_OK
    if fails >= max(1, strikes):
        return STATUS_DOWN
    return STATUS_DEGRADED


def snapshot(
    path: str | None = None,
    *,
    strikes: int = DEFAULT_STRIKES,
    stale_after: int = DEFAULT_STALE_AFTER_SECONDS,
    now: float | None = None,
    now_dt: datetime | None = None,
) -> dict[str, Any]:
    """Render-safe payload for Owner Command Center module 5 (question Q5).

    Always returns the full 14 rows — the canonical list is static truth, while
    the per-combo status is whatever the watchdog actually recorded. Combos the
    watchdog has never probed come back ``unknown``; that is the honest answer,
    not a gap to paper over.
    """
    path = path or STATE_PATH
    now = now if now is not None else datetime.now(timezone.utc).timestamp()
    now_dt = now_dt or datetime.now(timezone.utc)

    state = load_state(path)
    mtime = state_mtime(path)
    age = None if mtime is None else max(0.0, now - mtime)
    stale = age is None or age > max(1, stale_after)
    instrumented = bool(state) and not stale

    rows: list[dict[str, Any]] = []
    for canonical, label, aliases in CANONICAL_COMBOS:
        record = state.get(canonical)
        if record is None:
            # Accept a probe recorded under any of this combo's aliases.
            for alias in aliases:
                if alias in state:
                    record = state[alias]
                    break
        status = classify_combo(record, strikes=strikes)
        last_ok = None
        last_error = ""
        if isinstance(record, dict):
            last_ok = record.get("last_ok") or None
            last_error = str(record.get("last_error") or "")
        rows.append(
            {
                "combo": canonical,
                "label": label,
                "aliases": list(aliases),
                "status": STATUS_UNKNOWN if stale and status == STATUS_OK else status,
                "fails": int(record.get("fails", 0) or 0) if isinstance(record, dict) else 0,
                "last_ok": last_ok,
                "last_error": last_error,
            }
        )

    return {
        "generated_at": now_dt,
        "source": "scripts/omniroute_combo_watchdog.py -> data/omniroute_combo_state.json",
        "state_path": path,
        "instrumented": instrumented,
        "stale": stale,
        "state_age_seconds": age,
        "strikes": max(1, strikes),
        "expected": EXPECTED_COMBO_COUNT,
        "total": len(rows),
        "ok": sum(1 for r in rows if r["status"] == STATUS_OK),
        "degraded": sum(1 for r in rows if r["status"] == STATUS_DEGRADED),
        "down": sum(1 for r in rows if r["status"] == STATUS_DOWN),
        "unknown": sum(1 for r in rows if r["status"] == STATUS_UNKNOWN),
        "combos": rows,
    }


__all__ = [
    "CANONICAL_COMBOS",
    "DEFAULT_STALE_AFTER_SECONDS",
    "DEFAULT_STRIKES",
    "EXPECTED_COMBO_COUNT",
    "STATE_PATH",
    "STATUS_DEGRADED",
    "STATUS_DOWN",
    "STATUS_OK",
    "STATUS_UNKNOWN",
    "canonical_ids",
    "classify_combo",
    "labels",
    "load_state",
    "resolve_combo",
    "snapshot",
    "state_mtime",
]
