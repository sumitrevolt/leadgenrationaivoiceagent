"""GTM City×Niche targeting dataset + paced coverage engine (council 2026-06-28).

WHAT: a structured, tiered dataset of Indian cities × the 39 builtin niches, with a
coverage-state ledger so the lead-harvester can systematically work through ALL
city×niche pairs over time ("one by one"), prioritised by niche lead_band × city tier,
WITHOUT blowing the Google-Maps cost cap (OSM-free-first, N pairs/run budget).

WHY: replace the ad-hoc 15-city pool + 4-niche prospector targets with a proper,
queryable coverage matrix that scales outbound coverage as the GTM motion grows.

CONTRACT (enterprise gate):
- Flag-gated: `GTM_TARGETING=1` (default OFF = current niche_prospector behaviour unchanged).
- Inert-without-flag, never-raise, free-stack (no new paid dep).
- Idempotent coverage marking (success-marked; failed pair retried next run).
- Cost-bounded: caller passes the per-run budget; we never emit more pairs than that.
- Coverage-state = data/gtm_coverage.json (bind-mounted, file_lock atomic).

This module is PURE DATA + SELECTION — it does NOT fetch anything itself; the harvester
calls `next_targets()` to get the next city×niche pairs to prospect, then `mark_covered()`.
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STATE = os.path.join("data", "gtm_coverage.json")

# --------------------------------------------------------------------------- #
# City dataset — tiered. T1 metros, T2 tier-2, T3 emerging. (state for context.)
# --------------------------------------------------------------------------- #
CITY_TIERS: dict[str, list[tuple[str, str]]] = {
    "T1": [
        ("Mumbai", "MH"),
        ("Delhi", "DL"),
        ("Bengaluru", "KA"),
        ("Hyderabad", "TS"),
        ("Chennai", "TN"),
        ("Kolkata", "WB"),
        ("Pune", "MH"),
        ("Ahmedabad", "GJ"),
    ],
    "T2": [
        ("Jaipur", "RJ"),
        ("Surat", "GJ"),
        ("Lucknow", "UP"),
        ("Kanpur", "UP"),
        ("Nagpur", "MH"),
        ("Indore", "MP"),
        ("Bhopal", "MP"),
        ("Visakhapatnam", "AP"),
        ("Patna", "BR"),
        ("Vadodara", "GJ"),
        ("Ludhiana", "PB"),
        ("Agra", "UP"),
        ("Nashik", "MH"),
        ("Rajkot", "GJ"),
        ("Varanasi", "UP"),
        ("Coimbatore", "TN"),
        ("Kochi", "KL"),
        ("Chandigarh", "CH"),
        ("Guwahati", "AS"),
        ("Mysuru", "KA"),
        ("Thiruvananthapuram", "KL"),
        ("Jodhpur", "RJ"),
        ("Ranchi", "JH"),
        ("Raipur", "CG"),
        ("Madurai", "TN"),
    ],
    "T3": [
        ("Kolhapur", "MH"),
        ("Aurangabad", "MH"),
        ("Solapur", "MH"),
        ("Amravati", "MH"),
        ("Jalandhar", "PB"),
        ("Amritsar", "PB"),
        ("Dehradun", "UK"),
        ("Gwalior", "MP"),
        ("Jabalpur", "MP"),
        ("Bhubaneswar", "OD"),
        ("Cuttack", "OD"),
        ("Tiruchirappalli", "TN"),
        ("Salem", "TN"),
        ("Hubli", "KA"),
        ("Mangalore", "KA"),
        ("Belgaum", "KA"),
        ("Vijayawada", "AP"),
        ("Guntur", "AP"),
        ("Warangal", "TS"),
        ("Nellore", "AP"),
        ("Bareilly", "UP"),
        ("Aligarh", "UP"),
        ("Moradabad", "UP"),
        ("Gorakhpur", "UP"),
        ("Udaipur", "RJ"),
        ("Ajmer", "RJ"),
        ("Bikaner", "RJ"),
        ("Siliguri", "WB"),
        ("Durgapur", "WB"),
        ("Jamshedpur", "JH"),
    ],
}

# Which city tiers a niche band should target (premium = metros; mass-local = everywhere).
# lead_band C = premium/HNI, B = high-ticket, A = mass-local (niches.py).
_BAND_TIERS = {"C": ("T1",), "B": ("T1", "T2"), "A": ("T1", "T2", "T3")}
# Priority weight: higher = harvested earlier (band-value × city-tier reach).
_BAND_W = {"C": 3, "B": 2, "A": 1}
_TIER_W = {"T1": 3, "T2": 2, "T3": 1}


def all_cities(tiers: tuple[str, ...] = ("T1", "T2", "T3")) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for t in tiers:
        out.extend(CITY_TIERS.get(t, []))
    return out


def _city_tier(city: str) -> str:
    cl = (city or "").strip().lower()
    for t, lst in CITY_TIERS.items():
        if any(c.lower() == cl for c, _ in lst):
            return t
    return "T3"


def build_matrix() -> list[dict[str, Any]]:
    """Full City×Niche target matrix, priority-scored. Pure (no I/O besides niches).
    Each pair: {city, state, tier, niche, query, band, priority}."""
    out: list[dict[str, Any]] = []
    try:
        from app.niches import NICHES, lead_band
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("[gtm] niches import failed: %s", e)
        return out
    for nkey, ncfg in (NICHES or {}).items():
        band = (lead_band(nkey) or "A").upper()
        tiers = _BAND_TIERS.get(band, ("T1", "T2", "T3"))
        # Google-Maps/OSM search phrase: first keyword > niche name > key (no search_query field).
        _kws = (ncfg or {}).get("keywords") or []
        query = str(
            (_kws[0] if isinstance(_kws, list) and _kws else None)
            or (ncfg or {}).get("name")
            or nkey.replace("_", " ")
        )
        for tier in tiers:
            for city, state in CITY_TIERS.get(tier, []):
                out.append(
                    {
                        "city": city,
                        "state": state,
                        "tier": tier,
                        "niche": nkey,
                        "query": query,
                        "band": band,
                        "priority": _BAND_W.get(band, 1) * 3 + _TIER_W.get(tier, 1),
                    }
                )
    out.sort(key=lambda p: -p["priority"])
    return out


def _pair_key(p: dict[str, Any]) -> str:
    return f"{p.get('niche')}|{p.get('city')}"


def _load_state() -> dict[str, Any]:
    try:
        if os.path.exists(_STATE):
            with open(_STATE, encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}


def _save_state(state: dict[str, Any]) -> None:
    try:
        from app.utils.file_lock import locked_rewrite

        locked_rewrite(_STATE, json.dumps(state, ensure_ascii=False, default=str))
    except Exception as e:
        logger.debug("[gtm] state save skipped: %s", e)


def enabled() -> bool:
    return os.environ.get("GTM_TARGETING", "0").strip().lower() in ("1", "true", "yes", "on")


def next_targets(n: int = 8, *, day_ordinal: int | None = None) -> list[dict[str, Any]]:
    """The next `n` highest-priority city×niche pairs that are LEAST-recently covered.
    Systematic 'one by one' coverage: never-covered first, then oldest-covered. Caller
    must respect its own API/cost cap via `n`. Returns [] if flag OFF. Never raises."""
    try:
        if not enabled():
            return []
        matrix = build_matrix()
        if not matrix:
            return []
        state = _load_state()
        covered: dict[str, Any] = state.get("pairs") or {}

        # sort: uncovered (sort_at=0) first, then oldest last_run; tie-break by priority desc
        def _sort_at(p: dict[str, Any]) -> tuple[float, float]:
            rec = covered.get(_pair_key(p)) or {}
            return (float(rec.get("last_run") or 0.0), -float(p.get("priority") or 0))

        matrix.sort(key=_sort_at)
        return matrix[: max(1, int(n))]
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("[gtm] next_targets failed: %s", e)
        return []


def mark_covered(pair: dict[str, Any], *, yield_count: int = 0, ts: float | None = None) -> None:
    """Record that a city×niche pair was harvested (success-marked, idempotent). `ts` is
    unix seconds (caller supplies — module never calls time.time at import). Never raises."""
    try:
        if not pair:
            return
        state = _load_state()
        pairs = state.setdefault("pairs", {})
        k = _pair_key(pair)
        rec = pairs.get(k) or {}
        rec["last_run"] = float(ts or 0.0)
        rec["runs"] = int(rec.get("runs") or 0) + 1
        rec["yield"] = int(rec.get("yield") or 0) + max(0, int(yield_count))
        rec["city"] = pair.get("city")
        rec["niche"] = pair.get("niche")
        pairs[k] = rec
        _save_state(state)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("[gtm] mark_covered failed: %s", e)


def coverage_summary() -> dict[str, Any]:
    """Admin view: total pairs, covered, % coverage, total yield, top uncovered. Never raises."""
    try:
        matrix = build_matrix()
        total = len(matrix)
        state = _load_state()
        covered = state.get("pairs") or {}
        n_cov = sum(1 for p in matrix if _pair_key(p) in covered)
        total_yield = sum(int((r or {}).get("yield") or 0) for r in covered.values())
        uncovered = [
            {"niche": p["niche"], "city": p["city"], "priority": p["priority"]}
            for p in matrix
            if _pair_key(p) not in covered
        ][:20]
        return {
            "enabled": enabled(),
            "cities": sum(len(v) for v in CITY_TIERS.values()),
            "total_pairs": total,
            "covered_pairs": n_cov,
            "coverage_pct": round(100 * n_cov / total, 1) if total else 0,
            "total_leads_harvested": total_yield,
            "top_uncovered": uncovered,
        }
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("[gtm] coverage_summary failed: %s", e)
        return {"enabled": enabled(), "error": "summary_failed"}


__all__ = [
    "CITY_TIERS",
    "all_cities",
    "build_matrix",
    "next_targets",
    "mark_covered",
    "coverage_summary",
    "enabled",
]
