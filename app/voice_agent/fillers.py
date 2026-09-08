"""
Natural Thinking-Filler Injector
================================

LLM jab soch raha hota hai (network + inference latency), tab silence aata hai —
phone par yeh silence robotic / awkward lagta hai ("kya line cut gayi?"). Real
insaan us gap me chhote natural fillers bolta hai: "ek second...", "hmm...",
"dekhiye...", "let me check...". Yeh module wahi karta hai — bot ko *human* feel
deta hai jab tak asli jawab generate ho raha ho. (Retell/Vapi me ise "filler /
backchannel audio" kehte hain.)

Pure python, no external services, import-safe. Anti-repeat memory rakhta hai
taaki same filler lagataar repeat na ho (jo turant robotic feel deta hai).

Usage:
    from app.voice_agent.fillers import pick_filler, FillerPlayer

    # one-shot:
    print(pick_filler(lang="hinglish", context="thinking"))   # "ek second..."

    # stateful (anti-repeat) — recommended per-call:
    fp = FillerPlayer(lang="hinglish")
    while waiting_for_llm:
        say(fp.next("thinking"))      # har baar alag filler, repeat avoid
    # phir asli reply bol do
"""

from __future__ import annotations

import random

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Filler banks — language-aware (hinglish / hi / en), category-wise.
# Categories:
#   thinking     -> LLM soch raha hai, latency mask karo ("ek second...")
#   acknowledge  -> customer ne abhi kuch kaha, sun liya signal ("haan...", "achha")
#   transition   -> topic / step badalte waqt smooth bridge ("dekhiye...", "to...")
#   empathy      -> objection / hesitation par warmth ("samajh sakti hoon...")
# --------------------------------------------------------------------------- #
FILLERS: dict[str, dict[str, list[str]]] = {
    "hinglish": {
        "thinking": [
            "hmm theek hai...",
            "ji dekhiye...",
            "haan bilkul...",
            "let me check...",
            "ji main samajh rahi hoon...",
            "achha...",
            "ji dekh leti hoon...",
        ],
        "acknowledge": [
            "haan...",
            "achha...",
            "theek hai...",
            "samajh gayi...",
            "bilkul...",
            "ji haan...",
            "hmm...",
            "right...",
        ],
        "transition": [
            "to dekhiye...",
            "achha ek baat...",
            "waise...",
            "to phir...",
            "ek cheez bataiye...",
            "chaliye...",
        ],
        "empathy": [
            "samajh sakti hoon...",
            "bilkul, koi baat nahi...",
            "haan sahi baat hai...",
            "main samajhti hoon...",
            "no problem...",
            "koi pressure nahi...",
        ],
    },
    "hi": {
        "thinking": [
            "ek pal...",
            "ek kshan...",
            "haan dekhiye...",
            "thodi der...",
            "rukiye zara...",
            "achha...",
        ],
        "acknowledge": [
            "haan...",
            "achha...",
            "theek hai...",
            "ji...",
            "samajh gaya...",
            "bilkul...",
        ],
        "transition": [
            "to...",
            "achha ek baat...",
            "ek prashn...",
            "aage badhte hain...",
            "chaliye...",
        ],
        "empathy": [
            "main samajhta hoon...",
            "koi baat nahi...",
            "bilkul sahi...",
            "aapki baat sahi hai...",
        ],
    },
    "en": {
        "thinking": [
            "one second...",
            "let me check...",
            "hmm, okay...",
            "just a moment...",
            "give me a sec...",
            "right...",
            "let me see...",
        ],
        "acknowledge": [
            "yeah...",
            "okay...",
            "got it...",
            "sure...",
            "right...",
            "mm-hmm...",
            "understood...",
        ],
        "transition": [
            "so...",
            "okay, so...",
            "one thing...",
            "by the way...",
            "alright...",
            "let me ask you...",
        ],
        "empathy": [
            "i understand...",
            "no worries...",
            "that's fair...",
            "totally get it...",
            "i hear you...",
            "no pressure...",
        ],
    },
}

_DEFAULT_LANG = "hinglish"
_DEFAULT_CATEGORY = "thinking"


