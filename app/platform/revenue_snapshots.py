"""B1 - daily MRR/churn/LTV snapshots (append-only) + backfill estimate.

Real history grows one row/day via the scheduled ``revenue_snapshot`` job
(team_scheduler). Before the first snapshot exists we reconstruct an
*approximate* curve from client start-dates + plan price (clearly marked
``estimated=True``). Defensive: never raises on read.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_SNAP_FILE = os.path.join("data", "revenue_snapshots.jsonl")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _append_row(row: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(_SNAP_FILE) or ".", exist_ok=True)
        with open(_SNAP_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception as e:  # never raise
        logger.warning("revenue_snapshots append failed: %s", e)
        return False


def _read_rows() -> list[dict]:
    out: list[dict] = []
    try:
        if not os.path.isfile(_SNAP_FILE):
            return out
        with open(_SNAP_FILE, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                    if isinstance(rec, dict) and rec.get("date"):
                        out.append(rec)
                except Exception:
                    continue
    except Exception as e:
        logger.debug("revenue_snapshots read failed: %s", e)
    return out


async def snapshot_today() -> dict:
    """Collect current revenue stats and append one row for today (idempotent
    per-day on read: latest write for a date wins).
    mrr_new / mrr_churned = delta vs previous real snapshot (0 if none).
    """
    row = {
        "date": _today(),
        "mrr": 0,
        "active": 0,
        "churn_pct": 0.0,
        "ltv": 0,
        "mrr_new": 0,
        "mrr_churned": 0,
    }
    try:
        from app.platform import client_health, revenue_digest

        stats = await revenue_digest._collect()
        subs = stats.get("subscriptions") or {}
        mrr = int(stats.get("mrr") or 0)
        active = int(subs.get("active") or 0)
        health = await client_health.health_report()
        total = len(health) or 1
        reds = sum(1 for h in health if h.get("band") == "red")
        yellows = sum(1 for h in health if h.get("band") == "yellow")

        # MRR delta vs last real snapshot (skip today's estimated rows)
        prev_mrr = 0
        today_str = _today()
        for r in reversed(_read_rows()):
            if str(r.get("date"))[:10] < today_str and not r.get("estimated"):
                prev_mrr = int(r.get("mrr") or 0)
                break
        delta = mrr - prev_mrr
        mrr_new = max(0, delta)
        mrr_churned = max(0, -delta)

        row.update(
            mrr=mrr,
            active=active,
            churn_pct=round((reds + yellows) / total * 100, 1),
            ltv=int(mrr * 12 / max(1, active or total)),
            mrr_new=mrr_new,
            mrr_churned=mrr_churned,
        )
    except Exception as e:
        logger.warning("snapshot_today collect failed: %s", e)
        row["error"] = str(e)[:120]
    _append_row(row)
    return row


def _default_price(c: dict) -> int:
    """Best-effort per-client monthly ₹ from enriched keys (estimate fallback)."""
    for k in ("plan_price_inr", "price_inr", "mrr"):
        v = c.get(k)
        if v:
            try:
                return int(v)
            except Exception:
                continue
    return 0


def _load_clients() -> list[dict]:
    try:
        from app.marketing.clients_store import list_clients

        return list_clients()
    except Exception:
        return []


def _estimate_curve(days: int, clients: list[dict], price_fn) -> list[dict]:
    """Approx MRR per day = sum(price for clients started on/before that day)."""
    pts: list[dict] = []
    today = datetime.now(timezone.utc).date()
    parsed = []
    for c in clients:
        ca = str(c.get("created_at") or "")[:10]
        try:
            d = datetime.strptime(ca, "%Y-%m-%d").date()
        except Exception:
            continue
        try:
            price = int(price_fn(c) or 0)
        except Exception:
            price = 0
        parsed.append((d, price))
    if not parsed:
        return pts
    for i in range(days - 1, -1, -1):
        day = today - timedelta(days=i)
        active = sum(1 for (d, _) in parsed if d <= day)
        if active == 0:
            continue
        mrr = sum(p for (d, p) in parsed if d <= day)
        pts.append(
            {
                "date": day.strftime("%Y-%m-%d"),
                "mrr": mrr,
                "active": active,
                "churn_pct": 0.0,
                "ltv": int(mrr * 12 / max(1, active)),
                "estimated": True,
            }
        )
    return pts


def read_trend(days: int = 90, clients: list[dict] | None = None, price_fn=None) -> list[dict]:
    """Real snapshots (latest-per-date) override the estimate curve.

    ``price_fn`` prices a client dict for the estimate; the admin endpoint
    injects ``admin_dashboard._client_mrr`` (handles marketing/voice/combo).
    """
    days = max(1, min(int(days or 90), 365))
    if price_fn is None:
        price_fn = _default_price
    if clients is None:
        clients = _load_clients()
    by_date: dict[str, dict] = {}
    for p in _estimate_curve(days, clients, price_fn):
        by_date[p["date"]] = p
    for r in _read_rows():  # later real rows overwrite estimate + earlier rows
        d = str(r.get("date"))[:10]
        by_date[d] = {
            "date": d,
            "mrr": int(r.get("mrr") or 0),
            "active": int(r.get("active") or 0),
            "churn_pct": float(r.get("churn_pct") or 0.0),
            "ltv": int(r.get("ltv") or 0),
            "estimated": False,
        }
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days)).strftime("%Y-%m-%d")
    return sorted((p for d, p in by_date.items() if d >= cutoff), key=lambda x: x["date"])
