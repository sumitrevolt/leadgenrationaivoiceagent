#!/usr/bin/env python3
"""Bounded 20-minute production burn-in — replaces 24h soak as launch gate.

Read-only probes. Never mutates flags, never dials, never sends.
Exit 0 = burn-in PASS; non-zero = FAIL (do not GO).

  python3 scripts/prod_burn_in.py --minutes 20 --base-url https://leadsgenai.in
  python3 scripts/prod_burn_in.py --minutes 1 --once   # single sample (CI/local)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _get(url: str, timeout: float = 20.0) -> tuple[int, str]:
    if not url.startswith(("https://", "http://")):
        return 0, "ValueError:url_scheme_not_allowed"
    req = urllib.request.Request(url, headers={"User-Agent": "leadgen-burn-in/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 — scheme gated above
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return int(e.code), body
    except Exception as e:
        return 0, f"{type(e).__name__}:{e}"


def _sample(base: str) -> dict:
    out: dict = {"at": _utc()}
    code, body = _get(f"{base}/health")
    out["health_code"] = code
    try:
        h = json.loads(body) if body.startswith("{") else {}
    except Exception:
        h = {}
    out["version"] = h.get("version")
    out["status"] = h.get("status")
    out["environment"] = h.get("environment")
    code2, body2 = _get(f"{base}/health/ready")
    out["ready_code"] = code2
    try:
        r = json.loads(body2) if body2.startswith("{") else {}
    except Exception:
        r = {}
    out["ready_status"] = r.get("status")
    checks = r.get("checks") or {}
    out["db"] = (checks.get("database") or {}).get("status")
    out["redis"] = (checks.get("redis") or {}).get("status")
    code3, body3 = _get(f"{base}/api/activation/summary")
    out["activation_code"] = code3
    try:
        a = json.loads(body3) if body3.startswith("{") else {}
    except Exception:
        a = {}
    out["ready_for_launch"] = a.get("ready_for_launch")
    out["blocker_count"] = a.get("blocker_count")
    out["payments_ready"] = a.get("payments_ready")
    for path in ("/pricing", "/start", "/api/billing/plans", "/api/public/pay-info"):
        c, _ = _get(f"{base}{path}")
        out[f"http_{path}"] = c
    return out


def _ok_sample(s: dict, expect_version: str | None) -> list[str]:
    fails = []
    if s.get("health_code") != 200 or s.get("status") != "healthy":
        fails.append("health")
    if s.get("environment") != "production":
        fails.append("environment")
    if expect_version and s.get("version") != expect_version:
        fails.append(f"version_skew:{s.get('version')}!={expect_version}")
    if s.get("ready_code") != 200 or s.get("ready_status") != "healthy":
        fails.append("ready")
    if s.get("db") != "healthy" or s.get("redis") != "healthy":
        fails.append("db_or_redis")
    if s.get("activation_code") != 200 or s.get("ready_for_launch") is not True:
        fails.append("activation")
    bc = s.get("blocker_count")
    if bc is None or int(bc) != 0:
        fails.append("blockers")
    if s.get("payments_ready") is not True:
        fails.append("payments")
    for path in ("/pricing", "/start", "/api/billing/plans", "/api/public/pay-info"):
        if s.get(f"http_{path}") != 200:
            fails.append(path)
    return fails


def main() -> int:
    ap = argparse.ArgumentParser(description="LeadGen 20-minute production burn-in")
    ap.add_argument("--minutes", type=float, default=20.0)
    ap.add_argument("--interval-sec", type=float, default=60.0)
    ap.add_argument("--base-url", default="https://leadsgenai.in")
    ap.add_argument("--expect-version", default="")
    ap.add_argument("--once", action="store_true", help="Single sample then exit")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    first = _sample(base)
    expect = (args.expect_version or first.get("version") or "").strip() or None
    fails = _ok_sample(first, expect)
    samples = [first]
    print(json.dumps({"event": "burn_in_start", "sample": first, "fails": fails}, indent=2))
    if fails:
        print("BURN_IN_FAIL immediate", fails, file=sys.stderr)
        return 2
    if args.once:
        print("BURN_IN_PASS once", expect)
        return 0

    deadline = time.time() + max(60.0, args.minutes * 60.0)
    while time.time() < deadline:
        time.sleep(max(5.0, args.interval_sec))
        s = _sample(base)
        samples.append(s)
        f = _ok_sample(s, expect)
        print(
            json.dumps(
                {"event": "burn_in_tick", "at": s["at"], "version": s.get("version"), "fails": f}
            )
        )
        if f:
            print("BURN_IN_FAIL", f, file=sys.stderr)
            if args.out:
                open(args.out, "w", encoding="utf-8").write(
                    json.dumps({"ok": False, "fails": f, "samples": samples}, indent=2)
                )
            return 3

    result = {
        "ok": True,
        "expect_version": expect,
        "samples": len(samples),
        "started": samples[0]["at"],
        "ended": samples[-1]["at"],
        "policy": "20m_burn_in_replaces_24h_soak",
    }
    print(json.dumps({"event": "burn_in_pass", **result}, indent=2))
    print(f"BURN_IN_PASS {expect} samples={len(samples)}")
    if args.out:
        open(args.out, "w", encoding="utf-8").write(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
