"""
reels.py — Instagram Reels / YouTube Shorts script generator (free stack).
===========================================================================

  - reels_scripts(business_name, niche, topic="", n=3) -> dict:
      n scripts, har ek {hook (3s), body (15s), cta, caption, hashtags[5],
      duration:"30s"} — script total ≤120 words (HARD enforce).
      LLM-first (free_ai, 1 call), 3 deterministic template fallbacks
      (festival / offer / tip patterns) — KABHI khali nahi.

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

_MAX_WORDS = 120
_FIELD_RE = re.compile(r"^\s*(HOOK|BODY|CTA|CAPTION|TAGS)\s*[:.\-]\s*(.+)$", re.IGNORECASE)


def _label(niche: str) -> str:
    n = (niche or "").strip().replace("_", " ")
    return (n.title() if n and n.lower() != "general" else "Business")[:40]


def _tagword(s: str) -> str:
    w = re.sub(r"[^a-z0-9]", "", (s or "").lower())
    return w[:24]


def _hashtags(niche: str, topic: str, biz: str) -> list[str]:
    cands = ["#reels", "#trending"]
    for src in (niche.replace("_", ""), topic, biz):
        w = _tagword(src)
        if w and len(w) >= 3:
            cands.append("#" + w)
    cands += ["#india", "#smallbusiness", "#viral", "#localbusiness"]
    out: list[str] = []
    seen = set()
    for t in cands:
        if t.lower() not in seen and len(t) > 1:
            seen.add(t.lower())
            out.append(t)
        if len(out) >= 5:
            break
    return out[:5]


def _words(s: str) -> int:
    return len((s or "").split())


def _enforce_budget(script: dict[str, Any]) -> dict[str, Any]:
    """hook+body+cta+caption total ≤120 words — body se trim hota hai."""
    fixed = _words(script["hook"]) + _words(script["cta"]) + _words(script["caption"])
    body_budget = max(5, _MAX_WORDS - fixed)
    body_words = (script["body"] or "").split()
    if len(body_words) > body_budget:
        script["body"] = " ".join(body_words[:body_budget])
    return script


def _fallback_scripts(biz: str, label: str, topic: str) -> list[dict[str, Any]]:
    """3 patterns: offer / tip / festival — deterministic, chhote, ready."""
    t = (topic or "").strip() or label
    return [
        {  # OFFER pattern
            "hook": f"Ruk jao! 🛑 {t} pe itna bada offer miss mat karna.",
            "body": (
                f"{biz} laya hai limited-time deal — wahi quality, kam "
                f"daam. Pehle aao, pehle pao. Sirf is hafte ke liye, "
                "slots tezi se bhar rahe hain."
            ),
            "cta": "Abhi WhatsApp karo 'OFFER' likh kar! 📲",
            "caption": f"🔥 {biz} ka dhamaka offer — bio link pe details!",
        },
        {  # TIP pattern
            "hook": f"99% log {t} me ye galti karte hain! 😱",
            "body": (
                f"Aaj ek pro tip {biz} ki taraf se: sahi jankari ke "
                f"bina decision mat lo. Hamare experts pehle FREE me "
                "samjhate hain, phir aap aaram se choose karo."
            ),
            "cta": "Aisi tips ke liye follow karo + share karo! 🔁",
            "caption": f"💡 {t} pro tip — save kar lo, kaam aayegi!",
        },
        {  # FESTIVAL pattern
            "hook": "Is tyohar kuch khaas hone wala hai... ✨",
            "body": (
                f"{biz} ki poori team ki taraf se aapko dher saari "
                f"shubhkamnayein! Celebration ke saath {t} ka special "
                "surprise bhi — story pe nazar rakhna."
            ),
            "cta": "Visit karo ya DM karo — festive slot book karo! 🎉",
            "caption": f"🪔 Tyohar ki shubhkamnayein {biz} ki taraf se ❤️",
        },
    ]


def _parse_llm_scripts(text: str) -> list[dict[str, Any]]:
    """'---' separated blocks me HOOK:/BODY:/CTA:/CAPTION:/TAGS: parse karo."""
    scripts: list[dict[str, Any]] = []
    for block in re.split(r"\n\s*-{3,}\s*\n?", text or ""):
        cur: dict[str, Any] = {}
        for ln in block.splitlines():
            m = _FIELD_RE.match(ln)
            if not m:
                continue
            key, val = m.group(1).lower(), m.group(2).strip()
            if key == "tags":
                tags = [
                    w if w.startswith("#") else "#" + w
                    for w in re.split(r"[\s,]+", val)
                    if _tagword(w)
                ]
                cur["hashtags"] = tags[:5]
            else:
                cur[key] = val
        if cur.get("hook") and cur.get("body"):
            scripts.append(cur)
    return scripts


async def reels_scripts(
    business_name: str, niche: str, topic: str = "", n: int = 3
) -> dict[str, Any]:
    """n Reels scripts (hook/body/cta/caption/hashtags/duration). Kabhi raise nahi."""
    biz = (business_name or "").strip()[:120] or "Aapka Business"
    label = _label(niche)
    topic_c = (topic or "").strip()[:120]
    try:
        n = max(1, min(int(n), 6))
    except Exception:
        n = 3
    provider = "template"

    llm_scripts: list[dict[str, Any]] = []
    if free_ai is not None:
        system = (
            f"Tu viral Instagram Reels scriptwriter hai. Hinglish (Roman "
            f"script) me {n} alag-alag 30-second Reel scripts likh. Har "
            "script ka format EXACT:\nHOOK: (pehle 3 second me pakadne wali "
            "line)\nBODY: (15 second ka bolne ka script, 2-3 chhote vakya)\n"
            "CTA: (1 line)\nCAPTION: (1 line + emoji)\nTAGS: #tag1 #tag2 "
            "#tag3 #tag4 #tag5\nHar script ke beech '---' line. Har script "
            "total 100 shabd se kam. Koi extra commentary nahi."
        )
        user = f"Business: {biz}. Category: {label}." + (f" Topic: {topic_c}." if topic_c else "")
        try:
            text, p = await free_ai.chat(
                system,
                [{"role": "user", "content": user}],
                max_tokens=750,
                temperature=0.8,
            )
            llm_scripts = _parse_llm_scripts(text)
            if llm_scripts and p:
                provider = p
        except Exception as e:
            logger.warning(f"reels_scripts LLM failed, using templates: {e}")

    fallbacks = _fallback_scripts(biz, label, topic_c)
    scripts: list[dict[str, Any]] = []
    for i in range(n):
        src = llm_scripts[i] if i < len(llm_scripts) else fallbacks[i % len(fallbacks)]
        tags = src.get("hashtags") or _hashtags(niche or "", topic_c, biz)
        while len(tags) < 5:
            for extra in _hashtags(niche or "", topic_c, biz) + ["#explore"]:
                if extra not in tags:
                    tags.append(extra)
                if len(tags) >= 5:
                    break
        script = {
            "hook": str(src.get("hook") or "").strip()[:200] or f"{biz} — ye dekhna mat bhoolna!",
            "body": str(src.get("body") or "").strip()[:900],
            "cta": str(src.get("cta") or "").strip()[:200] or "Follow karo aur DM karo! 📲",
            "caption": str(src.get("caption") or "").strip()[:300] or f"✨ {biz} ✨",
            "hashtags": tags[:5],
            "duration": "30s",
        }
        if not script["body"]:
            script["body"] = fallbacks[i % len(fallbacks)]["body"]
        scripts.append(_enforce_budget(script))

    return {
        "business_name": biz,
        "niche": label,
        "topic": topic_c,
        "count": len(scripts),
        "scripts": scripts,
        "provider": provider,
        "tip": "Hook pehle 3 second me bolo (text overlay ke saath), phone "
        "vertical 9:16, trending audio low-volume pe — reach 2-3x.",
    }
