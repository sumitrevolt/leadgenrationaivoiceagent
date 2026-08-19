#!/usr/bin/env python3
"""Diagnostic: email outreach pipeline health check.

Run on VPS: python3 scripts/check_outreach_pipeline.py

Checks:
1. AUTO_EMAIL_OUTREACH flag state
2. SMTP/API config
3. Prospect store (count, ready, emailed, dead, with_email)
4. Email warmup state (pause expiry check)
5. Daily send count vs cap
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone


def _check(name: str, ok: bool, detail: str) -> str:
    icon = "PASS" if ok else "FAIL"
    return f"[{icon}] {name}: {detail}"


def _is_warmup_paused(state: dict) -> bool:
    """Check if warmup is CURRENTLY paused (paused_until > now)."""
    raw = str(state.get("paused_until") or "")
    if not raw:
        return False
    try:
        until = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) < until
    except Exception:
        return False


def main() -> None:
    results: list[str] = []
    warnings: list[str] = []

    # -- 1. Flags --
    auto_outreach = os.environ.get("AUTO_EMAIL_OUTREACH", "").strip()
    sales_autopilot = os.environ.get("SALES_AUTOPILOT_ENABLED", "").strip()
    email_warmup = os.environ.get("EMAIL_WARMUP", "").strip()
    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_pass = os.environ.get("SMTP_PASSWORD", "").strip()
    resend_key = os.environ.get("RESEND_API_KEY", "").strip()
    brevo_key = os.environ.get("BREVO_API_KEY", "").strip()

    results.append(
        _check(
            "AUTO_EMAIL_OUTREACH",
            auto_outreach in ("1", "true", "yes"),
            f"={auto_outreach!r}"
            + (" (OUTREACH WILL SKIP)" if auto_outreach not in ("1", "true", "yes") else ""),
        )
    )
    results.append(
        _check(
            "SALES_AUTOPILOT_ENABLED",
            sales_autopilot in ("1", "true", "yes"),
            f"={sales_autopilot!r}"
            + (" (PROSPECT REFILL OFF)" if sales_autopilot not in ("1", "true", "yes") else ""),
        )
    )
    results.append(
        _check(
            "EMAIL_WARMUP",
            email_warmup in ("1", "true", "yes"),
            f"={email_warmup!r}"
            + (" (NO WARMUP RAMP)" if email_warmup not in ("1", "true", "yes") else ""),
        )
    )

    has_api = bool(resend_key or brevo_key)
    has_smtp = bool(smtp_user and smtp_pass)
    provider = "api" if has_api else ("smtp" if has_smtp else "none")
    results.append(
        _check(
            "Email provider",
            has_api or has_smtp,
            f"provider={provider} api={'yes' if has_api else 'no'} smtp={'yes' if has_smtp else 'no'}"
            + (" (NO EMAIL PROVIDER -- EMAILS WILL NOT SEND)" if not (has_api or has_smtp) else ""),
        )
    )

    # -- 2. Prospect store --
    prospects_path = None
    for candidate in [
        os.environ.get("LEADGEN_RUNTIME_DATA_ROOT", "") + "/sales/prospects.jsonl",
        "data/prospects.jsonl",
        "/var/lib/leadgen/runtime/data/prospects.jsonl",
    ]:
        if candidate and os.path.isfile(candidate):
            prospects_path = candidate
            break

    if prospects_path:
        try:
            with open(prospects_path, encoding="utf-8") as f:
                all_rows = [json.loads(ln) for ln in f if ln.strip()]
            total = len(all_rows)
            ready = sum(1 for r in all_rows if str(r.get("status") or "ready") == "ready")
            emailed = sum(1 for r in all_rows if r.get("emailed_at"))
            dead = sum(1 for r in all_rows if str(r.get("status") or "") == "dead")
            with_email = sum(1 for r in all_rows if str(r.get("email") or "").strip())
            results.append(
                _check(
                    "Prospect store",
                    True,
                    f"total={total} ready={ready} emailed={emailed} dead={dead} with_email={with_email} path={prospects_path}",
                )
            )
            emailable = sum(
                1
                for r in all_rows
                if str(r.get("status") or "ready") == "ready"
                and str(r.get("email") or "").strip()
                and not r.get("emailed_at")
            )
            results.append(
                _check(
                    "Emailable ready prospects",
                    emailable > 0,
                    f"count={emailable} (ready + has email + not yet emailed)",
                )
            )
            if ready == 0:
                warnings.append(
                    "NO ready prospects -- harvest may not be running or all prospects processed."
                )
            if ready > 0 and with_email == 0:
                warnings.append("Ready prospects exist but NONE have email addresses.")
            if emailable == 0 and ready > 0:
                warnings.append("All ready prospects already emailed or lack email addresses.")
        except Exception as e:
            results.append(_check("Prospect store", False, f"read error: {e}"))
    else:
        results.append(_check("Prospect store", False, "prospects.jsonl not found"))
        warnings.append("Prospect file missing.")

    # -- 3. Email warmup state --
    warmup_path = os.path.join("data", "email_warmup.json")
    if os.path.isfile(warmup_path):
        try:
            with open(warmup_path, encoding="utf-8") as f:
                wu = json.load(f)
            is_paused = _is_warmup_paused(wu)
            paused_until = wu.get("paused_until") or "none"
            sent_events = wu.get("sent_events") or []
            bounce_events = wu.get("bounce_events") or []
            start_date = wu.get("start_date") or "?"
            results.append(
                _check(
                    "Email warmup",
                    not is_paused,
                    f"start={start_date} sent_events={len(sent_events)} bounce_events={len(bounce_events)} paused_until={paused_until} currently_paused={is_paused}",
                )
            )
            if is_paused:
                warnings.append(f"Warmup PAUSED until {paused_until} -- all emails blocked.")
        except Exception as e:
            results.append(_check("Email warmup", False, f"read error: {e}"))
    else:
        results.append(_check("Email warmup", True, "no state file (warmup OFF = cap = base)"))

    # -- 4. Daily send count --
    for log_name in ["email_outreach_log.jsonl", "email_send_log.jsonl"]:
        log_path = os.path.join("data", log_name)
        if os.path.isfile(log_path):
            try:
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                with open(log_path, encoding="utf-8") as f:
                    today_sends = sum(
                        1
                        for ln in f
                        if ln.strip() and json.loads(ln).get("at", "").startswith(today)
                    )
                daily_cap = int(os.environ.get("OUTREACH_DAILY_CAP", "25"))
                results.append(
                    _check(
                        "Daily sends today",
                        True,
                        f"sent={today_sends} cap={daily_cap} file={log_name}",
                    )
                )
                if today_sends >= daily_cap:
                    warnings.append(f"Daily cap reached ({today_sends}/{daily_cap}).")
                break
            except Exception as e:
                results.append(_check("Daily sends", False, f"read error: {e}"))
                break
    else:
        results.append(_check("Daily sends", True, "no outreach log found"))

    # -- Output --
    print("=" * 60)
    print("EMAIL OUTREACH PIPELINE DIAGNOSTIC")
    print("=" * 60)
    for r in results:
        print(r)
    if warnings:
        print("\n--- WARNINGS ---")
        for w in warnings:
            print(f"  WARNING: {w}")
    print("\n" + "=" * 60)

    has_blocker = any("[FAIL]" in r for r in results)
    has_warning = bool(warnings)
    if has_blocker:
        print("VERDICT: PIPELINE BLOCKED -- outreach will NOT send emails.")
        print("ACTION: Fix the FAIL items above, then re-run this script.")
    elif has_warning:
        print("VERDICT: PIPELINE DEGRADED -- outreach may send but conditions suboptimal.")
    else:
        print("VERDICT: PIPELINE HEALTHY -- outreach should be sending.")
    print("=" * 60)


if __name__ == "__main__":
    main()
