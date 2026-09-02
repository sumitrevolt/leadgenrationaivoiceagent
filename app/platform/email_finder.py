"""Email Finder Waterfall (Apollo.io ka free equivalent) — website/domain se
deliverable email nikaalo.

Waterfall: (1) website HTML se real emails (EXISTING web_extract.find_contacts),
(2) common Indian-SMB patterns (info@/contact@/hello@/sales@/<name>@), (3) har
candidate ka MX-verify (EXISTING email_verify — syntax+MX), sirf deliverable
lautao. Apollo $49/mo me yahi karta — hum DNS se free karte. SMTP-handshake
verify NAHI karte (port-25 reputation risk) — MX = bounce<2% ke liye kaafi
(auto_outreach ka proven standard).

Import-safe, kabhi raise nahi. Network: 1 HTTP GET (site) + DNS lookups.
"""

from __future__ import annotations

import re
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_PATTERNS = ["info", "contact", "hello", "sales", "enquiry", "support", "admin"]


def _domain_of(website_or_domain: str) -> str:
    s = (website_or_domain or "").strip().lower()
    if not s:
        return ""
    s = re.sub(r"^https?://", "", s).split("/")[0].split("?")[0]
    s = s.removeprefix("www.")
    return s if "." in s else ""


def candidates(domain: str, owner_name: str = "") -> list[str]:
    """Pattern-based guesses (pure fn — testable). Free-mail domains skip
    (gmail pe pattern-guess bekaar)."""
    d = _domain_of(domain)
    if not d or any(
        d.endswith(f)
        for f in ("gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "rediffmail.com")
    ):
        return []
    out = [f"{p}@{d}" for p in _PATTERNS]
    nm = re.sub(r"[^a-z]", "", (owner_name or "").strip().lower().split(" ")[0])
    if nm and len(nm) >= 3:
        out.insert(0, f"{nm}@{d}")
    return out


async def _site_emails(domain: str) -> list[str]:
    """Website HTML se real emails (best source). [] on any failure."""
    d = _domain_of(domain)
    if not d:
        return []
    # SSRF guard (fail-CLOSED): only fetch if the domain resolves to PUBLIC IPs.
    # Blocks an attacker-supplied domain that points at 169.254.169.254 / 127.0.0.1 /
    # 10./172.16./192.168. / docker service IPs. redirects OFF so a public host can't
    # 302-bounce us to an internal target (httpx doesn't re-validate redirect IPs).
    try:
        from app.marketing.website_auditor import _resolve_is_public

        if not _resolve_is_public(d):
            return []
    except Exception:
        return []
    try:
        import httpx

        from app.lead_scraper.web_extract import find_contacts

        async with httpx.AsyncClient(
            follow_redirects=False, headers={"User-Agent": "Mozilla/5.0"}
        ) as client:
            for url in (f"https://{d}", f"https://{d}/contact"):
                try:
                    r = await client.get(url, timeout=10.0)
                    if r.status_code == 200:
                        emails = (find_contacts(r.text) or {}).get("emails") or []
                        if emails:
                            return [str(e).lower() for e in emails][:5]
                except Exception:
                    continue
    except Exception as e:
        logger.debug(f"[email_finder] site fetch skip: {e}")
    return []


async def find(
    website_or_domain: str, owner_name: str = "", max_results: int = 3
) -> dict[str, Any]:
    """Waterfall: site-extract → patterns → MX-verify. Returns
    {ok, emails: [{email, source, verified}], domain}. Kabhi raise nahi."""
    d = _domain_of(website_or_domain)
    if not d:
        return {"ok": False, "error": "valid website/domain do", "emails": []}
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        from app.lead_scraper.email_verify import verify

        # 1) website se real emails (highest confidence)
        for em in await _site_emails(d):
            if em in seen:
                continue
            seen.add(em)
            v = verify(em, check_mx=True)
            if v.get("ok"):
                found.append({"email": v["email"], "source": "website", "verified": True})
            if len(found) >= max_results:
                return {"ok": True, "domain": d, "emails": found}
        # 2) pattern guesses + MX (MX domain-level hota — ek hi lookup se sab
        #    candidates ka domain verify; pehla MX-pass pattern hi kaafi)
        for em in candidates(d, owner_name):
            if em in seen:
                continue
            seen.add(em)
            v = verify(em, check_mx=True)
            if v.get("ok"):
                found.append({"email": v["email"], "source": "pattern", "verified": "mx_only"})
                if len(found) >= max_results:
                    break
    except Exception as e:
        logger.debug(f"[email_finder] find skip: {e}")
    return {"ok": bool(found), "domain": d, "emails": found}
