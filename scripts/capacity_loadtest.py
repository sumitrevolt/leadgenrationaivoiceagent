#!/usr/bin/env python3
"""Off-peak public ramp against /health and /. Never /audit (writes). Never from VPS.

Default is a tiny 5-concurrent / 10s probe. Use --knee only off-peak after
pausing Uptime alerts. Safe limit = 60% of knee (p95 2x or errors >1%).
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "evidence" / "capacity_loadtest.json"


def _one(url: str, timeout: float) -> tuple[int, float]:
    t0 = time.perf_counter()
    try:
        if not url.startswith(("https://", "http://")):
            return 0, time.perf_counter() - t0
        req = urllib.request.Request(
            url, method="GET", headers={"User-Agent": "leadgen-capacity/1"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            resp.read(64)
            return int(resp.status), time.perf_counter() - t0
    except urllib.error.HTTPError as exc:
        return int(exc.code), time.perf_counter() - t0
    except Exception:
        return 0, time.perf_counter() - t0


def ramp(url: str, concurrency: int, duration_s: float, timeout: float) -> dict:
    latencies: list[float] = []
    codes: dict[int, int] = {}
    deadline = time.perf_counter() + duration_s

    def worker():
        while time.perf_counter() < deadline:
            code, sec = _one(url, timeout)
            latencies.append(sec)
            codes[code] = codes.get(code, 0) + 1

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futs = [pool.submit(worker) for _ in range(concurrency)]
        for fut in as_completed(futs):
            fut.result()
    latencies.sort()
    n = len(latencies) or 1
    errors = sum(c for code, c in codes.items() if code == 0 or code >= 500)
    p50 = latencies[min(len(latencies) - 1, int(0.50 * n))] if latencies else 0
    p95 = latencies[min(len(latencies) - 1, int(0.95 * n))] if latencies else 0
    p99 = latencies[min(len(latencies) - 1, int(0.99 * n))] if latencies else 0
    mean = statistics.fmean(latencies) if latencies else 0
    return {
        "url": url,
        "concurrency": concurrency,
        "duration_s": duration_s,
        "n": len(latencies),
        "p50_s": round(p50, 4),
        "p95_s": round(p95, 4),
        "p99_s": round(p99, 4),
        "mean_s": round(mean, 4),
        "error_n": errors,
        "error_pct": round(100.0 * errors / n, 3),
        "codes": {str(k): v for k, v in sorted(codes.items())},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://leadsgenai.in")
    ap.add_argument("--knee", action="store_true", help="5→20→50 ramp; default is 5/10s only")
    args = ap.parse_args()
    targets = [f"{args.base.rstrip('/')}/health", f"{args.base.rstrip('/')}/"]
    levels = [5, 20, 50] if args.knee else [5]
    duration = 15.0 if args.knee else 10.0
    rows = []
    for url in targets:
        for c in levels:
            rows.append(ramp(url, c, duration, timeout=8.0))
    out = {
        "probed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": "Did not hit /audit or /start POST. Safe limit = 60% of knee.",
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
