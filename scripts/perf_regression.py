#!/usr/bin/env python3
"""perf_regression.py — Stdlib-only HTTP latency regression checker.

HOW TO RUN:
    # First run — creates baseline at data/perf_baseline.json:
    python scripts/perf_regression.py

    # Subsequent runs — compares against baseline, exit 1 if p95 regressed >50%:
    python scripts/perf_regression.py

    # Against internal VPS endpoint (run on VPS or via SSH):
    BASE_URL=http://127.0.0.1:8000 python scripts/perf_regression.py

    # More iterations for stable numbers:
    PERF_N=20 python scripts/perf_regression.py

ENV VARS:
    BASE_URL        Target base URL (default: https://leadsgenai.in)
    PERF_N          Requests per endpoint per run (default: 10)
    PERF_THRESHOLD  Regression factor — 1.5 = 50% slower = FAIL (default: 1.5)
    PERF_BASELINE   Path to baseline JSON (default: data/perf_baseline.json)

SAFE: read-only GET requests only, never-crash on network error.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Config (overridable via env)
# ---------------------------------------------------------------------------
BASE_URL: str = os.environ.get("BASE_URL", "https://leadsgenai.in").rstrip("/")
N: int = int(os.environ.get("PERF_N", "10"))
THRESHOLD: float = float(os.environ.get("PERF_THRESHOLD", "1.5"))  # 1.5 = 50% regression
BASELINE_PATH: Path = Path(os.environ.get("PERF_BASELINE", "data/perf_baseline.json"))
REQUEST_TIMEOUT: int = 15  # seconds per request

# Endpoints to benchmark — (label, path) tuples
ENDPOINTS: list[tuple[str, str]] = [
    ("health", "/health"),
    ("niches", "/api/data/niches"),
    ("audit_page", "/audit"),
    ("home", "/"),
    ("blog", "/blog"),
    ("pricing", "/pricing"),
    ("sitemap", "/sitemap.xml"),
]


# ---------------------------------------------------------------------------
# Latency helpers
# ---------------------------------------------------------------------------
def _percentile(values: list[float], pct: float) -> float:
    """Sorted percentile (nearest rank)."""
    if not values:
        return 0.0
    sv = sorted(values)
    idx = max(0, min(int(round(pct / 100 * len(sv))) - 1, len(sv) - 1))
    return sv[idx]


def measure_endpoint(label: str, url: str, n: int) -> dict:
    """Hit `url` n times, return latency stats dict. Never raises."""
    durations: list[float] = []
    errors: int = 0

    for i in range(n):
        t0 = time.monotonic()
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "LeadGenAI-PerfRegression/1.0",
                    "Accept": "text/html,application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                _ = resp.read()  # consume body (realistic)
                status = resp.status
        except urllib.error.HTTPError as e:
            status = e.code
            errors += 1
        except Exception:
            status = 0
            errors += 1
        finally:
            elapsed_ms = (time.monotonic() - t0) * 1000

        # 4xx/5xx = error but still record latency (latency regression valid)
        if status not in (200, 201, 301, 302, 304):
            errors += 1
        durations.append(elapsed_ms)

        # Small pause to avoid hammering (not a load test — just regression check)
        time.sleep(0.1)

    p50 = _percentile(durations, 50)
    p95 = _percentile(durations, 95)
    p99 = _percentile(durations, 99)
    avg = sum(durations) / len(durations) if durations else 0.0

    return {
        "label": label,
        "url": url,
        "n": n,
        "errors": errors,
        "p50_ms": round(p50, 1),
        "p95_ms": round(p95, 1),
        "p99_ms": round(p99, 1),
        "avg_ms": round(avg, 1),
        "min_ms": round(min(durations), 1) if durations else 0.0,
        "max_ms": round(max(durations), 1) if durations else 0.0,
    }


# ---------------------------------------------------------------------------
# Baseline IO
# ---------------------------------------------------------------------------
def load_baseline(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"[WARN] Baseline load error ({path}): {e}")
        return None


def save_baseline(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"[INFO] Baseline saved → {path}")
    except Exception as e:
        print(f"[WARN] Could not save baseline: {e}")


# ---------------------------------------------------------------------------
# Comparison + reporting
# ---------------------------------------------------------------------------
def compare(current: dict, baseline: dict, threshold: float) -> tuple[bool, list[str]]:
    """Return (passed, list_of_regression_messages)."""
    regressions: list[str] = []

    for ep in current.get("endpoints", []):
        label = ep["label"]
        cur_p95 = ep["p95_ms"]

        # Find matching baseline endpoint
        base_ep = next(
            (b for b in baseline.get("endpoints", []) if b["label"] == label),
            None,
        )
        if base_ep is None:
            print(f"  [SKIP] {label}: naya endpoint, baseline me nahi — skipping comparison")
            continue

        base_p95 = base_ep["p95_ms"]
        if base_p95 <= 0:
            continue  # avoid division by zero

        ratio = cur_p95 / base_p95
        status_str = "OK  " if ratio <= threshold else "FAIL"
        print(
            f"  [{status_str}] {label:20s}  "
            f"p95: {cur_p95:7.1f}ms  (baseline: {base_p95:7.1f}ms,  ratio: {ratio:.2f}x)"
        )

        if ratio > threshold:
            regressions.append(
                f"{label}: p95 {cur_p95:.1f}ms vs baseline {base_p95:.1f}ms "
                f"({ratio:.2f}x > {threshold}x threshold)"
            )

    return (len(regressions) == 0), regressions


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    print("=" * 60)
    print("LeadGenAI — Performance Regression Check")
    print(f"BASE_URL  : {BASE_URL}")
    print(f"N per ep  : {N}")
    print(f"Threshold : {THRESHOLD}x (p95 regression limit)")
    print(f"Baseline  : {BASELINE_PATH}")
    print("=" * 60)

    # --- Measure current latencies ---
    results: list[dict] = []
    for label, path in ENDPOINTS:
        url = f"{BASE_URL}{path}"
        print(f"\nMeasuring [{label}] {url} (n={N})...")
        stat = measure_endpoint(label, url, N)
        results.append(stat)
        err_str = f"  errors={stat['errors']}" if stat["errors"] > 0 else ""
        print(
            f"  p50={stat['p50_ms']}ms  p95={stat['p95_ms']}ms  "
            f"p99={stat['p99_ms']}ms  avg={stat['avg_ms']}ms{err_str}"
        )

    current_snapshot = {
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_url": BASE_URL,
        "n": N,
        "endpoints": results,
    }

    # --- Load or create baseline ---
    baseline = load_baseline(BASELINE_PATH)

    if baseline is None:
        print("\n[INFO] Baseline nahi mila — current run ko baseline bana rahe hain.")
        save_baseline(BASELINE_PATH, current_snapshot)
        print("\nFirst run complete. Agle run me regression check chalega.")
        print("RESULT: BASELINE_CREATED")
        return 0

    # --- Compare ---
    print("\n" + "=" * 60)
    print(f"Comparing against baseline recorded at: {baseline.get('recorded_at', 'unknown')}")
    print("=" * 60)

    passed, regressions = compare(current_snapshot, baseline, THRESHOLD)

    print("\n" + "=" * 60)
    if passed:
        print("RESULT: PASS — koi p95 regression nahi (within threshold)")
    else:
        print("RESULT: FAIL — p95 regression detected:")
        for r in regressions:
            print(f"  ✗ {r}")
        print(f"\nBaseline update karna ho to: rm {BASELINE_PATH} aur script dobara chalao.")
    print("=" * 60)

    # Always write latest run alongside baseline for history
    latest_path = BASELINE_PATH.parent / "perf_latest.json"
    try:
        latest_path.parent.mkdir(parents=True, exist_ok=True)
        latest_path.write_text(json.dumps(current_snapshot, indent=2), encoding="utf-8")
    except Exception:
        pass

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
