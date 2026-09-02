"""AI Website Auditor — PUBLIC lead magnet (`/audit` ka website-wala bhai).

Prospect apna website URL daale → instant score + Hinglish improvement tips →
CTA /pricing. Checks (sab free, ek GET request): title/meta-description/H1,
phone+WhatsApp visible?, mobile viewport, HTTPS, page weight, contact form hint.
free-LLM se 3 personalized tips (fallback static). Kabhi raise nahi.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _resolve_is_public(host: str) -> bool:
    """True only if EVERY resolved IP for ``host`` is a public address. Blocks SSRF to
    loopback / private / link-local / reserved targets (cloud-metadata
    169.254.169.254, docker service IPs, 127.0.0.1, 10./172.16./192.168., etc.)."""
    low = (host or "").strip().lower().rstrip(".")
    if not low or low == "localhost" or low.endswith((".local", ".internal")):
        return False
    try:
        infos = socket.getaddrinfo(low, None)
    except Exception:
        return False
    if not infos:
        return False
    for info in infos:
        ip = str(info[4][0]).split("%")[0]  # strip IPv6 zone id
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            return False
    return True


def _safe_audit_target(u: str) -> bool:
    """User-supplied audit URL http(s) hai AND sirf public IPs pe resolve hota?"""
    return _normalize_safe_audit_url(u) is not None


def _normalize_safe_audit_url(u: str) -> str | None:
    """Return canonical URL if safe for audit, else None."""
    try:
        p = urlparse((u or "").strip())
    except Exception:
        return None
    if p.scheme not in ("http", "https") or not p.hostname:
        return None
    # Reject credentialed URLs and fragments to reduce parser/bypass edge-cases.
    if p.username is not None or p.password is not None or p.fragment:
        return None
    if not _resolve_is_public(p.hostname):
        return None
    return p.geturl()


def _normalize_safe_audit_url(u: str) -> str | None:
    """Return canonical URL if safe for audit, else None."""
    try:
        p = urlparse((u or "").strip())
    except Exception:
        return None
    if p.scheme not in ("http", "https") or not p.hostname:
        return None
    # Reject credentialed URLs and fragments to reduce parser/bypass edge-cases.
    if p.username is not None or p.password is not None or p.fragment:
        return None
    if not _resolve_is_public(p.hostname):
        return None
    return p.geturl()


def analyze_html(html_text: str, final_url: str = "") -> dict[str, Any]:
    """Pure function — HTML string par checks + 0-100 score. Testable."""
    h = html_text or ""
    hl = h.lower()
    checks = {
        "https": final_url.startswith("https://") if final_url else True,
        "title": bool(re.search(r"<title[^>]*>\s*[^<\s]", hl)),
        "meta_description": 'name="description"' in hl or "name='description'" in hl,
        "h1": "<h1" in hl,
        "viewport": 'name="viewport"' in hl or "name='viewport'" in hl,
        "phone_visible": bool(
            re.search(r"(\+91[\s-]?\d{5}[\s-]?\d{5})|(?<!\d)[6-9]\d{9}(?!\d)", h)
        ),
        "whatsapp_link": "wa.me" in hl or "api.whatsapp.com" in hl,
        "contact_form": "<form" in hl,
        "light_page": len(h) < 600_000,
    }
    weights = {
        "https": 10,
        "title": 10,
        "meta_description": 15,
        "h1": 10,
        "viewport": 15,
        "phone_visible": 15,
        "whatsapp_link": 10,
        "contact_form": 10,
        "light_page": 5,
    }
    score = sum(weights[k] for k, ok in checks.items() if ok)
    missing = [k for k, ok in checks.items() if not ok]
    return {"score": score, "checks": checks, "missing": missing}


_TIPS = {
    "meta_description": "Meta description add karo (150 chars, seva + sheher + phone) — Google me click badhega.",
    "phone_visible": "Phone number header me bada dikhao — mobile user 5 second me call decide karta hai.",
    "whatsapp_link": "WhatsApp chat button lagao (wa.me link) — Indian customers form se zyada WA pe aate hain.",
    "viewport": "Mobile viewport tag missing — aadhe se zyada visitors mobile pe hain, site tooti dikhegi.",
    "contact_form": "Ek chhota inquiry form lagao (naam+phone bas) — ya hamara free embed widget use karo.",
    "h1": "Ek clear H1 heading do: 'Sheher ki best <seva>' — SEO aur clarity dono.",
    "title": "Page title likho: '<Seva> in <Sheher> | <Business>' format me.",
    "https": "HTTPS lagao (free Let's Encrypt) — bina iske Google 'Not Secure' dikhata hai.",
    "light_page": "Page bahut bhaari hai — images compress karo, loading speed = conversions.",
}


async def audit_url(url: str) -> dict[str, Any]:
    """Public audit: URL fetch → checks → AI tips → CTA. Kabhi raise nahi."""
    u = (url or "").strip()
    if not u:
        return {"ok": False, "error": "URL do"}
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    try:
        import httpx

        html_text = ""
        final_url = u
        cur = _normalize_safe_audit_url(u)
        if not cur:
            return {
                "ok": False,
                "error": "Yeh URL allowed nahi — sirf public website audit hoti hai",
            }
        # SSRF guard: redirects manually follow karo aur HAR hop ka host validate karo
        # (warna public->internal redirect se metadata/DB/redis hit ho sakta).
        async with httpx.AsyncClient(
            follow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0 (LeadsGenAI-Audit)"},
        ) as client:
            for _hop in range(5):
                resp = await client.get(cur, timeout=12.0)
                loc = resp.headers.get("location")
                if resp.is_redirect and loc:
                    nxt = _normalize_safe_audit_url(urljoin(cur, loc))
                    if not nxt:
                        return {
                            "ok": False,
                            "error": "Yeh URL allowed nahi — sirf public website audit hoti hai",
                        }
                    cur = nxt
                    continue
                html_text = resp.text[:800_000]
                final_url = str(resp.url)
                break
            else:
                return {"ok": False, "error": "Bahut zyada redirects — URL check karo"}
    except Exception as e:
        return {"ok": False, "error": f"Site fetch nahi hui ({str(e)[:80]}) — URL check karo"}

    result = analyze_html(html_text, final_url)
    tips = [_TIPS[m] for m in result["missing"] if m in _TIPS][:3]
    # AI personalized tip (best-effort, fallback = static hi kaafi)
    try:
        if len(tips) < 3:
            from app.voice_agent.free_ai import chat

            raw, _ = await chat(
                "Tu website conversion expert hai. EK chhota Hinglish tip de (<25 words) is site ke liye.",
                [
                    {
                        "role": "user",
                        "content": f"Site: {final_url}, score {result['score']}/100, missing: {result['missing']}",
                    }
                ],
                max_tokens=60,
            )
            if raw and len(raw) > 10:
                tips.append(raw.strip()[:160])
    except Exception:
        pass
    grade = (
        "A"
        if result["score"] >= 80
        else ("B" if result["score"] >= 60 else ("C" if result["score"] >= 40 else "D"))
    )
    return {
        "ok": True,
        "url": final_url,
        "score": result["score"],
        "grade": grade,
        "checks": result["checks"],
        "tips": tips or ["Site achhi hai! Ab leads automate karo — leadsgenai.in/pricing"],
        "cta": {
            "message": "Website theek karne se zyada zaroori: har inquiry ka 2-min me jawab. Hum dono automate karte hain.",
            "audit": "https://leadsgenai.in/audit",
            "pricing": "https://leadsgenai.in/pricing",
        },
    }
