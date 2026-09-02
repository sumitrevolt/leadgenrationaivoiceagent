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

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)

from collections.abc import Iterable

from app.voice_agent.knowledge_base import KnowledgeBase, chunk_text, get_knowledge_base

# --------------------------------------------------------------------------- #
# Common business FAQs — har niche ke liye relevant (LeadGen AI ka apna pitch).
# Yeh natural_dialog.DEFAULT_KNOWLEDGE["_global"] ke saath consistent hai.
# --------------------------------------------------------------------------- #
COMMON_BUSINESS_FAQS: list[str] = [
    "LeadGen AI ka main product AI Automated Marketing hai — Instagram, Facebook "
    "aur Google pe posts, ads aur profile boost AI se automatic hota hai.",
    "Pricing: Main plan ₹1,999/mahina, Advanced/Combo ₹5,999/mahina. Growth ₹2,999 "
    "legacy hidden hai. Per-lead paisa nahi — flat monthly SaaS.",
    "7 din FREE trial bina card. Aapko khud posts nahi banani — AI banata hai, "
    "aap approve ya publish karte ho.",
    "Advanced plan me inquiry pe AI voice callback bhi milta hai (feature), "
    "lekin main product marketing automation hai — marketing+voice bundle framing mat use karo.",
    "Demo bilkul free hai. 15 minute me dikha dete hain ki system aapke business "
    "ke liye kaise content aur leads laata hai.",
    "Aap kisi bhi waqt start ya pause kar sakte ho — koi lambe contract ki majboori nahi.",
]


