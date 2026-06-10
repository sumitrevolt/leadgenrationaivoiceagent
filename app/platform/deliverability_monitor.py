"""Deliverability / blacklist monitor (Smartlead-pattern, free DNS-based).

Cold-email engine ki sender reputation hi sab kuch hai. Yeh monitor roz check
karta: (1) domain ke SPF/DMARC TXT records intact hain, (2) VPS IP kisi DNSBL
(Spamhaus ZEN, SpamCop) me listed to nahi. Problem mile to NOTIFY_EMAIL pe alert
(gated `DELIVERABILITY_MONITOR=1`; off = silent check, store-only).

Pure DNS lookups (dnspython — email-validator ke saath pehle se installed).
Store: data/deliverability_checks.jsonl. Import-safe, kabhi raise nahi.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_LOG = os.path.join("data", "deliverability_checks.jsonl")
DOMAIN = os.environ.get("OUTREACH_DOMAIN", "leadsgenai.in")
_DNSBLS = ["zen.spamhaus.org", "bl.spamcop.net"]


def _enabled_alerts() -> bool:
    return os.environ.get("DELIVERABILITY_MONITOR", "0").strip().lower() in ("1", "true", "yes")


def _txt_lookup(name: str) -> list[str]:
    try:
        import dns.resolver

        return [b"".join(r.strings).decode("utf-8", "ignore") for r in dns.resolver.resolve(name, "TXT")]
    except Exception:
        return []


def _a_lookup(name: str) -> bool:
    """DNSBL me listed? (A record milta hai = LISTED)."""
    try:
        import dns.resolver

        dns.resolver.resolve(name, "A")
        return True
    except Exception:
        return False


def _public_ip() -> str:
    ip = os.environ.get("PUBLIC_IP", "").strip()
    if ip:
        return ip
    try:
        import dns.resolver

        r = dns.resolver.Resolver()
        r.nameservers = ["208.67.222.222"]  # OpenDNS
        ans = r.resolve("myip.opendns.com", "A")
        return str(ans[0])
    except Exception:
        return ""


def check_records(domain: str = DOMAIN) -> dict[str, Any]:
    """SPF + DMARC presence check (pure DNS, kabhi raise nahi)."""
    out: dict[str, Any] = {"domain": domain, "spf_ok": False, "dmarc_ok": False}
    try:
        out["spf_ok"] = any("v=spf1" in t.lower() for t in _txt_lookup(domain))
        out["dmarc_ok"] = any("v=dmarc1" in t.lower() for t in _txt_lookup(f"_dmarc.{domain}"))
    except Exception:
        pass
    return out


def check_blacklists(ip: str = "") -> dict[str, Any]:
    """VPS IP DNSBLs me? reversed-IP query (industry standard). Kabhi raise nahi."""
    out: dict[str, Any] = {"ip": "", "listed_on": [], "checked": []}
    try:
        ip = ip or _public_ip()
        out["ip"] = ip
        if not ip or ip.count(".") != 3:
            return out
        rev = ".".join(reversed(ip.split(".")))
        for bl in _DNSBLS:
            out["checked"].append(bl)
            if _a_lookup(f"{rev}.{bl}"):
                out["listed_on"].append(bl)
    except Exception:
        pass
    return out


async def run_check() -> dict[str, Any]:
    """Full check + store + (gated) alert. Scheduler watchdog-job se. Kabhi raise nahi."""
    try:
        rec = {
            "at": datetime.now(timezone.utc).isoformat(),
            **check_records(),
            "blacklist": check_blacklists(),
        }
        problems: list[str] = []
        if not rec.get("spf_ok"):
            problems.append("SPF record missing/broken")
        if not rec.get("dmarc_ok"):
            problems.append("DMARC record missing/broken")
        if rec["blacklist"].get("listed_on"):
            problems.append(f"IP blacklisted: {', '.join(rec['blacklist']['listed_on'])}")
        rec["problems"] = problems
        try:
            os.makedirs(os.path.dirname(_LOG) or ".", exist_ok=True)
            with open(_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass
        if problems and _enabled_alerts():
            notify = os.environ.get("NOTIFY_EMAIL", "").strip()
            if notify:
                try:
                    from app.integrations.email_sender import email_sender

                    await email_sender.send_email(
                        [notify],
                        f"⚠️ Email deliverability problem ({len(problems)})",
                        "Outreach sender-reputation issues:\n\n- " + "\n- ".join(problems)
                        + "\n\nJaldi fix karo warna cold emails spam me jayengi. (deliverability_monitor)",
                    )
                except Exception as e:
                    logger.warning(f"[deliverability] alert failed: {e}")
        try:
            from app.platform import team

            team.log_event("kavya", "deliverability_check", "OK" if not problems else "; ".join(problems)[:200], status="ok" if not problems else "warn")
        except Exception:
            pass
        return rec
    except Exception as e:
        logger.warning(f"[deliverability] run_check failed: {e}")
        return {"error": str(e)}
