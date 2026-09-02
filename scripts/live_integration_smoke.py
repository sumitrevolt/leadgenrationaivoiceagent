#!/usr/bin/env python3
"""Live production smoke — pages 200 + workflow APIs registered (not 404).

Runs against BASE_URL (default https://leadsgenai.in).
Auth-required routes: 401/403/422/405 = OK (route exists). 404 = FAIL.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = os.environ.get("BASE_URL", "https://leadsgenai.in").rstrip("/")
TIMEOUT = int(os.environ.get("SMOKE_TIMEOUT", "20"))

PUBLIC_PAGES = [
    "/",
    "/health",
    "/health/ready",
    "/audit",
    "/site-audit",
    "/pricing",
    "/start",
    "/blog",
    "/compare",
    "/demo",
    "/status",
    "/app/admin",
    "/app/admin-login",
    "/app/customer",
    "/app/login",
    "/app/automation",
    "/app/marketing",
    "/app/clients",
    "/app/outreach",
    "/app/team",
    "/app/test-call",
    "/app/growth-tools",
    "/app/dashboards",
    "/app/battlecard",
    "/robots.txt",
    "/sitemap.xml",
]

# All Automation Hub workflow POST endpoints (admin_dashboard autoAction map).
WORKFLOW_POSTS = [
    "/api/growth/selfimprove/run",
    "/api/growth/optimizer/run",
    "/api/growth/niche/scrape",
    "/api/platform/team/email-outreach/run",
    "/api/growth/revenue/dunning/run",
    "/api/growth/revenue/digest/run",
    "/api/growth/revenue/health/run",
    "/api/growth/harvest/run",
    "/api/growth/cadence/run",
    "/api/growth/revenue/lifecycle/run",
    "/api/platform/team/email-followups/run",
    "/api/platform/team/reply-triage/run",
    "/api/platform/team/run/isha",
    "/api/platform/team/run/blog",
    "/api/platform/team/growth/run",
    "/api/growth/reviews/monitor-run",
    "/api/journeys/emit",
    "/api/growth/sales/team-run?limit=1",
    "/api/growth/upgrader/scan",
    "/api/platform/team/run/arjun",
    "/api/platform/team/prospects/run",
]

CRITICAL_GETS = [
    "/api/admin/system/summary",
    "/api/growth/infra/automation-health",
    "/api/growth/overview/today",
    "/api/clientops/approvals",
    "/api/growth/selfimprove/approvals-pending",
    "/api/growth/process/runs",
    "/api/marketing/packages",
    "/api/voice/packages",
]


def _req(method: str, path: str, body: bytes | None = None, *, tries: int = 3) -> tuple[int, str]:
    # Retry+backoff on throttle (429) and connection blips (-1) — the smoke fires
    # ~55 rapid requests and can trip the per-IP rate limiter, plus Docker-recreate
    # windows cause transient blips. Mirrors the uptime probe hardening (ee6a9b8):
    # absorb transient noise, only surface a persistent state.
    url = BASE + path
    headers = {"User-Agent": "leadgen-live-smoke/1.0", "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    ctx = ssl.create_default_context()
    last: tuple[int, str] = (-1, "")
    for attempt in range(tries):
        r = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(r, timeout=TIMEOUT, context=ctx) as resp:
                return resp.status, resp.read(500).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            last = (e.code, (e.read(300).decode("utf-8", errors="replace") if e.fp else ""))
            if e.code != 429:  # 429 = our own burst tripped the limiter — back off and retry
                return last
        except Exception as e:
            last = (-1, str(e)[:200])
        if attempt < tries - 1:
            time.sleep(2 * (attempt + 1))  # 2s, 4s backoff
    return last


def _extract_admin_workflows() -> list[str]:
    html = (ROOT / "frontend/admin_dashboard.html").read_text(encoding="utf-8", errors="ignore")
    urls = re.findall(r'url:"(/api/[^"]+)"', html)
    # only autoAction map block — filter growth/team/journeys
    return sorted({u.split("?")[0] for u in urls if "/api/" in u})


def main() -> int:
    print(f"=== LIVE INTEGRATION SMOKE @ {BASE} ===\n")
    fails: list[str] = []

    # 1) Public pages — 200 = rendered; 429 = alive but probe-throttled (self-inflicted
    #    burst, not a broken page) → WARN, non-fatal (consistent with the API checks below).
    print("## Public pages")
    for p in PUBLIC_PAGES:
        code, _ = _req("GET", p)
        ok = code in (200, 429)
        label = "OK" if code == 200 else ("WARN" if code == 429 else "FAIL")
        print(f"  {label} {code:>4} GET {p}")
        if not ok:
            fails.append(f"page {p} -> {code}")

    # 2) Health JSON
    print("\n## Health")
    code, body = _req("GET", "/health")
    if code == 200:
        try:
            h = json.loads(body)
            env = h.get("environment", "")
            print(f"  OK environment={env} status={h.get('status')}")
            if env != "production" and "127.0.0.1" not in BASE:
                fails.append(f"health environment={env} (expected production)")
        except json.JSONDecodeError:
            fails.append("health invalid json")
    elif code == 429:
        print("  WARN 429 health throttled (alive) — probe tripped rate limit, not down")
    else:
        fails.append(f"health -> {code}")

    # 3) Workflow POSTs (no auth — must NOT 404)
    print("\n## Automation workflow APIs (POST, no auth)")
    body = b"{}"
    for path in WORKFLOW_POSTS:
        code, _ = _req("POST", path, body)
        ok = code not in (-1, 404)
        print(f"  {'OK' if ok else 'FAIL'} {code:>4} POST {path}")
        if not ok:
            fails.append(f"workflow POST {path} -> {code}")

    # 4) Critical admin GETs
    print("\n## Critical admin APIs (GET, no auth)")
    for path in CRITICAL_GETS:
        code, _ = _req("GET", path)
        # Route-exists semantics: auth (401/403), method/validation (405/422),
        # rate-limit (429 = alive, just throttled) all prove the route is wired.
        # Only connection-error/404/5xx are real failures.
        ok = code in (200, 401, 403, 405, 422, 429)
        print(f"  {'OK' if ok else 'FAIL'} {code:>4} GET {path}")
        if not ok:
            fails.append(f"critical GET {path} -> {code}")

    # 5) Cross-check admin HTML URLs vs local routes
    print("\n## Admin HTML API refs vs local FastAPI")
    sys.path.insert(0, str(ROOT))
    from scripts.deep_wiring_audit import load_routes, route_exists

    routes = load_routes()
    html_apis = _extract_admin_workflows()
    missing = [p for p in html_apis if not route_exists(p, routes)]
    if missing:
        for p in missing:
            print(f"  FAIL missing route {p}")
            fails.append(f"admin html api {p}")
    else:
        print(f"  OK {len(html_apis)} admin workflow URLs registered locally")

    print(f"\n=== LIVE SMOKE SUMMARY: {len(fails)} failures ===")
    for f in fails:
        print(f"  - {f}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
