"""GEO visibility report — "AI search me aapka business dikh raha hai?" (lead magnet #3).

Birdeye Search-AI parity, free-stack: ChatGPT/Gemini-type AI search ab naya
local-discovery channel hai — customers AI se poochte hain "best dentist in
Pune?". Yeh module free_ai chain se 3-4 probe questions poochta hai aur check
karta hai ki business ka naam AI ke jawab me aata hai ya nahi → 0-100 score +
Hinglish verdict + fix tips + CTA (/audit, /pricing).

Design (project patterns):
- NEVER raises — har failure pe {"ok": False, "error": ...}.
- Lazy imports (free_ai handler ke andar).
- 1-hr cache (in-memory + jsonl log) keyed (name, city) — PUBLIC endpoint hai,
  abuse-safe: same business dobara check = pollen-free cache hit.
- LLM call ASYNC hai; endpoint `asyncio.wait_for(..., 20)` se wrap karta
  (prod-down lesson: event loop kabhi block nahi).
- Deterministic fallback: LLM poori tarah down → ok=False "ai_unavailable"
  (galat 0-score report kabhi nahi dete — lead magnet ki credibility).

Store: data/geo_checks.jsonl (append-only, inquiries.jsonl pattern).
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_LOG_FILE = os.path.join("data", "geo_checks.jsonl")
_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_CACHE_TTL = 3600  # 1 hr

# Generic tokens jo business-name match me count nahi hote (false positives)
_GENERIC = {
    "the",
    "and",
    "of",
    "in",
    "for",
    "ltd",
    "pvt",
    "private",
    "limited",
    "co",
    "company",
    "services",
    "service",
    "shop",
    "store",
    "enterprises",
    "india",
    "new",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: str, rec: dict[str, Any]) -> bool:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception as e:
        logger.warning(f"[geo] append {path} failed: {e}")
        return False


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        if not os.path.isfile(path):
            return out
        with open(path, encoding="utf-8") as f:
            for ln in f:
                try:
                    rec = json.loads(ln)
                    if isinstance(rec, dict):
                        out.append(rec)
                except Exception:
                    continue
    except Exception as e:
        logger.debug(f"[geo] read {path} failed: {e}")
    return out


# --------------------------------------------------------------------------- #
# Pure helpers (unit-testable, no network)
# --------------------------------------------------------------------------- #
def _tokens(text: str) -> set[str]:
    t = "".join(ch if ch.isalnum() else " " for ch in (text or "").lower())
    return {w for w in t.split() if len(w) > 2 and w not in _GENERIC}


def _mentions(answer: str, business_name: str) -> bool:
    """Fuzzy: AI ke jawab me business ka naam aaya? (lowercase substring ya
    token overlap >= 60% of business tokens). Pure function — tests isi pe."""
    a = " ".join((answer or "").lower().split())
    b = " ".join((business_name or "").lower().split())
    if not a or not b:
        return False
    if b in a:
        return True
    bt = _tokens(business_name)
    if not bt:
        return False
    at = _tokens(answer)
    return len(bt & at) / len(bt) >= 0.6


def build_probes(niche: str, city: str) -> list[str]:
    """3-4 probe questions — English + Hinglish mix (real AI-search queries jaisi)."""
    niche = (niche or "local business").strip()
    city = (city or "").strip()
    return [
        f"Best {niche} in {city}? Naam batao.",
        f"{city} me sabse accha {niche} kaun sa hai?",
        f"Top rated {niche} near {city} — 2-3 recommend karo.",
        f"Mujhe {city} me ek reliable {niche} chahiye, kise contact karu?",
    ]


def _verdict(score: int, mentioned: int, answered: int) -> str:
    if answered and mentioned == answered:
        return "Badhiya! AI search me aapka business consistently dikh raha hai — yeh edge banaye rakho."
    if score >= 40:
        return (
            f"AI me aapka business {answered} me se sirf {mentioned} baar dikha — "
            "partial visibility hai, aur push chahiye."
        )
    return (
        "AI me aapka business NAHI dikh raha — yeh naya search hai, customers AI se "
        "pooch rahe hain aur competitor ka naam aa raha hai."
    )


_TIPS = [
    "GBP (Google Business Profile) 100% complete karo — category, photos, hours, services.",
    "Reviews badhao — AI recommendations me high-review businesses pehle aate hain.",
    "Website pe naam+city+niche clear likho aur LocalBusiness schema (JSON-LD) lagao.",
    "Justdial/Sulekha/IndiaMART jaise directories me consistent NAP (name-address-phone) rakho.",
    "FAQ/blog content banao jo customer ke sawaal directly answer kare — AI wahi se uthata hai.",
]


# --------------------------------------------------------------------------- #
# Main check (async — endpoint wait_for se wrap karta hai)
# --------------------------------------------------------------------------- #
async def check(business_name: str, niche: str, city: str) -> dict[str, Any]:
    """AI-search visibility check → score 0-100 + Hinglish verdict + tips + CTA.

    Cache-first (1 hr, keyed name+city). Never raises.
    """
    try:
        business_name = (business_name or "").strip()
        niche = (niche or "").strip()
        city = (city or "").strip()
        if not business_name or not city:
            return {"ok": False, "error": "business_name aur city dono chahiye"}

        key = (business_name.lower(), city.lower())
        cached = _CACHE.get(key)
        if cached and (time.time() - cached[0]) < _CACHE_TTL:
            return {**cached[1], "cached": True}

        probes = build_probes(niche, city)
        results: list[dict[str, Any]] = []
        answered = 0
        mentioned = 0
        try:
            from app.voice_agent import free_ai
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"[geo] free_ai import failed: {e}")
            free_ai = None

        for q in probes:
            answer = ""
            if free_ai is not None:
                try:
                    reply, _provider = await free_ai.chat(
                        system=(
                            "Tu ek local business recommendation assistant hai (AI search "
                            "engine jaisa). User ke sawaal ka seedha jawab de — 2-4 actual "
                            "business naam suggest kar, short me."
                        ),
                        messages=[{"role": "user", "content": q}],
                        max_tokens=150,
                        temperature=0.3,
                    )
                    answer = (reply or "").strip()
                except Exception as e:
                    logger.info(f"[geo] probe failed: {e}")
            hit = False
            if answer:
                answered += 1
                hit = _mentions(answer, business_name)
                if hit:
                    mentioned += 1
            results.append(
                {"question": q, "answered": bool(answer), "mentioned": hit, "snippet": answer[:200]}
            )

        if answered == 0:
            # Deterministic fallback — galat 0-score kabhi report nahi karte
            return {
                "ok": False,
                "error": "ai_unavailable",
                "message": "AI check abhi nahi ho paya — thodi der baad try karo.",
            }

        score = round(100 * mentioned / answered)
        report = {
            "ok": True,
            "business_name": business_name,
            "niche": niche,
            "city": city,
            "score": score,
            "mentioned": mentioned,
            "answered": answered,
            "probes": results,
            "verdict": _verdict(score, mentioned, answered),
            "tips": _TIPS,
            "cta": {
                "audit": "/audit",
                "pricing": "/pricing",
                "line": "FREE GBP audit lo → /audit · AI-era marketing shuru karo → /pricing",
            },
            "checked_at": _now(),
        }
        _CACHE[key] = (time.time(), report)
        _append_jsonl(
            _LOG_FILE,
            {
                "checked_at": report["checked_at"],
                "business_name": business_name,
                "niche": niche,
                "city": city,
                "score": score,
                "mentioned": mentioned,
                "answered": answered,
            },
        )
        return report
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"[geo] check failed: {e}")
        return {"ok": False, "error": str(e)}


def recent(limit: int = 20) -> list[dict[str, Any]]:
    """Recent geo-checks newest-first (admin view). Never raises."""
    try:
        rows = _read_jsonl(_LOG_FILE)
        rows.sort(key=lambda r: str(r.get("checked_at") or ""), reverse=True)
        return rows[: max(1, min(int(limit), 200))]
    except Exception as e:
        logger.debug(f"[geo] recent failed: {e}")
        return []


__all__ = ["check", "recent", "build_probes", "_mentions"]
