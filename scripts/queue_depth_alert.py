#!/usr/bin/env python3
"""Queue depth alert — monitor Celery queue + alert if > threshold.

Usage:
    python scripts/queue_depth_alert.py              # check + alert if needed
    python scripts/queue_depth_alert.py --prometheus # emit Prometheus metrics

Playbook ref: Queue System — every queue must have alert thresholds.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Thresholds per queue
ALERT_THRESHOLDS = {
    "celery": 100,
    "heavy": 50,
    "scraping": 30,
    "calling": 20,
    "reporting": 50,
    "sync": 30,
    "training": 20,
}


def _redis_client():
    try:
        import redis as _redis

        url = os.environ.get("REDIS_URL", "redis://redis:6379")
        return _redis.from_url(url, decode_responses=True)
    except Exception:
        return None


def check_queue_depth() -> dict[str, int]:
    """Return {queue_name: depth} for all Celery queues."""
    r = _redis_client()
    if not r:
        print("[WARN] Redis not available — cannot check queue depth")
        return {}

    depths = {}
    for queue, threshold in ALERT_THRESHOLDS.items():
        try:
            depth = r.llen(queue)
            depths[queue] = depth
        except Exception as e:
            print(f"[WARN] Could not check queue {queue}: {e}")
            depths[queue] = -1
    return depths


def emit_prometheus_metrics(depths: dict[str, int]) -> None:
    """Write Prometheus metrics to a text file for scraping."""
    metrics_dir = ROOT / "monitoring" / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    metrics_file = metrics_dir / "celery_queue_depth.prom"

    lines = [
        "# HELP celery_queue_depth Current depth of Celery queues",
        "# TYPE celery_queue_depth gauge",
    ]
    for queue, depth in depths.items():
        if depth >= 0:
            lines.append(f'celery_queue_depth{{queue="{queue}"}} {depth}')

    metrics_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[METRICS] Written to {metrics_file}")


def check_alerts(depths: dict[str, int]) -> list[str]:
    """Return list of alert messages for queues exceeding threshold."""
    alerts = []
    for queue, depth in depths.items():
        threshold = ALERT_THRESHOLDS.get(queue, 100)
        if depth > threshold:
            alerts.append(f"[ALERT] Queue '{queue}' depth={depth} > threshold={threshold}")
    return alerts


def main() -> int:
    args = sys.argv[1:]
    prometheus_mode = "--prometheus" in args

    print("[queue_depth_alert] Checking Celery queue depths...")
    print("=" * 60)

    depths = check_queue_depth()
    if not depths:
        print("[WARN] No queue data available")
        return 1

    for queue, depth in depths.items():
        threshold = ALERT_THRESHOLDS.get(queue, 100)
        status = "🔴 ALERT" if depth > threshold else "🟢 OK"
        print(f"  {queue:15s} depth={depth:4d}  threshold={threshold:4d}  {status}")

    if prometheus_mode:
        emit_prometheus_metrics(depths)

    alerts = check_alerts(depths)
    if alerts:
        print("\n" + "=" * 60)
        for a in alerts:
            print(a)
        print(f"[ALERT] {len(alerts)} queue(s) over threshold")
        return 1

    print("\n[OK] All queues within thresholds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
