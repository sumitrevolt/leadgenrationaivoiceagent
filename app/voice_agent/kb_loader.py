"""
Knowledge Base Loaders
======================

Helpers to *populate* the KnowledgeBase (app.voice_agent.knowledge_base) se
content. Yeh Retell/Vapi ke "Add knowledge source" flow jaisa hai:
  - niche FAQs + common business FAQs (built-in, no deps)
  - raw text / pasted docs
  - website sync (URL -> HTML strip -> chunks), defensive (fetch fail par skip)

Usage:
    from app.voice_agent.kb_loader import bootstrap_default_kb, load_from_website

    kb = bootstrap_default_kb()          # niche + business FAQs pre-loaded
    load_from_website(kb, "https://client.com", namespace="solar_commercial")

    ans = kb.grounded_answer("pricing kya hai?", namespace="_global")
"""
from __future__ import annotations

from typing import List, Optional

try:
    from app.utils.logger import setup_logger
    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging
    logger = logging.getLogger(__name__)

from app.voice_agent.knowledge_base import (
    KnowledgeBase,
    chunk_text,
    get_knowledge_base,
)


# --------------------------------------------------------------------------- #
# Common business FAQs — har niche ke liye relevant (LeadGen AI ka apna pitch).
# Yeh natural_dialog.DEFAULT_KNOWLEDGE["_global"] ke saath consistent hai.
# --------------------------------------------------------------------------- #
COMMON_BUSINESS_FAQS: List[str] = [
    "Hum aapke business ke potential customers ko AI voice agent se call karke "
    "qualified leads laate hain — aap sirf interested customers se baat karte ho.",
    "Pricing per qualified lead hoti hai, ₹200 se ₹500 ke beech. Aap sirf result "
    "ke paise dete ho — koi fixed mahina kharcha nahi.",
    "Demo bilkul free hai. 15 minute me dikha dete hain ki system aapke business "
    "ke liye kaise leads laata hai.",
    "Aapko kuch setup nahi karna. Hum poora system handle karte hain — scripting, "
    "calling, follow-up sab.",
    "Leads seedha aapke WhatsApp par ya aapke CRM (HubSpot/Google Sheets) me "
    "deliver ho jaate hain, real-time.",
    "AI voice agent aapke business ke hisaab se customer se baat karta hai, unhe "
    "qualify karta hai, aur sirf serious leads aage bhejta hai.",
    "Aap kisi bhi waqt start ya pause kar sakte ho — koi lambe contract ki "
    "majboori nahi.",
    "Calls aapke kaam ke ghanton me hoti hain (din me), DND rules ka dhyaan rakhte "
    "hue — compliance handle hum karte hain.",
]


def load_from_text(
    kb: KnowledgeBase,
    text: str,
    namespace: str = "default",
    source: Optional[str] = None,
) -> int:
    """
    Raw text ya pasted doc ko chunk + KB me add karo.

    Args:
        kb: KnowledgeBase instance.
        text: koi bhi plain text (FAQ doc, brochure, notes).
        namespace: client/niche scope.
        source: label (e.g. "brochure", "pasted").

    Returns:
        Number of chunks added.
    """
    if not (text or "").strip():
        return 0
    added = kb.add_documents([text], source=source or "text", namespace=namespace)
    logger.info(f"KB '{namespace}': loaded {added} chunk(s) from text source.")
    return added


