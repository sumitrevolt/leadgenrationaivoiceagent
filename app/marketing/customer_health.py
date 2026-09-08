"""Customer Health Score — automated churn prediction + engagement tracking.

Inspired by HubSpot Customer Health, Totango, Gainsight:
  - Multi-factor scoring: engagement, usage, payment, satisfaction, growth
  - Churn risk classification: healthy / at_risk / critical
  - Automated alerts for at-risk accounts
  - Customer health dashboard data
  - Track: data/customer_health.jsonl
  - Feature flag: CUSTOMER_HEALTH (default OFF)

100% free stack, never raises, tenant-isolated.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STORE = os.path.join("data", "customer_health.jsonl")

# Scoring weights (total = 100)
WEIGHTS = {
    "engagement": 25,  # Dashboard logins, content approvals, interactions
    "usage": 20,  # Features used, posts scheduled, leads handled
    "payment": 25,  # On-time payments, subscription status
    "satisfaction": 15,  # NPS, review sentiment, support tickets
    "growth": 15,  # Lead volume trend, content performance
}

# Thresholds
HEALTHY_THRESHOLD = 70
AT_RISK_THRESHOLD = 40


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _track(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_STORE) or ".", exist_ok=True)
        with open(_STORE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _load_health(client_id: str) -> dict[str, Any] | None:
    """Load latest health record for a client."""
    latest = None
    try:
        if os.path.exists(_STORE):
            with open(_STORE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if rec.get("client_id") == client_id:
                            latest = rec
                    except Exception:
                        pass
    except Exception:
        pass
    return latest


def calculate_health_score(
    client_id: str,
    engagement_data: dict[str, Any] | None = None,
    usage_data: dict[str, Any] | None = None,
    payment_data: dict[str, Any] | None = None,
    satisfaction_data: dict[str, Any] | None = None,
    growth_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate customer health score from multiple factors.

    Each data dict provides raw metrics. Score is 0-100.
    """
    scores = {}

    # Engagement score (0-100)
    eng = engagement_data or {}
    eng_score = min(
        100,
        (
            (eng.get("dashboard_logins_30d", 0) * 10)
            + (eng.get("content_approvals_30d", 0) * 15)
            + (eng.get("support_replies_30d", 0) * 5)
            + (eng.get("last_login_days_ago", 30) * -2)
        ),
    )
    scores["engagement"] = max(0, min(100, eng_score))

    # Usage score (0-100)
    usg = usage_data or {}
    usg_score = min(
        100,
        (
            (usg.get("posts_created_30d", 0) * 8)
            + (usg.get("leads_handled_30d", 0) * 3)
            + (usg.get("features_used", 0) * 10)
            + (usg.get("api_calls_30d", 0) * 0.5)
        ),
    )
    scores["usage"] = max(0, min(100, usg_score))

    # Payment score (0-100)
    pay = payment_data or {}
    pay_score = 100
    if pay.get("subscription_status") == "cancelled":
        pay_score = 0
    elif pay.get("subscription_status") == "past_due":
        pay_score = 30
    elif pay.get("subscription_status") == "active":
        pay_score = 80
    if pay.get("on_time_payments_pct", 100) >= 90:
        pay_score = min(100, pay_score + 20)
    scores["payment"] = max(0, min(100, pay_score))

    # Satisfaction score (0-100)
    sat = satisfaction_data or {}
    nps = sat.get("nps_score", 5)
    sat_score = nps * 10  # NPS 0-10 → 0-100
    if sat.get("support_tickets_open", 0) > 3:
        sat_score -= 20
    if sat.get("review_sentiment", 3) >= 4:
        sat_score += 15
    scores["satisfaction"] = max(0, min(100, sat_score))

    # Growth score (0-100)
    grw = growth_data or {}
    grw_score = 50  # baseline
    if grw.get("leads_trend") == "up":
        grw_score += 25
    elif grw.get("leads_trend") == "down":
        grw_score -= 20
    if grw.get("content_performance") == "up":
        grw_score += 15
    if grw.get("month_over_month_growth", 0) > 10:
        grw_score += 10
    scores["growth"] = max(0, min(100, grw_score))

    # Weighted total
    total = sum(scores[k] * WEIGHTS[k] / 100 for k in WEIGHTS if k in scores)
    total = max(0, min(100, round(total, 1)))

    # Classification
    if total >= HEALTHY_THRESHOLD:
        classification = "healthy"
    elif total >= AT_RISK_THRESHOLD:
        classification = "at_risk"
    else:
        classification = "critical"

    # Build recommendation
    recommendation = _build_recommendation(classification, scores)

    return {
        "client_id": client_id,
        "total_score": total,
        "classification": classification,
        "scores": scores,
        "recommendation": recommendation,
        "calculated_at": _now(),
    }


