#!/usr/bin/env python
"""Prospect Score V2 — SHADOW evaluation (read-only, no writes, no contact).

Compares V1 vs V2 on the live prospects.jsonl dataset and answers the mission
§4 acceptance questions:
  - old vs new distribution (min/max/mean/median/percentiles)
  - number crossing 50 (newly eligible)
  - top-25 sample with feature breakdown (PII-safe: no phone/email in output)
  - segment concentration (niche/city of the crossing cohort)
  - false-positive review markers (junk name, missing phone, no website)
  - score monotonicity (enriched supersets score >= base)
  - estimated brief volume per run (V2>=50 with valid phone, not yet dialed)
  - records excluded and exact reason (non-ready / not quality-approved)

Output is JSON to stdout. NEVER mutates prospects.jsonl.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.platform import lead_scoring, lead_scoring_v2, prospector  # noqa: E402


def _pct(scores: list[int], p: float) -> float:
    if not scores:
        return 0.0
    ss = sorted(scores)
    return float(ss[min(len(ss) - 1, int(len(ss) * p))])


def _mask(rec: dict) -> dict:
    """PII-safe projection for review output."""
    return {
        "business_name": str(rec.get("business_name") or "")[:40],
        "niche": rec.get("niche"),
        "city": rec.get("city"),
        "rating": rec.get("rating"),
        "reviews_count": rec.get("reviews_count"),
        "has_website": rec.get("has_website"),
        "status": rec.get("status"),
        "score": rec.get("score"),
        "lead_score": rec.get("lead_score"),
    }


def main() -> int:
    all_rows = prospector._read_all()
    approved = [r for r in all_rows if prospector.is_quality_approved(r)]
    ready = [r for r in approved if (r.get("status") or "ready") == "ready"]
    excluded = {
        "total": len(all_rows),
        "not_quality_approved": len(all_rows) - len(approved),
        "not_ready": len(approved) - len(ready),
    }

    v1 = [lead_scoring.score_lead(r) for r in ready]
    v2 = [lead_scoring_v2.score_lead_v2(r) for r in ready]

    def _dist(scores):
        return {
            "min": min(scores),
            "max": max(scores),
            "mean": round(sum(scores) / max(1, len(scores)), 2),
            "median": sorted(scores)[len(scores) // 2],
            "p50": _pct(scores, 0.50),
            "p75": _pct(scores, 0.75),
            "p90": _pct(scores, 0.90),
            "p95": _pct(scores, 0.95),
            "p99": _pct(scores, 0.99),
        }

    # Newly crossing 50.
    crossed = [r for r, s in zip(ready, v2) if s >= 50 and lead_scoring.score_lead(r) < 50]
    # Top-25 with breakdown (PII-safe).
    ranked = lead_scoring_v2.rank_v2(ready)
    top25 = []
    for r in ranked[:25]:
        row = _mask(r)
        row["score"] = r.get("lead_score")
        row["components"] = r.get("score_components")
        top25.append(row)

    # Segment concentration of crossing cohort.
    nic = Counter(str(r.get("niche") or "?") for r in crossed)
    cit = Counter(str(r.get("city") or "?") for r in crossed)

    # False-positive markers within crossed cohort.
    fp = {
        "junk_or_test_name": sum(1 for r in crossed if lead_scoring_v2._is_junk_name(r)),
        "no_valid_phone": sum(1 for r in crossed if not lead_scoring_v2.is_valid_india_mobile(r)),
        "no_website": sum(1 for r in crossed if not lead_scoring_v2.has_working_website(r)),
        "no_email": sum(1 for r in crossed if not lead_scoring_v2.is_plausible_email(r)),
        "zero_reviews": sum(1 for r in crossed if lead_scoring_v2._reviews_count(r) == 0),
    }

    # Monotonicity: enriched superset must score >= base.
    mono_checks = 0
    mono_pass = 0
    for r in ready[:500]:
        base = lead_scoring_v2.score_lead_v2(r)
        sup = dict(r)
        sup["phone"] = "+91 98220 12345"
        sup["email"] = "info@example.com"
        sup["website"] = "https://example.com"
        sup["has_website"] = "true"
        sup["wa_link"] = "https://wa.me/919822012345"
        sup["reviews_count"] = max(lead_scoring_v2._reviews_count(r), 100)
        sup["rating"] = max(lead_scoring_v2._rating(r), 4.6)
        sup["found_at"] = datetime.now(timezone.utc).isoformat()
        up = lead_scoring_v2.score_lead_v2(sup)
        mono_checks += 1
        if up >= base:
            mono_pass += 1

    # Estimated brief volume per run (V2>=50, valid phone, not yet dialed).
    dialed: set[str] = set()
    try:
        from app.platform import dialer_log

        for rec in dialer_log._read_logs():
            d = lead_scoring_v2.phone10(rec)
            if d:
                dialed.add(d)
    except Exception:
        pass
    eligible = [
        r
        for r, s in zip(ready, v2)
        if s >= 50
        and lead_scoring_v2.is_valid_india_mobile(r)
        and lead_scoring_v2.phone10(r) not in dialed
    ]

    out = {
        "score_version": lead_scoring_v2.SCORE_VERSION,
        "dataset": {
            "total_rows": len(all_rows),
            "quality_approved": len(approved),
            "ready_approved": len(ready),
        },
        "excluded": excluded,
        "old_v1": _dist(v1),
        "new_v2": _dist(v2),
        "crossing_50": {
            "count": len(crossed),
            "share_of_ready": round(100.0 * len(crossed) / max(1, len(ready)), 2),
        },
        "top_25": top25,
        "segment_concentration": {
            "niche": dict(nic.most_common(10)),
            "city": dict(cit.most_common(10)),
        },
        "false_positive_review": fp,
        "monotonicity": {"checks": mono_checks, "pass": mono_pass},
        "estimated_briefs_per_run": len(eligible),
        "ready_count": len(ready),
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
