#!/usr/bin/env python3
"""Vobiz cold-calling go-live smoke (run inside leadgen_app container).

Checks: env vars · readiness score · balance · compliance gate · optional dry-run.
Never prints secrets — only SET/missing + masked caller-id tail.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

_BASE = (
    "/app" if os.path.isdir("/app") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _BASE)
os.chdir(_BASE)

from dotenv import load_dotenv

load_dotenv(os.path.join(_BASE, ".env"), override=True)

IST = timezone(timedelta(hours=5, minutes=30))


def _mask(s: str, tail: int = 4) -> str:
    s = (s or "").strip()
    if not s:
        return "unset"
    if len(s) <= tail:
        return "***"
    return "*" * (len(s) - tail) + s[-tail:]


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


async def main() -> int:
    print("=== Vobiz Go-Live Smoke ===")
    print(f"at_ist: {datetime.now(IST).strftime('%Y-%m-%d %H:%M IST')}")

    keys = [
        "TELEPHONY_PROVIDER",
        "VOBIZ_AUTH_ID",
        "VOBIZ_AUTH_TOKEN",
        "VOBIZ_CALLER_ID",
        "VOBIZ_TRUNK_ID",
        "DLT_APPROVED",
        "GROQ_API_KEY",
        "COMPLIANCE_ENABLED",
    ]
    for k in keys:
        v = _env(k)
        if k.endswith("_TOKEN") or k.endswith("_KEY"):
            print(f"  {k}: {'SET' if v else 'MISSING'}")
        elif k == "VOBIZ_CALLER_ID":
            print(f"  {k}: {_mask(v, 4)}")
        else:
            print(f"  {k}: {v or 'MISSING'}")

    from app.telephony.telephony_readiness import run_checks

    rd = run_checks()
    print(f"\nreadiness_score: {rd.get('score')}/100")
    if rd.get("missing"):
        print(f"  missing: {', '.join(rd['missing'])}")
    for a in rd.get("actions") or []:
        print(f"  -> {a}")

    from app.telephony.vobiz_handler import VobizClient

    vc = VobizClient()
    print(f"\nvobiz_available: {vc.available()}")
    if vc.available():
        bal = await vc.get_balance()
        print(f"vobiz_balance: {bal.get('status_code')} {str(bal.get('body'))[:200]}")

    from app.telephony.compliance import CallType, get_compliance_gate

    gate = get_compliance_gate()
    sample = "+919876543210"
    promo = await gate.check(sample, CallType.PROMOTIONAL)
    txn = await gate.check(sample, CallType.TRANSACTIONAL)
    print(f"\ncompliance_promo_sample: allowed={promo.allowed} reasons={promo.reasons}")
    print(f"compliance_txn_sample:   allowed={txn.allowed} reasons={txn.reasons}")

    # Webhook health (in-process)
    try:
        from app.telephony.telephony_service import TelephonyService

        ts = TelephonyService()
        st = ts.status()
        print(
            f"\ntelephony_status: provider={st.get('provider')} configured={st.get('configured')}"
        )
    except Exception as e:
        print(f"\ntelephony_status: skip ({e})")

    ok = (
        vc.available()
        and bool(_env("VOBIZ_CALLER_ID"))
        and _env("DLT_APPROVED") in ("1", "true", "yes")
        and rd.get("score", 0) >= 80
    )
    print(f"\nGO_LIVE_READY: {'YES' if ok else 'NO'}")
    if not ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
