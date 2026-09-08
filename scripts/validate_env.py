#!/usr/bin/env python3
"""Deploy-safety env validator — revenue-path readiness ek nazar me, BEFORE recreate.

Kyun: `config.validate_production_settings` sirf secret_key/jwt/debug check karta (fatal).
Operational revenue config (UPI armed? SMTP set? DB set?) deploy pe silently degrade ho
sakta — server boot ho jaata, par `/api/billing` ya signup pehli baar use pe break.
Yeh script woh gap dikhata: prod me HARD-missing secret = exit 1 (block deploy); revenue/
ops config missing = WARN (visible, par block nahi). Request-path me kuch NAHI — pure CLI,
zero runtime risk.

Usage:
  python scripts/validate_env.py            # report (exit 1 only on fatal prod secret gap)
  python scripts/validate_env.py --strict   # WARN bhi failure (exit 1) — strict deploy gate
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    strict = "--strict" in sys.argv
    try:
        from app.config import settings
    except Exception as e:  # config itself raised (e.g. prod secret check) — fatal
        print(f"[validate_env] FATAL: config load failed: {e}")
        return 1

    is_prod = getattr(settings, "is_production", False)
    fatal: list[str] = []
    warn: list[str] = []
    ok: list[str] = []

    def check(label: str, value: object, *, fatal_in_prod: bool = False) -> None:
        present = bool(str(value or "").strip())
        if present:
            ok.append(label)
        elif fatal_in_prod and is_prod:
            fatal.append(label)
        else:
            warn.append(label)

    # --- Secrets (fatal in prod if default/unset) ---
    sk = getattr(settings, "secret_key", "")
    jwt = getattr(settings, "jwt_secret_key", "")
    if is_prod and sk in ("", "change-this-in-production"):
        fatal.append("secret_key (default/unset)")
    else:
        ok.append("secret_key")
    if is_prod and jwt in ("", "change-this-jwt-secret-in-production"):
        fatal.append("jwt_secret_key (default/unset)")
    else:
        ok.append("jwt_secret_key")

    # --- Revenue path: UPI (primary payment rail) ---
    upi_vpa = ""
    try:
        from app.platform import upi_config

        upi_vpa = upi_config.get_vpa() if hasattr(upi_config, "get_vpa") else ""
    except Exception:
        upi_vpa = getattr(settings, "upi_vpa", "") or ""
    check("UPI_VPA (revenue path / pay-info)", upi_vpa, fatal_in_prod=False)

    # --- Ops/automation config (degrade = WARN) ---
    check("DATABASE_URL (Postgres)", getattr(settings, "database_url", ""))
    check(
        "SMTP host (email outreach)",
        getattr(settings, "smtp_host", "") or getattr(settings, "smtp_server", ""),
    )
    check("GROQ_API_KEY (STT)", getattr(settings, "groq_api_key", ""))
    check("SENTRY_DSN (error capture)", getattr(settings, "sentry_dsn", ""))

    # --- Report ---
    env_name = "production" if is_prod else "development"
    print(f"[validate_env] env={env_name}")
    print(f"  OK   ({len(ok)}): {', '.join(ok)}")
    if warn:
        print(f"  WARN ({len(warn)}): {', '.join(warn)}")
    if fatal:
        print(f"  FATAL ({len(fatal)}): {', '.join(fatal)}")

    if fatal:
        print("[validate_env] FAIL — fatal config gap (prod secret). Deploy BLOCK.")
        return 1
    if warn and strict:
        print("[validate_env] FAIL (--strict) — revenue/ops config WARN treated as gate.")
        return 1
    print("[validate_env] PASS" + (" (with warnings)" if warn else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