def _resolve_lang(lang: str | None) -> str:
    """User-provided lang ko supported bank key me map karo (defensive)."""
    if not lang:
        return _DEFAULT_LANG
    low = lang.lower().strip()
    if low in FILLERS:
        return low
    # common aliases
    if low in ("hindi", "hi-in", "in"):
        return "hi"
    if low in ("english", "en-in", "en-us", "eng"):
        return "en"
    if "hing" in low or low in ("hi-en", "en-hi"):
        return "hinglish"
    return _DEFAULT_LANG


def _resolve_category(category: str | None) -> str:
    if not category:
        return _DEFAULT_CATEGORY
    low = category.lower().strip()
    aliases = {
        "think": "thinking",
        "latency": "thinking",
        "wait": "thinking",
        "ack": "acknowledge",
        "backchannel": "acknowledge",
        "bridge": "transition",
        "transit": "transition",
        "empathize": "empathy",
        "empathetic": "empathy",
        "reassure": "empathy",
    }
    low = aliases.get(low, low)
    return low if low in FILLERS[_DEFAULT_LANG] else _DEFAULT_CATEGORY


def pick_filler(
    lang: str = "hinglish",
    context: str = "thinking",
    avoid: str | None = None,
) -> str:
    """Ek chhota natural filler return karo (language + context aware).

    Args:
        lang:     "hinglish" | "hi" | "en" (aliases handled).
        context:  "thinking" | "acknowledge" | "transition" | "empathy".
        avoid:    (optional) ek filler jo abhi-abhi bola gaya — usse repeat na karo.

    Returns:
        ek short filler string, e.g. "ek second...".
    """
    lkey = _resolve_lang(lang)
    ckey = _resolve_category(context)
    options = list(FILLERS[lkey].get(ckey) or FILLERS[lkey][_DEFAULT_CATEGORY])

    if avoid and len(options) > 1:
        options = [o for o in options if o != avoid] or options

    return random.choice(options)


class FillerPlayer:
    """Stateful filler generator with anti-repeat memory.

    Per-call ek instance banao. `next(category)` har baar ek naya filler deta hai
    aur recent ones ko avoid karta hai — taaki lagataar same word repeat na ho
    (jo turant robotic feel deta hai).

    Usage:
        fp = FillerPlayer(lang="hinglish", memory=2)
        fp.next("thinking")      # "ek second..."
        fp.next("thinking")      # "hmm theek hai..."  (pichla repeat nahi)
        fp.reset()               # naya call shuru
    """

    def __init__(self, lang: str = "hinglish", memory: int = 2):
        """
        Args:
            lang:    default language ("hinglish" | "hi" | "en").
            memory:  kitne recent fillers yaad rakhne hain (anti-repeat window).
        """
        self.lang = _resolve_lang(lang)
        self.memory = max(1, int(memory))
        self._recent: list[str] = []

    def next(self, category: str = "thinking", lang: str | None = None) -> str:
        """Agla anti-repeat filler do.

        Args:
            category:  "thinking" | "acknowledge" | "transition" | "empathy".
            lang:      (optional) is call ke liye language override.

        Returns:
            ek filler string jo recent window me na ho (jitna possible).
        """
        lkey = _resolve_lang(lang) if lang else self.lang
        ckey = _resolve_category(category)
        options = list(FILLERS[lkey].get(ckey) or FILLERS[lkey][_DEFAULT_CATEGORY])

        # recent fillers hata do; agar sab hat gaye to full set par fall back.
        fresh = [o for o in options if o not in self._recent]
        if not fresh:
            fresh = options

        choice = random.choice(fresh)

        # anti-repeat memory update (bounded window).
        self._recent.append(choice)
        if len(self._recent) > self.memory:
            self._recent.pop(0)

        return choice

    @property
    def last(self) -> str | None:
        """Sabse recent diya gaya filler (ya None)."""
        return self._recent[-1] if self._recent else None

    def reset(self) -> None:
        """Anti-repeat memory clear karo (naya call shuru)."""
        self._recent.clear()


__all__ = ["pick_filler", "FillerPlayer", "FILLERS"]
