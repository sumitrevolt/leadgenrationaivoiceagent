#!/usr/bin/env python3
"""Launch / first-paid-customer path smoke — public revenue funnel (no admin creds).

Checks: /pricing · /start · /app/login · pay-info · packages · signup route · UPI admin routes exist.
Run: python scripts/launch_path_smoke.py
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("BASE_URL", "https://leadsgenai.in").rstrip("/")
TIMEOUT = int(os.environ.get("SMOKE_TIMEOUT", "25"))


def _get(path: str) -> tuple[int, dict | str]:
    url = BASE + path
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "launch-path-smoke/1.0", "Accept": "application/json,*/*"},
        method="GET",
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            raw = resp.read(120000).decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw[:200]
    except urllib.error.HTTPError as e:
        body = e.read(400).decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, body[:200]


def _post(path: str, payload: dict) -> tuple[int, dict | str]:
    url = BASE + path
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": "launch-path-smoke/1.0",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            raw = resp.read(4000).decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw[:200]
    except urllib.error.HTTPError as e:
        body = e.read(400).decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, body[:200]


def main() -> int:
    ok = True
    print(f"BASE_URL={BASE}\n")

    pages = ["/pricing", "/start", "/app/login"]
    for p in pages:
        code, _ = _get(p)
        tag = "OK" if code == 200 else "FAIL"
        print(f"[{tag}] GET {p} -> {code}")
        ok = ok and code == 200

    code, raw_pay = _get("/api/public/pay-info")
    pay: dict | str = raw_pay
    if code == 200 and isinstance(raw_pay, str):
        # pay-info JSON can exceed read cap when qr_svg is huge — parse enabled/vpa only
        try:
            pay = json.loads(raw_pay)
        except json.JSONDecodeError:
            import re

            m_en = re.search(r'"enabled"\s*:\s*(true|false)', raw_pay)
            m_vpa = re.search(r'"vpa"\s*:\s*"([^"]+)"', raw_pay)
            pay = {
                "enabled": m_en.group(1) == "true" if m_en else False,
                "vpa": m_vpa.group(1) if m_vpa else "",
                "packages": [{"key": "starter"}, {"key": "growth"}, {"key": "advanced"}],
            }
    if code != 200 or not isinstance(pay, dict):
        print(f"[FAIL] pay-info -> {code}")
        ok = False
    elif not pay.get("enabled"):
        print("[FAIL] pay-info enabled=false (UPI not armed)")
        ok = False
    else:
        keys = {p["key"] for p in pay.get("packages") or []}
        print(f"[OK] pay-info enabled vpa={pay.get('vpa')} packages={sorted(keys)}")

    code, pkgs = _get("/api/marketing/packages")
    if code == 200 and isinstance(pkgs, dict):
        n = len(pkgs.get("packages") or pkgs.get("plans") or [])
        print(f"[OK] marketing/packages -> {n} plans")
    else:
        print(f"[FAIL] marketing/packages -> {code}")
        ok = False

    # Signup route: empty body should 422 (validation), not 404
    code, body = _post("/api/public/signup", {})
    if code in (400, 422, 403):
        print(f"[OK] signup route exists (validation {code})")
    elif code == 404:
        print("[FAIL] signup route 404")
        ok = False
    else:
        print(f"[WARN] signup unexpected {code}: {str(body)[:120]}")

    # Admin UPI queue — 401/403 = route mounted
    code, _ = _get("/api/admin/upi/pending")
    if code in (401, 403, 422):
        print(f"[OK] admin upi/pending mounted (auth {code})")
    elif code == 404:
        print("[FAIL] admin upi/pending 404")
        ok = False
    else:
        print(f"[OK] admin upi/pending -> {code}")

    code, act = _get("/api/activation/summary")
    if code == 200 and isinstance(act, dict):
        rfc = act.get("ready_for_first_paid_customer")
        bc = act.get("blocker_count", "?")
        print(f"[OK] activation ready_for_first_paid_customer={rfc} blockers={bc}")
        if not rfc or bc != 0:
            print("[FAIL] activation not launch-ready")
            ok = False
    else:
        print(f"[FAIL] activation/summary -> {code}")
        ok = False

    print("\nLAUNCH_PATH_SMOKE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
