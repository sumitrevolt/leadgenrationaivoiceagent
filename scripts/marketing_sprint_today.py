#!/usr/bin/env python3
"""One-shot marketing launch sprint — run inside leadgen_app container on VPS.

  docker exec leadgen_app python scripts/marketing_sprint_today.py

Checks env flags, live URL smoke, test inquiry + notify, email outreach fire, stats.
Secrets are never printed (only SET/UNSET).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PASS = "OK"
FAIL = "FAIL"
WARN = "WARN"
results: list[tuple[str, str, str]] = []


def log(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))
    mark = {"OK": "✓", "FAIL": "✗", "WARN": "?"}.get(status, "·")
    line = f"  [{mark}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)


def check_env() -> None:
    for key in ("NOTIFY_EMAIL", "AUTO_EMAIL_OUTREACH", "REPLY_AGENT", "UPI_VPA"):
        val = (os.environ.get(key) or "").strip()
        if val:
            log(PASS, f"env {key}", "SET")
        else:
            log(FAIL, f"env {key}", "UNSET — .env me set karo + app recreate")


def check_live_urls() -> None:
    import urllib.request

    base = (os.environ.get("PUBLIC_BASE_URL") or "https://leadsgenai.in").rstrip("/")
    checks = [
        ("/health", "production"),
        ("/voice-agent", "flat monthly"),
        ("/compare", "flat monthly"),
        ("/demo", "/voice-agent"),
        ("/audit", "audit"),
        ("/api/voice/packages", "flat_monthly"),
        ("/api/activation/summary", "production_ready"),
        ("/sitemap.xml", "urlset"),
        ("/api/public/pay-info", "enabled"),
    ]
    for path, needle in checks:
        url = base + path
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "marketing-sprint/1.0"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                body = resp.read(120_000).decode("utf-8", errors="replace")
            if needle.lower() in body.lower():
                log(PASS, f"GET {path}", f"contains '{needle}'")
            else:
                log(FAIL, f"GET {path}", f"missing '{needle}'")
        except Exception as exc:
            log(FAIL, f"GET {path}", str(exc)[:120])


async def test_inquiry() -> None:
    """Submit test inquiry — direct store path (container me localhost:8000 often unreachable)."""

    rec = {
        "id": str(uuid.uuid4()),
        "at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "name": "Sprint Test",
        "business_name": "LeadGen Sprint QA",
        "phone": "9876543210",
        "niche": "solar_residential",
        "city": "Pune",
        "message": f"marketing_sprint_today.py auto-test {datetime.now(timezone.utc).isoformat()}",
        "package": "growth",
        "source": "website",
        "ip": "127.0.0.1",
    }
    try:
        from app.api import public_site as ps

        stored = ps._append_jsonl(rec)
        lead_id = ps._save_lead_db(rec)
        if lead_id:
            rec["lead_id"] = lead_id
        # Owner notify (best-effort)
        try:
            await ps._notify_inquiry_email(dict(rec))
        except Exception:
            pass
        if stored or lead_id:
            log(PASS, "inquiry store", f"file={stored} db={bool(lead_id)}")
        else:
            log(FAIL, "inquiry store", "jsonl+db both failed")
            return
    except Exception as exc:
        log(FAIL, "inquiry store", str(exc)[:120])
        return

    # Verify jsonl tail
    path = os.path.join("data", "inquiries.jsonl")
    try:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                lines = [ln for ln in f.readlines() if ln.strip()]
            if lines:
                last = json.loads(lines[-1])
                if last.get("name") == "Sprint Test":
                    log(PASS, "inquiry jsonl", f"id={last.get('id', '')[:8]}…")
                else:
                    log(WARN, "inquiry jsonl", "last row is not sprint test (maybe race)")
            else:
                log(WARN, "inquiry jsonl", "empty file")
        else:
            log(WARN, "inquiry jsonl", "file missing")
    except Exception as exc:
        log(WARN, "inquiry jsonl", str(exc)[:80])


async def fire_outreach() -> None:
    if os.environ.get("AUTO_EMAIL_OUTREACH", "").strip().lower() not in ("1", "true", "yes", "on"):
        log(WARN, "email outreach", "AUTO_EMAIL_OUTREACH off — skip")
        return
    try:
        from app.platform import auto_outreach

        out = await auto_outreach.run_email_outreach()
        sent = out.get("sent") if isinstance(out, dict) else None
        skipped = out.get("skipped") if isinstance(out, dict) else None
        err = out.get("error") if isinstance(out, dict) else None
        if err:
            log(WARN, "email outreach run", str(err)[:100])
        else:
            log(PASS, "email outreach run", f"sent={sent} skipped={skipped}")
        stats = auto_outreach.outreach_stats()
        log(PASS, "outreach stats", json.dumps(stats, ensure_ascii=False)[:200])
    except Exception as exc:
        log(FAIL, "email outreach run", str(exc)[:150])


async def check_reply_agent() -> None:
    on = os.environ.get("REPLY_AGENT", "").strip().lower() in ("1", "true", "yes", "on")
    if not on:
        log(WARN, "reply_agent", "REPLY_AGENT off")
        return
    try:
        from app.platform import reply_agent

        log(PASS, "reply_agent module", "import OK")
    except Exception as exc:
        log(FAIL, "reply_agent module", str(exc)[:100])


async def main() -> int:
    print("=== Marketing Sprint Today ===\n")
    check_env()
    print()
    check_live_urls()
    print()
    await test_inquiry()
    print()
    await fire_outreach()
    print()
    await check_reply_agent()
    print()
    fails = sum(1 for s, _, _ in results if s == FAIL)
    warns = sum(1 for s, _, _ in results if s == WARN)
    print(f"=== SUMMARY: {fails} FAIL, {warns} WARN, {len(results) - fails - warns} OK ===")
    print("\nManual (tumhe): GSC sitemap submit · WA 10 contacts · 1 social post")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