def load_niche_faqs(kb: KnowledgeBase, namespace: str = "_global") -> int:
    """
    app.niches.NICHES + common business FAQs se KB entries banao.

    Har niche ke liye uske naam, pitch_hook aur qualification questions se
    grounded-answer-able facts bante hain, aur woh us niche ke namespace (niche
    key) me jaate hain. Common business FAQs `namespace` (default "_global") me
    bhi jaate hain taaki har conversation me available rahein.

    Args:
        kb: KnowledgeBase instance.
        namespace: jahan common business FAQs jaayein (default "_global").

    Returns:
        Total chunks added across all namespaces.
    """
    total = 0

    # 1) Common business FAQs -> global namespace
    total += kb.add_documents(
        COMMON_BUSINESS_FAQS, source="business_faq", namespace=namespace
    )

    # 2) Per-niche facts -> har niche ka apna namespace
    try:
        from app.niches import NICHES
    except Exception as e:  # pragma: no cover
        logger.warning(f"NICHES import failed, only common FAQs loaded: {e}")
        return total

    for niche_key, cfg in (NICHES or {}).items():
        facts: List[str] = []
        name = cfg.get("name", niche_key.replace("_", " ").title())
        hook = cfg.get("pitch_hook")
        deal = cfg.get("avg_deal_value")

        facts.append(
            f"{name} ke liye hum specially leads laate hain — "
            f"aapke type ke business ke potential customers ko call karke qualify karte hain."
        )
        if hook:
            facts.append(f"{name} ke liye hamara focus: {hook}.")
        if deal:
            facts.append(
                f"{name} jaise high-ticket business (avg deal value {deal}) ke liye "
                f"ek qualified lead bhi kaafi valuable hoti hai."
            )

        qs = cfg.get("qualification_questions") or []
        if qs:
            facts.append(
                f"{name} leads qualify karte waqt hum aise sawaal poochhte hain: "
                + "; ".join(q.strip() for q in qs if q and q.strip())
                + "."
            )

        # Rich end-customer domain facts (niche_knowledge pack) — yahi se agent
        # client ke offering ka grounded jawab deta hai (subsidy, EMI, process,
        # warranty...). Sirf builtin niches ke paas pack hota hai; custom niches
        # apne thin SAAS facts ke saath rehte hain.
        try:
            from app.niche_knowledge import NICHE_KNOWLEDGE, knowledge_facts
            if niche_key in NICHE_KNOWLEDGE:
                facts.extend(knowledge_facts(niche_key))
        except Exception as e:  # pragma: no cover
            logger.debug(f"niche_knowledge facts skipped for {niche_key}: {e}")

        # niche-specific facts apne namespace me + global me bhi (taaki default
        # KB me sab niches ki value-prop available rahe).
        n1 = kb.add_documents(facts, source=f"niche:{niche_key}", namespace=niche_key)
        n2 = kb.add_documents(facts, source=f"niche:{niche_key}", namespace=namespace)
        total += n1 + n2

    logger.info(f"KB: loaded niche FAQs — {total} chunk(s) total.")
    return total


def load_from_website(
    kb: KnowledgeBase,
    url: str,
    namespace: str = "default",
    timeout: float = 15.0,
) -> int:
    """
    URL fetch karo, HTML strip karke text nikaalo, chunk + KB me add karo.
    Retell/Vapi ke "sync KB from your website" jaisa.

    Defensive: koi bhi network / parse error par gracefully 0 return karta hai
    (crash nahi). httpx + BeautifulSoup optional hain — na hon to skip.

    Args:
        kb: KnowledgeBase instance.
        url: website URL (https://...).
        namespace: client/niche scope.
        timeout: fetch timeout seconds.

    Returns:
        Number of chunks added (0 on any failure).
    """
    if not (url or "").strip():
        return 0

    # 1) fetch
    html = ""
    try:
        import httpx
        headers = {"User-Agent": "Mozilla/5.0 (LeadGenAI KB sync)"}
        resp = httpx.get(url, timeout=timeout, follow_redirects=True, headers=headers)
        resp.raise_for_status()
        html = resp.text or ""
    except Exception as e:
        logger.warning(f"KB website fetch failed for {url}: {e}")
        return 0

    if not html.strip():
        return 0

    # 2) strip HTML -> text
    text = _html_to_text(html)
    if not text.strip():
        logger.warning(f"KB website {url}: no extractable text.")
        return 0

    # 3) chunk + add
    chunks = chunk_text(text)
    added = kb.add_documents(chunks, source=f"website:{url}", namespace=namespace)
    logger.info(f"KB '{namespace}': synced {added} chunk(s) from {url}.")
    return added


def _html_to_text(html: str) -> str:
    """HTML -> readable text. BeautifulSoup prefer; else regex fallback."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        # remove non-content elements
        for tag in soup(["script", "style", "noscript", "head", "header",
                         "footer", "nav", "svg", "form"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
    except Exception as e:
        logger.debug(f"BeautifulSoup unavailable/failed ({e}); regex strip.")
        import re
        # drop scripts/styles, then tags
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)

    # normalize whitespace, keep paragraph breaks
    import re as _re
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    cleaned = "\n".join(lines)
    cleaned = _re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def bootstrap_default_kb() -> KnowledgeBase:
    """
    Singleton KnowledgeBase ko niche + common business FAQs ke saath pre-load
    karke return karo. App startup par ek baar call karne ke liye ideal.

    Usage:
        from app.voice_agent.kb_loader import bootstrap_default_kb
        kb = bootstrap_default_kb()
        ans = kb.grounded_answer("pricing kya hai?", namespace="_global")
        ans2 = kb.grounded_answer("roof suitability?", namespace="solar_commercial")

    Returns:
        The pre-loaded singleton KnowledgeBase.
    """
    kb = get_knowledge_base()
    try:
        load_niche_faqs(kb, namespace="_global")
    except Exception as e:  # pragma: no cover
        logger.warning(f"bootstrap_default_kb: niche FAQ load issue: {e}")
    logger.info(f"KB bootstrap complete — {kb.stats()}")
    return kb


__all__ = [
    "load_niche_faqs",
    "load_from_text",
    "load_from_website",
    "bootstrap_default_kb",
    "COMMON_BUSINESS_FAQS",
]
