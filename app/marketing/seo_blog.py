"""
seo_blog.py — Programmatic SEO blog engine (100% FREE).
========================================================

Site ke liye apne-aap useful Hinglish articles likhta hai jo Google par
local-business marketing keywords pe rank karein aur inbound leads laayein —
sab free stack par:

  LLM:    app.voice_agent.free_ai.chat() (Cerebras/Groq/OpenRouter chain).
          free_ai ("","") de sakta hai (zero keys / quota / timeout) — ISLIYE
          har article ka TEMPLATE fallback hai jo niche ke content_focus se
          asli, kaam ki tips deta hai. KABHI khali article nahi.
  Niches: app.niches.NICHES (category=="marketing"/"both") se naam + focus.

Storage: data/blog/<slug>.json (ek file = ek article). Static pages (koi DB
nahi) — main.py routes inse render karte hain. Sitemap dynamic ho jaata hai.

Articles genuinely useful rakhe gaye hain (keyword-stuffed spam NAHI) —
har ek me intro + 4-6 H2 sections + ek closing CTA hai. CTA hamesha:
  "FREE Google audit: leadsgenai.in/audit | WhatsApp: wa.me/918459012607"

Import-safe: free_ai/NICHES na milein to bhi load hota hai aur templates se
kaam chalta hai. Koi function raise nahi karta.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from html import escape as _esc
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# --- free LLM chain (import-safe; None => sirf templates) --- #
try:
    from app.voice_agent import free_ai  # type: ignore
except Exception:  # pragma: no cover - free_ai khud import-safe hai
    free_ai = None  # type: ignore

# --- niche registry (import-safe; {} => generic flavor) --- #
try:
    from app.niches import NICHES  # type: ignore
except Exception:  # pragma: no cover
    NICHES = {}  # type: ignore

try:  # custom niches bhi pick ho jaayein (best-effort)
    from app.niches import refresh_custom_niches as _refresh_niches  # type: ignore
except Exception:  # pragma: no cover

    def _refresh_niches() -> None:  # type: ignore
        return None


# Storage dir (test monkeypatch karta hai _BLOG_DIR) ----------------------- #
_BLOG_DIR = str(Path(__file__).resolve().parent.parent.parent / "data" / "blog")

# Lead-magnet CTA (har article ke end me; routes me bhi buttons) ----------- #
_AUDIT_URL = "leadsgenai.in/audit"
_WA = "wa.me/918459012607"
_CTA_LINE = f"FREE Google audit: {_AUDIT_URL} | WhatsApp: {_WA}"

# Programmatic SEO cities (high-intent local-biz search markets) ----------- #
CITIES: list[str] = ["Pune", "Mumbai", "Nagpur", "Delhi", "Bangalore"]

# Evergreen Hinglish topic templates ({niche}/{city} fill hote hain) ------- #
TOPICS: list[str] = [
    "{niche} ki marketing kaise badhaye {city} me",
    "{niche} ke liye Instagram aur Google marketing tips",
    "{city} me {niche} business ke liye festival marketing ideas",
    "Google Business Profile {niche} ke liye optimize kaise kare",
    "{niche} business ke liye WhatsApp marketing kaise kare",
    "{city} me {niche} ke liye zyada customers kaise laaye",
]


# ============================================================================ #
# Helpers
# ============================================================================ #


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").strip().lower()).strip("-")
    return s[:90] or "article"


def _niche_cfg(niche: str) -> dict[str, Any]:
    try:
        return NICHES.get((niche or "").strip().lower(), {}) or {}
    except Exception:
        return {}


def _niche_name(niche: str) -> str:
    cfg = _niche_cfg(niche)
    name = str(cfg.get("name") or "").strip()
    if name:
        return name
    key = (niche or "business").strip() or "business"
    return key.replace("_", " ").title()


def _content_focus(niche: str) -> list[str]:
    cfg = _niche_cfg(niche)
    foc = cfg.get("content_focus") or []
    out = [str(f).strip() for f in foc if str(f).strip()]
    return out or ["social posts", "Google Business Profile", "festival posters", "reviews"]


def _marketing_niches() -> list[str]:
    """category 'marketing' ya 'both' wale niche keys (programmatic SEO target)."""
    _refresh_niches()
    keys: list[str] = []
    try:
        for k, cfg in NICHES.items():
            if (cfg or {}).get("category") in ("marketing", "both"):
                keys.append(k)
    except Exception:
        pass
    return keys or ["restaurant_cafe", "salon_spa", "real_estate"]


def _focus_label(f: str) -> str:
    """content_focus token ko ek readable Hinglish H2 phrase me badlo."""
    f = (f or "").strip().lower()
    mapping = {
        "festival posters": "Festival aur offer posters ka faida uthaye",
        "festival posts": "Festival posts se customers jodein",
        "gbp optimization": "Google Business Profile optimize karein",
        "social posts": "Regular social media posts daalein",
        "reels": "Reels banaye — sabse zyada reach yahi deti hai",
        "reviews": "Google reviews badhaye — bharosa jeetein",
        "menu posters": "Menu aur product posters share karein",
        "offer posters": "Offer posters se footfall badhaye",
        "offer creatives": "Offer creatives roz post karein",
        "offer posts": "Offer posts se inquiry laaye",
        "collection posts": "Nayi collection ke posts daalein",
        "before-after reels": "Before-after reels se results dikhaye",
        "before-after posts": "Before-after posts se kaam dikhaye",
        "portfolio reels": "Apna portfolio reels me dikhaye",
        "transformation reels": "Transformation reels se members jodein",
        "product posts": "Product posts regularly share karein",
        "catalog posters": "Catalog/price-list posters banaye",
        "package posters": "Package posters se enquiry laaye",
        "venue posters": "Venue ki photos aur posters daalein",
        "venue reels": "Venue reels se bookings badhaye",
        "destination reels": "Destination reels se travellers jodein",
        "health-day posts": "Health-day posts se community jodein",
        "service-offer posters": "Service-offer posters share karein",
        "new-arrival posts": "New-arrival posts daalte raho",
        "whatsapp offers": "WhatsApp par offers bhejein",
        "lead forms": "Lead-capture form lagaye website pe",
    }
    if f in mapping:
        return mapping[f]
    return f.replace("-", " ").replace("_", " ").title() + " par dhyan dein"


# ============================================================================ #
# Template article (LLM-fail fallback — genuinely useful, never empty)
# ============================================================================ #

# Universal, niche-agnostic free tips (har article me kaam ke aate hain).
_UNIVERSAL_TIPS: list[str] = [
    "Roz ek post karein — consistency hi sabse bada free hack hai. Google aur "
    "Instagram dono active business ko upar dikhate hain.",
    "Har post me apna area/city ka naam daalein (jaise '{city} me best {niche}') "
    "— 'near me' searches me aapka business tabhi match karta hai.",
    "Customer se Google review maangna mat bhoolein — har naye review se aapki "
    "local ranking aur bharosa dono badhte hain.",
    "Festival aur local events ka calendar bana ke pehle se posts taiyaar "
    "rakhein — last-minute me quality gir jaati hai.",
    "Phone number aur WhatsApp link har jagah same rakhein (Google, Instagram, "
    "website) — mismatch se Google ka trust girta hai.",
]


def _template_article(niche: str, city: str, topic: str) -> dict[str, str]:
    """Deterministic, useful Hinglish article (LLM bilkul na chale tab bhi)."""
    name = _niche_name(niche)
    focus = _content_focus(niche)
    city_phrase = f"{city} me " if city else ""

    title = topic.strip() or f"{name} ki marketing kaise badhaye"

    parts: list[str] = []
    # Intro
    parts.append(
        f"<p>Aaj ke time me {city_phrase}{name} chalana sirf accha kaam karne "
        f"tak limited nahi hai — log pehle online dekhte hain, phir aate hain. "
        f"Agar aapka business Google aur Instagram par sahi se nahi dikh raha, "
        f"toh customers seedhe aapke competitor ke paas chale jaate hain. "
        f"Achhi baat ye hai ki marketing badhane ke liye bada budget zaroori "
        f"nahi — bas sahi cheezein consistently karni hoti hain. Is guide me hum "
        f"{name} ke liye simple, free aur asar-daar tareeke dekhenge.</p>"
    )

    # H2 sections from niche content_focus (4-6 sections)
    used = set()
    sec_count = 0
    for f in focus:
        if sec_count >= 5:
            break
        head = _focus_label(f)
        if head in used:
            continue
        used.add(head)
        sec_count += 1
        parts.append(f"<h2>{_esc(head)}</h2>")
        parts.append(f"<p>{_esc(_focus_body(f, name, city))}</p>")

    # Top up with universal tips so we always have 4-6 sections
    uni = list(_UNIVERSAL_TIPS)
    ui = 0
    uni_heads = [
        "Roz post karein — consistency ka jaadu",
        "Local keywords ka istemaal karein",
        "Google reviews maange bina sharmaye",
    ]
    while sec_count < 5 and ui < len(uni):
        head = uni_heads[ui % len(uni_heads)]
        if head not in used:
            used.add(head)
            parts.append(f"<h2>{_esc(head)}</h2>")
            body = uni[ui].format(city=city or "apne sheher", niche=name)
            parts.append(f"<p>{_esc(body)}</p>")
            sec_count += 1
        ui += 1

    # Practical "kaise shuru karein" section
    parts.append("<h2>Aaj se kaise shuru karein</h2>")
    parts.append(
        f"<p>Sabse pehle apna Google Business Profile poora bharein — photos, "
        f"timings, services aur phone number. Phir hafte ke 3-4 din ke liye "
        f"posts pehle se plan karein. {name} jaise business me sabse zyada "
        f"asar tab hota hai jab aap apne asli kaam ki photos aur khush "
        f"customers ke reviews dikhate hain. Shuruaat chhoti rakhein, par "
        f"rukne mat dein — 30 din baad farak khud dikhega.</p>"
    )

    # CTA section (ALWAYS appended)
    parts.append("<h2>Free me apni marketing ki shuruaat karein</h2>")
    parts.append(
        f"<p>Apne business ka Google par kitna sahi setup hai, ye 2 minute me "
        f"free me check karein. Hum aapko batayenge kahan kami hai aur kaise "
        f"theek karein. <strong>{_esc(_CTA_LINE)}</strong></p>"
    )

    html_body = "\n".join(parts)
    return {"title": title, "html_body": html_body}


def _focus_body(f: str, name: str, city: str) -> str:
    """Ek content_focus ke liye 2-3 line ka useful Hinglish paragraph."""
    f = (f or "").strip().lower()
    in_city = f" {city} me" if city else ""
    bodies = {
        "reels": (
            f"Short reels (15-30 second) aaj ki sabse badi free reach hain. "
            f"{name} ke liye apne kaam, behind-the-scenes ya ek tip ka reel "
            f"banaye — trending audio lagaye aur hafte me 2-3 reels zaroor "
            f"daalein. Reels nayi audience tak pahunchte hain jo aapko "
            f"follow nahi karti."
        ),
        "reviews": (
            f"Google reviews aapki local ranking ka sabse bada factor "
            f"hain. Har khush customer se politely review maangein — ek "
            f"WhatsApp link bhej dein jisse wo 30 second me review de "
            f"sakein. Jitne zyada 4-5 star reviews, utna upar aapka "
            f"business{in_city} dikhega."
        ),
        "festival posters": (
            f"Har festival ek free marketing mauka hai. {name} "
            f"ke liye Diwali, Holi, Eid, Raksha Bandhan jaise har "
            f"tyohaar pe poster pehle se taiyaar rakhein — apne "
            f"naam, number aur ek chhote offer ke saath. Log "
            f"festival posts zyada share karte hain."
        ),
        "gbp optimization": (
            "Google Business Profile (GBP) free me aapki dukaan "
            "ko 'near me' searches me laata hai. Profile 100% "
            "bharein, hafte me photos daalein, har review ka "
            "reply dein aur sahi category chunein — yahi sabse "
            "sasta aur asar-daar lever hai."
        ),
        "menu posters": (
            "Apne menu ya popular items ke clean posters banaye aur "
            "Instagram + WhatsApp status pe share karein. Photo "
            "acchi ho toh log bina poochhe order kar dete hain — "
            "price clearly likhein."
        ),
        "before-after reels": (
            f"Before-after content sabse zyada bikta hai kyunki "
            f"usme result saaf dikhta hai. {name} ke liye "
            f"customer ki permission le ke transformation reel "
            f"banaye — yahi naye customers ko convince karta hai."
        ),
        "lead forms": (
            "Website ya Instagram bio me ek simple lead-capture form/"
            "link lagaye taaki interested log apna number chhod sakein. "
            "Phir 5 minute ke andar follow-up karein — jaldi reply "
            "karne wala business hi deal jeetta hai."
        ),
        "whatsapp offers": (
            f"WhatsApp par apne regular customers ko hafte me ek "
            f"chhota offer ya update bhejein (broadcast list use "
            f"karein, har kisi ko alag nahi). {name} ke liye yahi "
            f"repeat business laata hai — bilkul free."
        ),
    }
    if f in bodies:
        return bodies[f]
    label = f.replace("-", " ").replace("_", " ")
    return (
        f"{label.capitalize()} {name} ki marketing ka ek important hissa hai. "
        f"Ise regularly aur achhi quality me karein — apne area ka naam "
        f"daalein, photos clear rakhein aur har post pe ek clear call-to-action "
        f"(call/WhatsApp) dein taaki customer turant action le sake."
    )


# ============================================================================ #
# LLM article (LLM-first; template fallback)
# ============================================================================ #


def _strip_md(text: str) -> str:
    """Basic markdown ko clean text me badlo (## , **, * , - ) — clean HTML ke liye."""
    text = text or ""
    text = re.sub(r"`{1,3}", "", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    return text


def _llm_to_html(text: str) -> str:
    """LLM ke '## heading' + paragraph output ko clean <h2>/<p> HTML me badlo.

    Markdown headings/bold strip; har line either <h2> (## se) ya <p>.
    """
    lines = (text or "").splitlines()
    out: list[str] = []
    buf: list[str] = []

    def _flush() -> None:
        if buf:
            para = " ".join(x.strip() for x in buf if x.strip())
            para = _strip_md(para).strip()
            if para:
                out.append(f"<p>{_esc(para)}</p>")
            buf.clear()

    for ln in lines:
        raw = ln.rstrip()
        s = raw.strip()
        if not s:
            _flush()
            continue
        # Heading: markdown (##/###) ya "H2:" marker
        m = re.match(r"^#{2,4}\s+(.+)$", s) or re.match(r"^H2\s*[:\-]\s*(.+)$", s, re.I)
        if m:
            _flush()
            head = _strip_md(m.group(1)).strip().strip(":").strip()
            if head:
                out.append(f"<h2>{_esc(head)}</h2>")
            continue
        # Single-line "**Heading**" only-line => treat as heading
        only_bold = re.match(r"^\*\*(.+?)\*\*:?$", s)
        if only_bold:
            _flush()
            out.append(f"<h2>{_esc(_strip_md(only_bold.group(1)).strip())}</h2>")
            continue
        buf.append(s)
    _flush()
    return "\n".join(out)


def _ensure_cta(html_body: str, name: str) -> str:
    """Article ke end me CTA section pakka karo (LLM ne na daala ho to)."""
    if _AUDIT_URL in html_body and _WA in html_body:
        return html_body
    cta = (
        "<h2>Free me apni marketing ki shuruaat karein</h2>\n"
        f"<p>Apne business ka Google par setup 2 minute me free check karein — "
        f"hum batayenge kahan sudhaar chahiye. <strong>{_esc(_CTA_LINE)}</strong></p>"
    )
    return (html_body.rstrip() + "\n" + cta) if html_body.strip() else cta


# ============================================================================ #
# generate_article — LLM-first, template-guaranteed
# ============================================================================ #


async def generate_article(niche: str, city: str = "", topic: str | None = None) -> dict[str, Any]:
    """Ek genuinely-useful 500-700 word Hinglish article banao.

    Returns: {slug, title, meta_description(<=155), html_body(clean <h2>/<p>),
              niche, city, created_at}. KABHI empty/raise nahi.
    """
    niche = (niche or "general").strip().lower() or "general"
    city = (city or "").strip()
    name = _niche_name(niche)

    if not (topic or "").strip():
        # deterministic-ish topic pick (niche+city pe stable)
        idx = abs(hash(f"{niche}|{city}")) % len(TOPICS)
        topic = TOPICS[idx]
    topic = topic.format(niche=name, city=city or "apne sheher").strip()

    title = topic
    html_body = ""
    provider = "template"

    if free_ai is not None:
        try:
            try:  # semantic cache (flag-gated, OFF default; import-safe)
                from app.cache.semantic_cache import semantic_complete
            except Exception:  # pragma: no cover

                async def semantic_complete(_k, _f, **_kw):  # type: ignore
                    v = _f()
                    if hasattr(v, "__await__"):
                        v = await v
                    return v, {"cache": "disabled"}

            system = (
                "Tu ek expert Indian local-business marketing writer hai. Hinglish "
                "(Hindi + English mix, Roman script) me ek genuinely useful, "
                "practical blog article likh — keyword stuffing ya spam BILKUL "
                "nahi. Structure EXACT ye ho:\n"
                "- Pehle 2-3 line ka intro paragraph (koi heading nahi).\n"
                "- Phir 4 se 6 sections, har section '## ' se shuru hone wala "
                "ek short heading + uske neeche 2-4 line ka paragraph.\n"
                "- Har tip asli aur actionable ho (free tareeke, bina bade budget).\n"
                "Total 500-700 shabd. Koi closing CTA mat likh (wo hum khud "
                "add karenge). Sirf article likh, koi extra commentary nahi."
            )
            user = (
                f"Business type: {name}\n"
                + (f"City/area: {city}\n" if city else "")
                + f"Article ka title/topic: {topic}\n"
                "Is topic par upar diye structure me Hinglish article likho."
            )

            async def _gen_article_text() -> str:
                _txt, _prov = await free_ai.chat(
                    system,
                    [{"role": "user", "content": user}],
                    max_tokens=1100,
                    temperature=0.7,
                )
                # provider closure-capture: cache MISS pe asli provider record ho.
                if _txt and _txt.strip():
                    nonlocal provider
                    provider = _prov
                return (_txt or "").strip()

            # Bulk programmatic-SEO articles = templated niche×city×topic prompts —
            # same niche ke similar topics free-LLM TPD/token jaldi jalate hain. Yeh
            # wrapper near-duplicate prompts ko cache karta (scope=niche isolation).
            # OFF default (SEMANTIC_CACHE flag) -> _gen_article_text() seedha = byte-
            # identical behaviour + asli provider. Fail-open. cache-hit pe provider
            # "llm-cache" (downstream html-quality gate same chalta).
            text, _cinfo = await semantic_complete(
                f"{topic}\n{user}", _gen_article_text, scope=niche
            )
            if (_cinfo.get("cache") or "miss") in ("exact", "semantic"):
                provider = "llm-cache"
            if text and text.strip():
                html_body = _llm_to_html(text)
        except Exception as e:  # free_ai.chat khud nahi raise karta, par safety
            logger.warning(f"generate_article LLM step failed, using template: {e}")

    # LLM ki html me kam-se-kam 2 heading honi chahiye warna template behtar hai
    if html_body.count("<h2>") < 2 or len(re.sub(r"<[^>]+>", "", html_body)) < 350:
        tpl = _template_article(niche, city, topic)
        title = tpl["title"]
        html_body = tpl["html_body"]
        provider = "template"
    else:
        html_body = _ensure_cta(html_body, name)

    # Meta description (<=155 chars) — pehle paragraph ka clean text
    first_p = re.search(r"<p>(.*?)</p>", html_body, re.S)
    raw_meta = re.sub(r"<[^>]+>", "", first_p.group(1)) if first_p else f"{name} ki marketing tips."
    raw_meta = re.sub(r"\s+", " ", raw_meta).strip()
    meta = raw_meta[:152].rstrip(" ,.;:-") + ("…" if len(raw_meta) > 152 else "")

    base = _slugify(f"{niche}-{city}-{topic}") if city else _slugify(f"{niche}-{topic}")
    slug = base

    return {
        "slug": slug,
        "title": title.strip()[:160] or name,
        "meta_description": meta[:155],
        "html_body": html_body,
        "niche": niche,
        "city": city,
        "created_at": _now_iso(),
        "provider": provider,
    }


# ============================================================================ #
# Storage — data/blog/<slug>.json
# ============================================================================ #


def _ensure_dir() -> None:
    try:
        os.makedirs(_BLOG_DIR, exist_ok=True)
    except Exception:
        pass


def save_article(article: dict[str, Any]) -> str:
    """Article ko data/blog/<slug>.json me likho. Slug return karta hai.

    Slug uniqueness guarantee: agar slug already exist karta hai (alag content),
    toh -2, -3 ... suffix lagta hai.
    """
    _ensure_dir()
    slug = _slugify(str(article.get("slug") or article.get("title") or "article"))
    final = slug
    n = 1
    try:
        existing = set(all_slugs())
        while final in existing:
            n += 1
            final = f"{slug}-{n}"
            if n > 50:  # safety
                break
    except Exception:
        pass
    article = dict(article)
    article["slug"] = final
    try:
        path = os.path.join(_BLOG_DIR, f"{final}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(article, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"save_article failed for {final}: {e}")
    return final


def get_article(slug: str) -> dict[str, Any] | None:
    """Ek article load karo (slug se). None agar nahi mila / corrupt."""
    s = _slugify(slug or "")
    if not s:
        return None
    path = os.path.join(_BLOG_DIR, f"{s}.json")
    try:
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def all_slugs() -> list[str]:
    """Saare published article slugs (filename se)."""
    out: list[str] = []
    try:
        for fn in os.listdir(_BLOG_DIR):
            if fn.endswith(".json"):
                out.append(fn[:-5])
    except Exception:
        pass
    return out


def list_articles(limit: int = 200) -> list[dict[str, Any]]:
    """Lightweight list (newest first): slug/title/meta/niche/city/created_at."""
    rows: list[dict[str, Any]] = []
    try:
        for fn in os.listdir(_BLOG_DIR):
            if not fn.endswith(".json"):
                continue
            path = os.path.join(_BLOG_DIR, fn)
            try:
                with open(path, encoding="utf-8") as f:
                    a = json.load(f)
                rows.append(
                    {
                        "slug": a.get("slug") or fn[:-5],
                        "title": a.get("title") or fn[:-5],
                        "meta_description": a.get("meta_description") or "",
                        "niche": a.get("niche") or "",
                        "city": a.get("city") or "",
                        "created_at": a.get("created_at") or "",
                    }
                )
            except Exception:
                continue
    except Exception:
        pass
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    try:
        limit = max(1, min(int(limit), 1000))
    except Exception:
        limit = 200
    return rows[:limit]


# ============================================================================ #
# run_daily_blog — n naye niche×city articles publish karo (never raises)
# ============================================================================ #


async def run_daily_blog(n: int = 3) -> dict[str, Any]:
    """n niche×city combos (jo abhi tak cover nahi hue) chuno, generate + save.

    Returns {"published": n, "slugs": [...]}. log_event("isha","seo_article").
    KABHI raise nahi karta.
    """
    try:
        n = max(1, min(int(n), 25))
    except Exception:
        n = 3

    published: list[str] = []
    try:
        niches = _marketing_niches()
        existing = set(all_slugs())

        # niche×city×topic combos generate karo, jo cover nahi hue unme se pick
        combos: list[tuple] = []
        for niche in niches:
            for city in CITIES:
                # pehla topic stable; uska slug check (variety topics baad me)
                for ti in range(len(TOPICS)):
                    nm = _niche_name(niche)
                    topic = TOPICS[ti].format(niche=nm, city=city or "apne sheher")
                    base = _slugify(f"{niche}-{city}-{topic}")
                    if base not in existing:
                        combos.append((niche, city, TOPICS[ti]))
                        break  # is niche+city ka ek hi topic per run

        # combos ko niche-diversity ke liye interleave karo (round-robin cities)
        combos.sort(key=lambda c: (CITIES.index(c[1]) if c[1] in CITIES else 9, c[0]))

        for niche, city, topic in combos:
            if len(published) >= n:
                break
            try:
                art = await generate_article(niche, city, topic)
                slug = save_article(art)
                if slug:
                    published.append(slug)
                    existing.add(slug)
            except Exception as e:
                logger.warning(f"run_daily_blog: combo {niche}/{city} failed: {e}")

        # log to team feed (isha) — best-effort
        try:
            from app.platform.team import log_event

            log_event(
                "isha",
                "seo_article",
                f"{len(published)} articles published",
                meta={"slugs": published[:20]},
            )
        except Exception:
            pass

        return {"published": len(published), "slugs": published}
    except Exception as e:
        logger.warning(f"run_daily_blog failed: {e}")
        try:
            from app.platform.team import log_event

            log_event("isha", "seo_article", f"blog crash: {e}", status="error")
        except Exception:
            pass
        return {"published": len(published), "slugs": published, "error": str(e)}


__all__ = [
    "TOPICS",
    "CITIES",
    "generate_article",
    "save_article",
    "get_article",
    "all_slugs",
    "list_articles",
    "run_daily_blog",
]
