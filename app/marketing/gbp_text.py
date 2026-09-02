"""
gbp_text.py — Google Business Profile texts (description + services + posts).
===============================================================================

GBP ka sabse bada free-SEO lever ab description/services text hai (Q&A API
band ho chuki) — entity-optimized Hinglish-friendly copy:

  - gbp_texts(business_name, niche, city="", services=None) -> dict:
      description (HARD ≤750 chars — business+niche+city+services naturally),
      services: [{name, desc ≤300 chars}], posts: 3 "Google post" updates.
      LLM-first SINGLE call (free_ai), template fallback — KABHI khali nahi.

Kabhi raise nahi karta.
"""

from __future__ import annotations

import re
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

try:
    from app.voice_agent import free_ai  # type: ignore
except Exception:  # pragma: no cover - free_ai khud import-safe hai
    free_ai = None  # type: ignore

_DESC_MAX = 750  # GBP "from the business" description limit
_SVC_MAX = 300  # GBP service description limit

_MARK_RE = re.compile(r"^\s*(DESC|SVC(\d+)|POST(\d+))\s*[:.\-]\s*(.+)$", re.IGNORECASE)


def _label(niche: str) -> str:
    n = (niche or "").strip().replace("_", " ")
    return (n.title() if n and n.lower() != "general" else "Local Business")[:60]


def _clip(s: str, n: int) -> str:
    """HARD char clip — sentence/word boundary pe, guarantee len <= n."""
    s = re.sub(r"\s+", " ", (s or "")).strip()
    if len(s) <= n:
        return s
    cut = s[:n]
    dot = cut.rfind(". ")
    if dot > n // 2:
        return cut[: dot + 1]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,.;:-")[:n]


def _norm_services(services: list[Any] | None) -> list[str]:
    out: list[str] = []
    for s in services or []:
        v = str(s or "").strip()[:80]
        if v and v.lower() not in [x.lower() for x in out]:
            out.append(v)
        if len(out) >= 12:
            break
    return out


def _fallback_description(name: str, label: str, city: str, svcs: list[str]) -> str:
    in_city = f" {city} me" if city else ""
    svc_line = ""
    if svcs:
        svc_line = " Hamari services: " + ", ".join(svcs[:6]) + "."
    desc = (
        f"{name}{in_city} aapka bharosemand {label} hai. Quality kaam, "
        f"transparent pricing aur time par delivery — yahi hamari pehchan "
        f"hai.{svc_line} Hamari experienced team har customer ko personal "
        "attention deti hai, isliye log hume apno ko refer karte hain. "
        + (
            f"{city} aur aas-paas ke ilaake me hum ghar baithe consultation bhi dete hain. "
            if city
            else ""
        )
        + "Free estimate aur jaldi response ke liye aaj hi call ya WhatsApp "
        "karein — pehli baat bilkul free hai."
    )
    return _clip(desc, _DESC_MAX)


def _fallback_service_desc(name: str, svc: str, city: str) -> str:
    in_city = f" {city} me" if city else ""
    return _clip(
        f"{svc}: {name} ki expert team se professional {svc.lower()}{in_city} "
        "— sahi daam, pakka kaam aur time par completion. Free estimate ke "
        "liye call ya WhatsApp karein; pehle samjhein, phir decide karein.",
        _SVC_MAX,
    )


def _fallback_posts(name: str, label: str, city: str, svcs: list[str]) -> list[str]:
    svc = svcs[0] if svcs else label
    in_city = f" {city} me" if city else ""
    return [
        (
            f"📍 {name}{in_city} — {label} ke liye trusted naam! Quality kaam, "
            "sahi daam aur friendly team. Aaj hi profile se 'Call' button "
            "dabayein aur free consultation paayein."
        ),
        (
            f"🎉 Is hafte ka special: {svc} par extra dhyan, wahi quality, "
            f"behtar daam! {name} ke saath kaam karwane ka sabse accha time "
            "yahi hai — message karke slot book karein."
        ),
        (
            f"⭐ Hamare customers hume 5-star kyu dete hain? Time par kaam, "
            f"transparent baat aur after-service support. {name} ko aaj hi try "
            "karein — review section khud dekh lijiye!"
        ),
    ]


async def gbp_texts(
    business_name: str, niche: str, city: str = "", services: list[str] | None = None
) -> dict[str, Any]:
    """GBP description + services texts + 3 posts. LLM 1 call, kabhi raise nahi."""
    name = (business_name or "").strip()[:120] or "Aapka Business"
    label = _label(niche)
    city_c = (city or "").strip()[:80]
    svcs = _norm_services(services)
    provider = "template"

    llm_desc = ""
    llm_svc: dict[int, str] = {}
    llm_posts: dict[int, str] = {}

    if free_ai is not None:
        svc_fmt = "".join(
            f"\nSVC{i}: (max 280 chars — '{s}' ki selling description)"
            for i, s in enumerate(svcs, 1)
        )
        system = (
            "Tu local SEO expert hai. Google Business Profile ke liye "
            "Hinglish (Roman script) copy likh — business naam, category, "
            "city aur services NATURALLY use kar (keyword stuffing nahi). "
            "Output format EXACT (sirf ye lines):\n"
            f"DESC: (max 700 chars, ek paragraph){svc_fmt}\n"
            "POST1: (30-60 shabd ka Google post update)\n"
            "POST2: (30-60 shabd, offer/seasonal angle)\n"
            "POST3: (30-60 shabd, review/social-proof angle)"
        )
        user = (
            f"Business: {name}. Category: {label}."
            + (f" City: {city_c}." if city_c else "")
            + (f" Services: {', '.join(svcs)}." if svcs else "")
        )
        try:
            text, p = await free_ai.chat(
                system,
                [{"role": "user", "content": user}],
                max_tokens=900,
                temperature=0.65,
            )
            for ln in (text or "").splitlines():
                m = _MARK_RE.match(ln)
                if not m:
                    continue
                tag = m.group(1).upper()
                val = m.group(4).strip()
                if tag == "DESC":
                    llm_desc = val
                elif m.group(2):
                    llm_svc[int(m.group(2))] = val
                elif m.group(3):
                    llm_posts[int(m.group(3))] = val
            if (llm_desc or llm_posts) and p:
                provider = p
        except Exception as e:
            logger.warning(f"gbp_texts LLM failed, using template: {e}")

    description = _clip(llm_desc, _DESC_MAX) or _fallback_description(name, label, city_c, svcs)

    services_out = [
        {
            "name": s,
            "desc": _clip(llm_svc.get(i, ""), _SVC_MAX) or _fallback_service_desc(name, s, city_c),
        }
        for i, s in enumerate(svcs, 1)
    ]

    fb_posts = _fallback_posts(name, label, city_c, svcs)
    posts = [(_clip(llm_posts.get(i, ""), 1500) or fb_posts[i - 1]) for i in (1, 2, 3)]

    return {
        "business_name": name,
        "niche": label,
        "city": city_c,
        "description": description,
        "description_chars": len(description),
        "services": services_out,
        "posts": posts,
        "provider": provider,
        "tip": "Description GBP ke 'Edit profile → From the business' me paste "
        "karo; har hafte 1 Google post dalo — local ranking ka sabse "
        "sasta lever yahi hai.",
    }
