"""Prospect Score V2 — evidence-based qualified volume (2026-07-31).

WHY (ADR: prospect-score-v2): V1 (`lead_scoring.score_lead`) reads DB-Lead
fields (`source`, `phone_verified`, `email_verified`, `call_attempts`,
`created_at`) jo JSONL prospect records me NAHI hain — while the fields the
JSONL actually stores (`rating`, `reviews_count`, `website`, `has_website`,
`wa_link`, `found_at`, `source_query`) are ignored. Result: max cold-ready
score = status(4)+source(6)+verification(3)+recency(≤12)+niche(6)+engagement(2)
= 33. `dialer_sprint_prep` (min_score=50) therefore correctly returns 0.

V2 = schema-drift fix: score the signals that are actually stored, keep the
0-100 bound, add negative signals, explicit missing-data behavior, a
`score_version` + deterministic per-feature breakdown, and NO contact/send
side-effects. Pure, deterministic, idempotent, import-safe, never raises.

Design rules (mission §3):
- additive features, each → deterministic int, breakdown sum == total;
- quality-approval stays MANDATORY upstream (`prospector.is_quality_approved`);
- V1 read path untouched (this module is a new additive scorer; wiring behind
  a feature flag with V1 default — backward-compatible);
- no consent claim derived from score (score is qualification signal only);
- no automatic send / call; `counts_contact` stays False in the runtime.

Range: bounded 0-100. Missing field => 0 for that feature (never positive).
Negative signals: missing_phone (-18), low_reviews (-4), missing_email (-5),
missing_website (-5). Junk/test/QA names = HARD disqualifier (score 0,
fail-closed). India mobile = 10-digit starting 6-9 with 91/0 prefix
normalization; toll-free (1800/1860) + landline rejected.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

SCORE_VERSION = "2"

# Feature weights (single source of truth — testy bhi inhi pe assert karte hain).
# Calibrated 2026-07-31 via shadow eval: cap ~85 so only genuinely strong,
# multi-signal prospects cross 50; every feature must be EARNED (missing = 0,
# never positive). Reviews are tiered DESC (100+ = strongest proof of a real,
# operating business).
MAX_PTS = 100
PHONE_PTS = 16
EMAIL_PTS = 9
WEBSITE_PTS = 11
REVIEWS_PTS = {100: 14, 20: 9, 5: 5, 1: 2}
RATING_PTS = 6
WA_PTS = 5
COMPLETENESS_PTS = 7
NICHE_PTS = 5
SOURCE_PTS = 5
FRESH_PTS = {30: 7, 90: 4, 180: 2}
# Negative (explicit penalties — absence/quality is penalized, never rewarded).
PENALTY_NO_PHONE = -18
PENALTY_LOW_REVIEWS = -4
PENALTY_NO_EMAIL = -5
PENALTY_NO_WEBSITE = -5
PENALTY_JUNK_NAME = -20

# Junk/test/spam/example patterns (fail-closed: obvious test records HARD-disqualified).
_JUNK_NAME_TOKENS = (
    "test",
    "testing",
    "demo",
    "sample",
    "example",
    "asdf",
    "qwerty",
    "lorem",
    "dummy",
    "temp business",
    "placeholder",
    "xyz corp",
)


def _as_str(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _num(v: Any) -> int:
    try:
        return int(v)
    except Exception:
        return 0


def _float(v: Any) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


def phone10(rec: dict[str, Any]) -> str:
    """Last-10 digits (reuse memory_vault convention)."""
    digits = "".join(ch for ch in str(rec.get("phone") or "") if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else ""


def is_valid_india_mobile(rec: dict[str, Any]) -> bool:
    """10-digit India mobile: first digit 6-9 (true mobile ranges).

    Normalizes `91`/`0` prefixes (with or without +), rejects toll-free
    (1800/1860) and landline/STD patterns — a dialer cannot reach those.
    """
    digits = "".join(ch for ch in str(rec.get("phone") or "") if ch.isdigit())
    if not digits:
        return False
    if digits.startswith("1800") or digits.startswith("1860"):
        return False  # toll-free
    if digits.startswith("91") and len(digits) > 10:
        digits = digits[2:]
    if digits.startswith("0"):
        digits = digits[1:]
    return len(digits) == 10 and digits[0] in "6789"


def is_plausible_email(rec: dict[str, Any]) -> bool:
    em = _as_str(rec.get("email")).lower()
    if "@" not in em or "." not in em.split("@")[-1]:
        return False
    local, _, dom = em.partition("@")
    return bool(local.strip()) and bool(dom.strip())


def has_working_website(rec: dict[str, Any]) -> bool:
    ws = _as_str(rec.get("website"))
    if not ws:
        return False
    hw = _as_str(rec.get("has_website")).lower()
    return True if hw == "true" else bool(ws)


def _reviews_count(rec: dict[str, Any]) -> int:
    return _num(rec.get("reviews_count"))


def _rating(rec: dict[str, Any]) -> float:
    return _float(rec.get("rating"))


def _fresh_days(rec: dict[str, Any]) -> int | None:
    """found_at age in days (None = missing/parse-fail → 0 points)."""
    raw = _as_str(rec.get("found_at")) or _as_str(rec.get("created_at"))
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - dt).total_seconds() / 86400.0))
    except Exception:
        return None


def _is_junk_name(rec: dict[str, Any]) -> bool:
    name = _as_str(rec.get("business_name")).lower()
    if not name:
        return True  # unnamed business = not a real prospect
    return any(tok in name for tok in _JUNK_NAME_TOKENS)


def score_components_v2(rec: dict[str, Any]) -> dict[str, int]:
    """Deterministic feature breakdown (sum == final score). Missing → 0."""
    c: dict[str, int] = {}

    c["india_phone"] = PHONE_PTS if is_valid_india_mobile(rec) else 0
    c["business_email"] = EMAIL_PTS if is_plausible_email(rec) else 0
    c["working_website"] = WEBSITE_PTS if has_working_website(rec) else 0

    rc = _reviews_count(rec)
    # Descending floors: highest tier first (100+ > 20+ > 5+ > 1+).
    for floor, pts in sorted(REVIEWS_PTS.items(), reverse=True):
        if rc >= floor:
            c["reviews_signal"] = pts
            break
    else:
        c["reviews_signal"] = 0

    r = _rating(rec)
    c["rating_signal"] = RATING_PTS if (rc >= 5 and r >= 4.5) else 0

    c["wa_reach"] = WA_PTS if _as_str(rec.get("wa_link")) else 0

    present = [
        bool(c["india_phone"]),
        bool(c["working_website"]),
        bool(c["business_email"]),
        bool(_as_str(rec.get("city"))),
    ]
    c["profile_completeness"] = COMPLETENESS_PTS if all(present) else 0

    niche = _as_str(rec.get("niche")).lower()
    c["niche_specific"] = NICHE_PTS if (niche and niche != "general") else 0

    sq = _as_str(rec.get("source_query"))
    c["source_verified"] = SOURCE_PTS if (sq and (sq.startswith("harvest:") or len(sq) >= 5)) else 0

    fd = _fresh_days(rec)
    for floor, pts in sorted(FRESH_PTS.items()):
        if fd is not None and fd <= floor:
            c["freshness"] = pts
            break
    else:
        c["freshness"] = 0

    # Negative signals (explicit penalties).
    if not c["india_phone"]:
        c["missing_phone"] = PENALTY_NO_PHONE
    if rc == 0:
        c["low_reviews"] = PENALTY_LOW_REVIEWS
    if not c["business_email"]:
        c["missing_email"] = PENALTY_NO_EMAIL
    if not c["working_website"]:
        c["missing_website"] = PENALTY_NO_WEBSITE
    if _is_junk_name(rec):
        c["junk_or_test_name"] = PENALTY_JUNK_NAME

    return c


def score_lead_v2(rec: dict[str, Any]) -> int:
    """Bounded 0-100 score (V2). Deterministic; same record → same score.

    Junk/test/QA-name records are HARD-disqualified (score 0, fail-closed) —
    a fake name means it is not a real prospect, regardless of how rich the
    other fields look (prevents volume manufacturing via test/demo rows).
    """
    try:
        if _is_junk_name(rec):
            return 0
        total = sum(score_components_v2(rec).values())
        return max(0, min(MAX_PTS, total))
    except Exception as e:
        logger.debug("[lead_scoring_v2] score fail: %s", e)
        return 0


def explain_score(rec: dict[str, Any]) -> dict[str, Any]:
    """Breakdown + version + total (audit / top-cohort review)."""
    comps = score_components_v2(rec)
    junk = _is_junk_name(rec)
    total = 0 if junk else max(0, min(MAX_PTS, sum(comps.values())))
    return {
        "score_version": SCORE_VERSION,
        "score": total,
        "components": comps,
        "junk_name": junk,
        "valid_phone": is_valid_india_mobile(rec),
        "reviews_count": _reviews_count(rec),
        "rating": _rating(rec),
    }


def rank_v2(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Live V2 rank (desc) with breakdown + version, without mutating source."""
    out = []
    for r in records or []:
        expl = explain_score(r)
        out.append(
            {
                **r,
                "lead_score": expl["score"],
                "score_version": expl["score_version"],
                "score_components": expl["components"],
            }
        )
    out.sort(key=lambda x: x.get("lead_score", 0), reverse=True)
    return out


__all__ = [
    "SCORE_VERSION",
    "MAX_PTS",
    "score_components_v2",
    "score_lead_v2",
    "explain_score",
    "rank_v2",
    "is_valid_india_mobile",
    "is_plausible_email",
    "has_working_website",
    "phone10",
]