def load_from_text(
    kb: KnowledgeBase,
    text: str,
    namespace: str = "default",
    source: str | None = None,
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


def load_niche_faqs(
    kb: KnowledgeBase,
    namespace: str = "_global",
    only: str | Iterable[str] | None = None,
) -> int:
    """
    app.niches.NICHES + common business FAQs se KB entries banao.

    Har niche ke liye uske naam, pitch_hook aur qualification questions se
    grounded-answer-able facts bante hain, aur woh us niche ke namespace (niche
    key) me jaate hain. Common business FAQs `namespace` (default "_global") me
    bhi jaate hain taaki har conversation me available rahein.

    Args:
        kb: KnowledgeBase instance.
        namespace: jahan common business FAQs jaayein (default "_global").
        only: ADR-104 — niche scoping. `None` (default) = LEGACY behaviour, saare
            NICHES + common FAQs seed hote hain (bootstrap_default_kb ke 4 global
            callers isi pe depend karte hain — behaviour byte-for-byte same).
            str ya iterable dene par SIRF wahi niche(s) seed hote hain aur common
            business FAQs SKIP hote hain (wo niche-data nahi hai). Filtering
            expensive doc-generation/embed/upsert se PEHLE hoti hai, isliye ek
            niche maangne par doosre niches ka koi kaam nahi hota.

    Raises:
        ValueError: `only` me koi aisa niche key ho jo NICHES me nahi (fail-fast,
            taaki typo chupchaap "0 chunks seeded" me na badle).

    Returns:
        Total chunks added across all namespaces.
    """
    total = 0

    # 2) Per-niche facts -> har niche ka apna namespace
    try:
        from app.niches import NICHES
    except Exception as e:  # pragma: no cover
        logger.warning(f"NICHES import failed, only common FAQs loaded: {e}")
        if only is None:
            # legacy: common FAQs abhi bhi seed karo
            return kb.add_documents(
                COMMON_BUSINESS_FAQS, source="business_faq", namespace=namespace
            )
        return 0

    # ADR-104: `only` ko normalize + validate karo — expensive kaam se PEHLE.
    wanted: set[str] | None = None
    if only is not None:
        raw = [only] if isinstance(only, str) else list(only)
        wanted = {str(n).strip() for n in raw if str(n).strip()}
        unknown = sorted(wanted - set((NICHES or {}).keys()))
        if unknown:
            raise ValueError(f"load_niche_faqs: unknown niche key(s): {unknown}")

    # 1) Common business FAQs -> global namespace (SIRF legacy/full seed pe;
    #    scoped seed sirf maanga hua niche chhuta hai).
    # replace_source=True (ADR-104 A4.6): existing delete-before-reseed
    # mechanism (see load_from_website + tests/test_kb_delete_before_reseed.py)
    # — bina iske, dobara-bootstrap old text ko orphan chhod deta hai (naya
    # deterministic id != purana), sirf APPEND, kabhi OVERWRITE nahi. Scope
    # (namespace, source) tak seemित — koi doosra source/namespace touch nahi hota.
    if wanted is None:
        total += kb.add_documents(
            COMMON_BUSINESS_FAQS,
            source="business_faq",
            namespace=namespace,
            replace_source=True,
        )

    # Professional telecaller script dataset (pure-data, import-safe) — har niche
    # ke researched opening / discovery / objection-rebuttals / value-lines /
    # closing ko KB me seed karte hain taaki retrieval pe salesperson-grade
    # language surface ho (TelecallerBrain._kb_facts inhe pick karta hai).
    try:
        from app.voice_agent.niche_scripts import kb_documents as _script_docs
    except Exception as e:  # pragma: no cover
        logger.debug(f"niche_scripts kb_documents unavailable: {e}")
        _script_docs = None

    for niche_key, cfg in (NICHES or {}).items():
        # ADR-104: scoped seed — unrelated niche ka koi doc-generation/embed/upsert
        # nahi. Ye check LOOP ke sabse upar hai (expensive kaam se pehle) — yehi wo
        # jagah hai jiski kami se 4-niche QA run 39 niches seed kar deta tha.
        if wanted is not None and niche_key not in wanted:
            continue
        facts: list[str] = []
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
        # replace_source=True (ADR-104 A4.6 — the duplicate-vector-write fix):
        # NICHES/niche_knowledge text kabhi-kabhi edit hoti hai (pitch_hook
        # wording, naye facts) — bina replace_source ke purana-text ka point
        # `_kb_point_id`(namespace, text) se DIFFERENT id banata (naya
        # deterministic id != purana), to reseed sirf APPEND karta, kabhi
        # OVERWRITE/clean nahi. Yehi ~185x kb_main duplication ka root cause
        # tha (ADR-104 addendum #7 — measured, not assumed). Scope EXACTLY
        # (namespace, source) tak seemित hai (delete_source implementation:
        # knowledge_base.py _QdrantIndex.delete_source) — koi doosra niche,
        # koi doosra source (website:, kb_interview, ...) touch nahi hota.
        n1 = kb.add_documents(
            facts, source=f"niche:{niche_key}", namespace=niche_key, replace_source=True
        )
        n2 = kb.add_documents(
            facts, source=f"niche:{niche_key}", namespace=namespace, replace_source=True
        )
        total += n1 + n2

        # Professional script lines -> SAME per-niche namespace, taaki retrieval
        # pe opening/objection/closing/value surface ho. Covered niche apna
        # script deta hai; uncovered (custom incl.) "general" script pe map.
        # replace_source=True yahan bhi — same reasoning as facts above.
        if _script_docs is not None:
            try:
                sdocs = _script_docs(niche_key)
                if sdocs:
                    total += kb.add_documents(
                        sdocs,
                        source=f"script:{niche_key}",
                        namespace=niche_key,
                        replace_source=True,
                    )
            except Exception as e:  # pragma: no cover
                logger.debug(f"script docs skipped for {niche_key}: {e}")

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
    added = kb.add_documents(
        chunks, source=f"website:{url}", namespace=namespace, replace_source=True
    )
    logger.info(f"KB '{namespace}': synced {added} chunk(s) from {url}.")
    return added


def _html_to_text(html: str) -> str:
    """HTML -> readable text. BeautifulSoup prefer; else regex fallback."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        # remove non-content elements
        for tag in soup(
            ["script", "style", "noscript", "head", "header", "footer", "nav", "svg", "form"]
        ):
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


def seed_niche(kb: KnowledgeBase, niche: str) -> dict:
    """ADR-104: EK niche ka scoped seed + structured (redacted) result.

    `bootstrap_default_kb()` saare 39 niches seed karta hai — wo live voice
    reply-path ke liye kabhi safe nahi tha (dekho ADR-104). Ye uska bounded,
    owned replacement hai: sirf maanga hua niche.

    Result me SIRF safe operational metadata hai — koi document text, prompt,
    transcript, customer data ya secret nahi.

    Returns:
        {"niche", "ok", "chunks", "duration_s", "error_class"}
    """
    import time as _time

    t0 = _time.monotonic()
    try:
        chunks = load_niche_faqs(kb, only=niche)
        return {
            "niche": niche,
            "ok": True,
            "chunks": int(chunks),
            "duration_s": round(_time.monotonic() - t0, 3),
            "error_class": None,
        }
    except Exception as e:
        # error_class only — message me customer/secret data leak ho sakta hai.
        return {
            "niche": niche,
            "ok": False,
            "chunks": 0,
            "duration_s": round(_time.monotonic() - t0, 3),
            "error_class": type(e).__name__,
        }


__all__ = [
    "load_niche_faqs",
    "load_from_text",
    "load_from_website",
    "bootstrap_default_kb",
    "seed_niche",
    "COMMON_BUSINESS_FAQS",
]