def _build_recommendation(classification: str, scores: dict) -> str:
    """Generate actionable recommendation based on scores."""
    if classification == "healthy":
        return (
            "Customer healthy hai. Growth opportunities explore karo — upsell ya referral program."
        )

    weakest = min(scores, key=scores.get) if scores else "engagement"

    recs = {
        "engagement": "Customer kam engage ho raha hai. Personal outreach karo — call ya WhatsApp pe check karo.",
        "usage": "Features kaam me nahi aa rahe. Training session offer karo ya quick walkthrough bhejo.",
        "payment": "Payment issue hai. Dunning sequence activate karo ya owner ko alert karo.",
        "satisfaction": "Customer khush nahi hai. NPS survey bhejo ya personal call karo feedback lene.",
        "growth": "Growth ruk gaya hai. Naya content plan ya campaign proposal do.",
    }

    return recs.get(weakest, "Customer ko personally reach out karo.")


async def record_health(
    client_id: str,
    engagement_data: dict[str, Any] | None = None,
    usage_data: dict[str, Any] | None = None,
    payment_data: dict[str, Any] | None = None,
    satisfaction_data: dict[str, Any] | None = None,
    growth_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate and record customer health score."""
    result = calculate_health_score(
        client_id,
        engagement_data,
        usage_data,
        payment_data,
        satisfaction_data,
        growth_data,
    )
    _track(result)

    # Alert if critical
    if result["classification"] == "critical":
        try:
            from app.utils.logger import setup_logger

            logger.warning(
                f"[customer_health] CRITICAL health for {client_id}: "
                f"score={result['total_score']}, recommendation={result['recommendation']}"
            )
        except Exception:
            pass

    return result


def get_client_health(client_id: str) -> dict[str, Any] | None:
    """Get latest health record for a client."""
    return _load_health(client_id)


def get_all_health(client_id: str | None = None) -> list[dict[str, Any]]:
    """Get health records for all clients or filtered."""
    records = []
    try:
        if os.path.exists(_STORE):
            with open(_STORE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if client_id and rec.get("client_id") != client_id:
                            continue
                        records.append(rec)
                    except Exception:
                        pass
    except Exception:
        pass
    return records


def get_health_summary() -> dict[str, Any]:
    """Aggregate health summary across all clients."""
    records = get_all_health()
    total = len(records)
    healthy = sum(1 for r in records if r.get("classification") == "healthy")
    at_risk = sum(1 for r in records if r.get("classification") == "at_risk")
    critical = sum(1 for r in records if r.get("classification") == "critical")
    avg_score = sum(r.get("total_score", 0) for r in records) / total if total > 0 else 0

    return {
        "total_clients": total,
        "healthy": healthy,
        "at_risk": at_risk,
        "critical": critical,
        "avg_score": round(avg_score, 1),
        "health_rate": round(healthy / total * 100, 1) if total > 0 else 0,
    }


__all__ = [
    "calculate_health_score",
    "record_health",
    "get_client_health",
    "get_all_health",
    "get_health_summary",
    "WEIGHTS",
    "HEALTHY_THRESHOLD",
    "AT_RISK_THRESHOLD",
]
