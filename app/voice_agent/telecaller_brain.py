"""
TelecallerBrain — lean, phone-optimized Hinglish sales brain (NO ML overhead).
==============================================================================

WHY THIS EXISTS (vs llm_brain.LLMBrain)
---------------------------------------
LLMBrain carries ML/RAG/feedback machinery — great for web, too heavy and too
verbose for a live PSTN turn where every token = latency = dead air. This brain
is ONE system prompt + direct google.generativeai call (same _init_gemini
pattern as llm_brain), tuned with telecaller research (2025-26):

  * Gong (300M+ calls): permission-based openers hit ~11% success vs 2.3% avg.
  * Voice-AI prompting guides (Vapi/Smith.ai/Retell): 1-2 short sentences per
    turn, EXACTLY one question per turn, acknowledge-confirm-prompt structure.
  * LARA objection handling (Listen-Acknowledge-Respond-Ask); "busy" → offer
    two specific callback slots (alternative close); "not interested" → one
    respectful value-line, then thank + end (respect the no).
  * BANT sequencing: need/pain first, money later — questions woven into
    conversation, never an interrogation checklist.

Usage:
    brain = TelecallerBrain(niche="real_estate", client_name="Sharma Realty")
    text  = await brain.reply(history, user_text)   # "" on any failure
    opener = brain.opening_line()                    # permission-based greet
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Professional telecaller script dataset (pure-data, import-safe). Guarded so a
# missing/broken module can never stop the brain from initializing — get_script
# then degrades to {} and the prompt falls back to niche-data questions.
try:
    from app.voice_agent.niche_scripts import NICHE_SCRIPTS, get_script
except Exception:  # pragma: no cover - pure-data module, but never break the brain
    NICHE_SCRIPTS: dict[str, dict] = {}

    def get_script(_niche: str) -> dict:  # type: ignore[misc]
        return {}


# Readable Hinglish customer-phrase hints for objection keys (prompt me clear
# dikhe ki customer kya bolega) — niche_scripts ke objection dict keys ke liye.
_OBJ_HINT = {
    "mehenga": "mehnga hai / budget zyada",
    "abhi_nahi": "abhi nahi / baad me dekhte hain",
    "soch_ke": "soch ke batata hoon",
    "pehle_se_hai": "pehle se hai / le rakha hai",
    "bharosa": "bharosa nahi / genuine ho kya",
}

# Default qualification flow when the niche is unknown/missing.
_GENERIC_QUESTIONS = [
    "Aap apne business ke liye naye customers abhi kahan se laate hain?",
    "Ek mahine me approx kitni nayi inquiries aati hain aapke paas?",
    "Agar ready qualified leads milne lagein, toh kab se shuru karna chahenge?",
]

_MAX_HISTORY_TURNS = 8  # last ~8 turns to keep prompt (and latency) small
_GEN_CONFIG = {
    "temperature": 0.5,
    "max_output_tokens": 60,
}  # brevity (phone) — 60 so closes don't truncate
_REPLY_TIMEOUT_S = 4.5  # itne me LLM reply nahi => "" -> instant script_fallback (voice me 6s+ = dead-air "reply nahi deta"; mistral warm ~1-2s)

# KB-grounding (Qdrant niche + client KB) — phone hot path, so keep it tight:
# top-2 facts, short timeout, low score gate (works for both e5-cosine and
# keyword TF-IDF backends; LLM ko bola jata hai ki sirf relevant ho to use kare).
_KB_TOP_K = 2
_KB_TIMEOUT_S = 1.5
_KB_MIN_SCORE = 0.05


def _short_hook(hook: str, max_len: int = 90) -> str:
    """pitch_hook ka pehla, chhota hissa — opener me poora English hook lamba
    lagta hai. Split on em-dash/hyphen clause, cap length.

    English-heavy hook (B2B value-prop) end-customer greeting me NAHI daalte —
    "" return karte taaki greeting clean Hinglish fallback (opening_line ke
    `if hook:` else-branch) pe jaaye. (Test: solar ka poora-English pitch_hook
    Hindi greeting me leak ho raha tha → mixed-language + 41-word too-long.)"""
    h = (hook or "").strip()
    if not h:
        return ""
    _low = " " + h.lower() + " "
    _en = (" your ", " the ", " before ", " with ", " every ", " you ", " not ", " of ",
           " who ", " and ", "qualified", "homeowners", "borrowers", "patients",
           "aspirants", "suppliers", "inquiries", "booked", "replaced", "calendar")
    if sum(1 for m in _en if m in _low) >= 2:
        return ""  # English B2B hook — greeting me mat daalo
    for sep in ("—", " - ", ";"):
        if sep in h:
            h = h.split(sep)[0].strip()
            break
    return h[:max_len].rstrip(" ,.-")


# --------------------------------------------------------------------------- #
# KB singleton — bootstrap ONCE (niche + business FAQs seed) phir reuse. App
# startup KB ko seed nahi karta, isliye grounding ke liye yahin ensure karte
# hain; bootstrap_default_kb ko har turn call karna KB ko dobara-dobara seed kar
# deta, to ek hi baar (cached). Duplicate texts retrieve par dedupe ho jaate.
# --------------------------------------------------------------------------- #
_KB_SINGLETON: Any = None
_KB_TRIED = False


def _get_kb():
    """Cached, bootstrapped KnowledgeBase (None agar bootstrap fail)."""
    global _KB_SINGLETON, _KB_TRIED
    if _KB_TRIED:
        return _KB_SINGLETON
    _KB_TRIED = True
    try:
        from app.voice_agent.kb_loader import bootstrap_default_kb

        _KB_SINGLETON = bootstrap_default_kb()
    except Exception as e:  # pragma: no cover
        logger.debug(f"[telecaller-brain] KB bootstrap failed: {e}")
        _KB_SINGLETON = None
    return _KB_SINGLETON


class TelecallerBrain:
    """Phone-call brain: free-AI provider chain (free_ai.chat: Cerebras/Groq/
    OpenRouter) as PRIMARY, Gemini-direct (multi-key rotation) as fallback, no ML
    pipeline. KB-grounded (niche + client facts). Raises on init only if NEITHER
    Gemini NOR a free provider key is configured (caller falls back)."""

    def __init__(
        self, niche: str = "general", client_name: str = "Demo Co", client_id: str | None = None
    ) -> None:
        self.niche = (niche or "general").strip() or "general"
        self.client_name = (client_name or "Demo Co").strip() or "Demo Co"
        self.client_id = (str(client_id).strip() or None) if client_id else None
        # Agent memory (cross-session lead recall) subject — None by DEFAULT.
        # 🔒 SECURITY: client_id ko default subject MAT banao — warna ek client ke
        # SAARE leads ek hi bucket (lead:<client_id>) share karte => Lead A ka PII
        # (budget/identity) Lead B ki call me recall+inject ho sakta. Per-lead memory
        # ke liye call-session set_memory_subject(<lead_id/caller_phone>) bulaaye; jab
        # tak na bulaaye memory INERT (safe). AGENT_MEMORY flag OFF => waise bhi no-op.
        self.memory_subject: str | None = None

        # Multi-key rotation pool (free-AI resilience): STT + LLM share a Gemini
        # quota PER KEY, so we rotate to the next key on a quota/429 error. The
        # pool reads GEMINI_API_KEYS then GEMINI_API_KEY — so a single key still
        # works exactly as before.
        try:
            from app.voice_agent.gemini_keys import (
                active_key,
                advance_key,
                is_quota_error,
                key_count,
            )

            self._active_key = active_key
            self._advance_key = advance_key
            self._key_count = key_count
            self._is_quota_error = is_quota_error
        except Exception:  # pool import failed — degrade to single settings key
            self._active_key = lambda: (settings.gemini_api_key or "").strip()
            self._advance_key = lambda bad="": (settings.gemini_api_key or "").strip()
            self._key_count = lambda: 1 if (settings.gemini_api_key or "").strip() else 0
            self._is_quota_error = lambda e: False

        # Free-AI provider chain (Cerebras → Groq → OpenRouter) — PRIMARY now
        # (free, fast, quota-resilient); Gemini is the fallback. Shared layer:
        # app.voice_agent.free_ai (OpenAI-compatible; saari keys OPTIONAL).
        try:
            from app.voice_agent.free_ai import PROVIDERS_AVAILABLE

            self._free_ai_providers = [p for p, ok in PROVIDERS_AVAILABLE.items() if ok]
        except Exception:
            self._free_ai_providers = []

        # Gemini = fallback link (multi-key rotation). Key ho to init karo; warna
        # self._genai=None reh jaata hai aur brain free_ai.chat se chalta hai.
        first_key = self._active_key() or (settings.gemini_api_key or "").strip()
        self._genai = None
        self.model = "gemini-2.5-flash-lite"
        if first_key:
            try:
                # Same pattern as llm_brain._init_gemini — direct google.generativeai.
                import google.generativeai as genai

                genai.configure(api_key=first_key)
                self._genai = genai
                model = (settings.default_llm or "").strip()
                if "gemini" not in model.lower() or "vertex" in model.lower():
                    model = "gemini-2.5-flash-lite"  # highest free-tier quota
                self.model = model
            except Exception as e:  # SDK/config issue — free providers carry on
                logger.warning(f"[telecaller-brain] Gemini init skipped: {e}")
                self._genai = None

        # Brain usable agar Gemini ho YA koi free provider configured ho. Dono
        # nahi => raise (vobiz_stream LLMBrain par fall back kar leta hai).
        if self._genai is None and not self._free_ai_providers:
            raise ValueError(
                "TelecallerBrain needs a Gemini key (GEMINI_API_KEY/GEMINI_API_KEYS) "
                "OR a free provider key (GROQ_API_KEY/CEREBRAS_API_KEY/OPENROUTER_API_KEY)"
            )

        self._load_niche()
        self.system_prompt = self._build_system_prompt()
        logger.info(
            f"[telecaller-brain] ready niche={self.niche} model={self.model} "
            f"gemini_keys={self._key_count()} free_ai={self._free_ai_providers or 'none'} "
            f"client_id={self.client_id}"
        )

    def set_memory_subject(self, subject_id: str | None) -> None:
        """Call-session per-lead memory subject set kare (e.g. lead_id / phone).
        AGENT_MEMORY flag OFF ho to iska koi asar nahi (recall/remember no-op)."""
        if subject_id:
            self.memory_subject = str(subject_id).strip() or self.memory_subject

    # ------------------------------------------------------------------ #
    # Niche data (pitch_hook + qualification_questions from app.niches)
    # ------------------------------------------------------------------ #
    def _load_niche(self) -> None:
        data: dict = {}
        try:
            from app.niches import NICHES

            data = NICHES.get(self.niche) or {}
        except Exception as e:  # niches module broken should not kill calls
            logger.warning(f"[telecaller-brain] niches load failed: {e}")
        self.niche_name = data.get("name") or self.niche.replace("_", " ").title()
        self.pitch_hook = (data.get("pitch_hook") or "").strip()
        qs = data.get("qualification_questions") or []
        self.questions: list[str] = [str(q).strip() for q in qs if str(q).strip()] or list(
            _GENERIC_QUESTIONS
        )
        # Numbers the agent is ALLOWED to say — only what niche data provides.
        nums = []
        if data.get("avg_ticket_inr"):
            nums.append(f"typical deal/ticket size: {data['avg_ticket_inr']}")
        if data.get("avg_deal_value"):
            nums.append(f"average deal value: {data['avg_deal_value']}")
        self.allowed_numbers = "; ".join(nums)

        # ── niche_database schema injection ──────────────────────────────────
        # NICHE_CALL_SCHEMA se script_context + collect_during questions inject
        # karo — yeh brain ko call se PEHLE niche-specific context deta hai.
        # Defensive: import fail / key missing = no change (niches.py questions used).
        self.niche_script_context: str = ""
        self.collect_during_questions: list[str] = []
        try:
            from app.platform.niche_database import NICHE_CALL_SCHEMA

            schema = NICHE_CALL_SCHEMA.get(self.niche, {})
            self.niche_script_context = (schema.get("script_context") or "").strip()
            raw_cd = schema.get("collect_during") or []
            self.collect_during_questions = [
                str(q.get("question") or "").strip()
                for q in raw_cd
                if isinstance(q, dict) and str(q.get("question") or "").strip()
            ]
            # collect_during se better questions mile to questions override karo
            if self.collect_during_questions:
                self.questions = self.collect_during_questions
            if self.niche_script_context:
                logger.debug(
                    f"[telecaller-brain] niche_database schema loaded for {self.niche} "
                    f"({len(self.collect_during_questions)} collect_during qs)"
                )
        except Exception as _e:
            logger.debug(f"[telecaller-brain] niche_database schema skip: {_e}")

    # ------------------------------------------------------------------ #
    # System prompt — research-distilled rules + 3 few-shot exchanges
    # ------------------------------------------------------------------ #
    def _build_system_prompt(self) -> str:
        # Professional researched script for this niche (opening/discovery/
        # objections/value/closing). Covered niche => apna; uncovered => general.
        s = get_script(self.niche) or {}

        # Discovery flow that DRIVES the call: covered niche ke liye script ke
        # professional questions; uncovered (incl. custom) ke liye niche-data
        # qualification questions (general script se zyada specific). Hamesha
        # ek non-empty ordered list milti hai.
        script_disc = [str(q).strip() for q in (s.get("discovery") or []) if str(q).strip()]
        disc = (script_disc if self.niche in NICHE_SCRIPTS else self.questions) or self.questions
        q_block = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(disc))
        first_q = disc[0] if disc else "Aap exactly kis cheez ki talaash me hain?"

        hook = self.pitch_hook or "businesses ko ready qualified leads dilana"
        hook_short = _short_hook(hook) or "qualified leads"
        numbers_line = (
            self.allowed_numbers or "(koi nahi — matlab tum KOI number/price quote nahi kar sakti)"
        )

        # Compact professional-script reference blocks (style guide — copy-paste nahi).
        opening = (s.get("opening") or "").strip()
        closing = (s.get("closing") or "").strip()
        value_lines = [str(v).strip() for v in (s.get("value_lines") or []) if str(v).strip()]
        value_block = (
            "\n".join(f"- {v}" for v in value_lines) or "- (niche ke hisaab se ek crisp value-line)"
        )
        obj_block = (
            "\n".join(
                f'- Customer: "{_OBJ_HINT.get(k, k)}" -> Tum: {v}'
                for k, v in (s.get("objections") or {}).items()
                if str(v).strip()
            )
            or "- (empathize karo, ek chhoti value-line do, phir aage badho)"
        )
        script_block = (
            (f"Opening (permission-based): {opening}\n" if opening else "")
            + f"Discovery questions (ISI ORDER me, ek turn me sirf EK; jo customer PEHLE bata chuka woh SKIP):\n{q_block}\n"
            + f"Value lines (jab pitch karni ho):\n{value_block}"
            + (
                f"\nClosing (interest dikhe to appointment/visit/callback BOOK karo): {closing}"
                if closing
                else ""
            )
        )

        # Niche-database context block (call schema se inject hota hai call se pehle)
        niche_ctx_block = (
            f"\nNICHE CALL CONTEXT (call ke liye specific — follow karo): {self.niche_script_context}"
            if getattr(self, "niche_script_context", "")
            else ""
        )

        return f"""Tum "Swara" ho — {self.client_name} ki professional Indian female telecaller. Tum ek TOP professional Indian telecaller ho (noob nahi). Confident, warm, crisp. Customer ke har jawab ko sun ke uske hisab se aage badho — ratta-maar nahi. Tum ek LIVE PHONE CALL par ho (text chat nahi); bhasha natural Hinglish (Hindi-English mix), awaaz bilkul insaan jaisi.

CLIENT: {self.client_name} | NICHE: {self.niche_name}{niche_ctx_block}
VALUE LINE (pitch hook): {hook}

PROFESSIONAL SCRIPT (inhi lines/style me baat karo, copy-paste mat karo, natural raho):
{script_block}

OBJECTION HANDLING (agar customer aise bole to aise jawab do, phir aage badho):
{obj_block}

ALLOWED NUMBERS/PRICES (sirf yehi bol sakti ho): {numbers_line}

HARD RULES (har turn, bina exception):
1. Tum phone par ho. Insaan ki tarah baat karo: CHHOTA, seedha, turant. EK reply = MAX 1 vakya, 8-15 shabd. KABHI do sentence nahi.
2. KABHI apne baare me meta baat mat karo — "maine pehle poocha", "yeh maine nahi suna", "yeh detail nahi suni", "unclear hai", "thoda unclear", "maaf kijiye" jaisi cheezein BANNED. Bas aage badho.
3. User ka jawab unclear/aadha lage to sirf chhota sa poocho: "ji, zara dobara boliye?" — bas. Lamba explanation kabhi nahi.
4. Ek baar me EK hi sawaal. Jo user ne bola usko 2-3 shabd me acknowledge karke turant agla chhota sawaal. Sawaal reply ke END me.
5. Discovery questions UPAR diye order me, ek-ek. Jo user PEHLE bata chuka (history padho) woh sawaal dobara mat poocho — agle pe badho.
6. "Busy hoon" → ek line + do callback time options (jaise "shaam paanch ya kal subah gyarah?").
7. "Interest nahi" → ek chhoti value-line, shukriya, call khatam. Manana/pushy BANNED.
8. Numbers/prices SIRF ALLOWED list ya neeche FACTS se. Apne se koi figure/discount/promise kabhi nahi.
9. User ki bhasha mirror karo. "AI/bot ho?" poochhe to sach: haan AI assistant hoon — phir ek line value.
10. Output me SIRF bola jaane wala text — koi "Swara:" prefix, emoji, markdown, bullet nahi.
11. Hamesha customer ko izzat se 'aap' aur 'sir/madam' bolkar address karo. KABHI 'tum', 'tu', 'yaar', 'bhai' ya informal slang/tone ka use mat karo. Swara ki tone hamesha respectful, polite, aur highly professional honi chahiye.

GOOD vs BAD (hamesha GOOD jaisa — chhota, human, ek sawaal):

User: Haan leads aati hain par conversion bahut kam hai.
BAD: Yeh detail maine abhi tak nahi suni thi, lekin aapne conversion ki baat ki jo thodi unclear hai, toh maaf kijiye main phir se poochti hoon...
GOOD: Samajh gayi, conversion gap. {first_q}

User: वटाने (aadha/unclear)
BAD: Yeh thoda unclear hai, aapne वटाने kaha jo main samajh nahi payi, maaf kijiye.
GOOD: Ji, zara dobara boliye?

User: Abhi busy hoon.
GOOD: Bilkul, shaam paanch ya kal subah gyarah — kab theek rahega?

User: Nahi, interest nahi hai.
GOOD: Koi baat nahi — "{hook_short}" se hamare clients ko fayda hua hai. Shukriya, din shubh!"""

    # ------------------------------------------------------------------ #
    # Permission-based opener (Gong: ~11% vs 2.3% generic) — 2 sentences,
    # ends with a yes/no question. Used by vobiz_stream._opening_line().
    # ------------------------------------------------------------------ #
    def opening_line(self) -> str:
        hook = _short_hook(self.pitch_hook)
        if hook:
            return (
                f"Namaste, main Swara bol rahi hoon {self.client_name} ki taraf se. "
                f"Aapke kaam ki ek choti si baat hai — {hook} — kya main tees second me bata doon?"
            )
        return (
            f"Namaste, main Swara bol rahi hoon {self.client_name} ki taraf se. "
            "Kya main do minute le sakti hoon?"
        )

    # ------------------------------------------------------------------ #
    # Reply — system prompt + last ~8 turns → ONE short spoken line.
    # ------------------------------------------------------------------ #
    async def reply(self, history: list[dict[str, str]], user_text: str) -> str:
        """Returns stripped reply text, or "" on ANY failure (caller falls back).

        Pipeline: KB-grounding (niche + client facts) -> free_ai.chat (Cerebras ->
        Groq -> OpenRouter; PRIMARY — free, fast, quota-proof; instant no-op jab
        koi free key set na ho) -> Gemini-direct (multi-key rotation; fallback).
        Repeated-answer guard: bot pichhli line dohraye to ek nudged retry."""
        try:
            ut = (user_text or "").strip()
            facts = await self._kb_facts(ut)
            # Agent memory (cross-session lead recall) — flag-gated, off-loop+deadline
            # (recall khud bounded). OFF (AGENT_MEMORY unset) => instant []. Never blocks.
            try:
                if self.memory_subject:
                    from app.voice_agent import agent_memory

                    if agent_memory.is_enabled():
                        # OUTER hot-path deadline (embed+search sub-timeouts sum ~3.5s;
                        # _kb_facts/_generate jaisa ek hard cap rakho — dead-air na ho).
                        _mem = await asyncio.wait_for(
                            agent_memory.recall(self.memory_subject, ut, scope="lead"), timeout=2.0
                        )
                        if _mem:
                            facts = list(facts or []) + _mem
                        # write-hook: durable facts background me store (fire-and-forget,
                        # non-blocking). Sirf substantive user turns pe (chhote ack skip).
                        if len(ut) >= 15:
                            _hist = list(history or []) + [{"role": "user", "content": ut}]
                            _t = asyncio.create_task(
                                agent_memory.remember(self.memory_subject, _hist, scope="lead")
                            )
                            _t.add_done_callback(lambda t: t.cancelled() or t.exception())
            except Exception:
                pass
            prompt = self._build_prompt(history, ut, facts)

            # HARD LATENCY CAP — _generate (free_llm + gemini fallback) ko ek overall
            # deadline do. Free providers exhausted/slow ho (groq TPD, gemini quota,
            # openrouter 404) to cascade 10-14s tak chala jaata tha = voice me dead-air
            # ("reply nahi deta"). Timeout pe instant script_fallback (niche discovery-Q).
            try:
                text, prov = await asyncio.wait_for(self._generate(prompt), timeout=_REPLY_TIMEOUT_S)
            except Exception:
                text, prov = "", ""

            # REPEAT GUARD — nudge-retry (2nd LLM call) HATA diya: wo per-turn latency
            # ~6s tak badha deta tha ("reply nahi deta" feel = dead-air). Repeat/empty/
            # re-greet ab seedha script_fallback se handle (instant + niche discovery-Q).
            prev = self._prev_assistant(history)
            text = self._fill(self._clean(text))  # brevity cap + placeholder fill ([Company] leak guard)
            # RE-GREETING GUARD — LLM cold/first-turn pe niche opening PARROT kar deta
            # (user ke sawaal ka jawab nahi, sirf dobara greet → "reply nahi deta" feel).
            # Non-first turn pe greeting-like reply = chhodo, script ka asli
            # discovery-question do taaki conversation aage badhe.
            _spoken = sum(1 for m in (history or []) if (m.get("role") or "") == "assistant")
            _regreet = bool(text and _spoken >= 1 and self._looks_like_greeting(text))
            # SCRIPT FALLBACK: LLM throttled/slow/empty/re-greet -> niche-script ka
            # agla PROFESSIONAL sawaal (instant, niche-specific, kabhi repeat nahi).
            if not text or _regreet or (prev and self._too_similar(text, prev)):
                sc = self._script_fallback(history)
                if sc:
                    return sc
            if text:
                logger.debug(f"[telecaller-brain] reply via {prov}")
            return text or self._safe_fallback(history)
        except Exception as e:
            logger.warning(f"[telecaller-brain] reply failed: {e}")
            return self._script_fallback(history) or self._safe_fallback(history)

    # Agent KABHI chup na rahe — LLM slow/empty + script-fallback bhi khali ho to
    # ek safe Hinglish clarify/ack line do (silence = worst UX; test me "NO REPLY" bug).
    _SAFE_LINES = (
        "Ji, main sun rahi hoon — zara dobara boliye?",
        "Achha sir, thoda detail me bataaiye?",
        "Samajh gayi sir — ek minute, aap boliye?",
    )

    def _safe_fallback(self, history: list[dict[str, str]]) -> str:
        try:
            n = sum(1 for m in (history or []) if (m.get("role") or "") == "assistant")
            return self._SAFE_LINES[n % len(self._SAFE_LINES)]
        except Exception:
            return "Ji, boliye?"

    @staticmethod
    def _looks_like_greeting(text: str) -> bool:
        """Reply niche-opening jaisa hai? (Namaste + greeting-phrase). Non-first turn
        pe ye re-greeting = bug; script discovery-question se replace karte."""
        t = (text or "").lower()
        if "namaste" not in t and "hello" not in t and "main swara" not in t:
            return False
        markers = ("bol rahi hoon", "bol raha hoon", "30 second", "tees second",
                   "baat kar sakti", "baat kar sakta", "do minute", "ek minute de",
                   "se baat kar rah", "se swara", "minute baat")
        return any(m in t for m in markers)

    def _fill(self, text: str) -> str:
        """Template placeholders ([Company]/[Name]/[Project]) ko real values se
        replace — LLM kabhi script opening parrot kare to "[Company]" raw na bole
        (test: solar reply me "[Company]" leak hua tha). Never-raise."""
        try:
            t = text or ""
            if "[" not in t:
                return t
            return (
                t.replace("[Company]", self.client_name or "hamari company")
                .replace("[Name]", "Swara")
                .replace("[Project]", "hamare project")
                .replace("[City]", "aapke area")
            )
        except Exception:
            return text or ""

    def _script_fallback(self, history: list[dict[str, str]]) -> str:
        """Deterministic professional line from the niche script (no LLM).
        Rotates through discovery questions by how many bot turns happened,
        then a value line, then the close — so it advances + never repeats."""
        try:
            from app.voice_agent.niche_scripts import get_script

            s = get_script(self.niche) or {}
        except Exception:
            return ""
        disc = [d for d in (s.get("discovery") or []) if d]
        vals = [v for v in (s.get("value_lines") or []) if v]
        closing = (s.get("closing") or "").strip()
        # how many times bot already spoke = our position in the flow
        spoken = sum(1 for m in (history or []) if m.get("role") == "assistant")
        seq = disc + vals + ([closing] if closing else [])
        if not seq:
            return ""
        line = seq[spoken % len(seq)] if spoken < len(seq) else closing or seq[-1]
        return self._clean(line)

    async def _generate(self, prompt: str) -> tuple:
        """(reply_text, provider). free_ai.chat (Cerebras->Groq->OpenRouter) pehle
        — free keys absent ho to instant ""; phir Gemini-direct (multi-key)."""
        text = await self._free_llm(prompt)
        if text:
            return text, "free_ai"
        text = await self._gemini_reply(prompt)
        return (text, "gemini") if text else ("", "")

    @staticmethod
    def _prev_assistant(history: list[dict[str, str]] | None) -> str:
        """Last assistant turn ka text (repeated-answer guard ke liye)."""
        for m in reversed(history or []):
            if m.get("role") == "assistant":
                return str(m.get("content") or "").strip()
        return ""

    @staticmethod
    def _too_similar(a: str, b: str) -> bool:
        """Repeated-line guard: normalized equality ya high token-overlap (>=0.8
        Jaccard). Hinglish ke liye Devanagari range bhi shamil."""
        na = re.sub(r"[^a-z0-9ऀ-ॿ ]", "", (a or "").lower()).strip()
        nb = re.sub(r"[^a-z0-9ऀ-ॿ ]", "", (b or "").lower()).strip()
        if not na or not nb:
            return False
        if na == nb:
            return True
        ta, tb = set(na.split()), set(nb.split())
        if not ta or not tb:
            return False
        return (len(ta & tb) / len(ta | tb)) >= 0.8

    # ------------------------------------------------------------------ #
    # Prompt assembly (system + KB facts + recent turns)
    # ------------------------------------------------------------------ #
    def _build_prompt(
        self, history: list[dict[str, str]], user_text: str, facts: list[str] | None = None
    ) -> str:
        turns = list(history or [])[-_MAX_HISTORY_TURNS:]
        lines: list[str] = [self.system_prompt]
        if facts:
            # KB facts as ONE short line (phone hot path — no paragraphs). Use
            # only if relevant; never invent numbers/claims beyond these.
            joined = " | ".join(f.strip() for f in facts if f and f.strip())
            if joined:
                lines.append(f"FACTS (relevant ho to hi use karo): {joined[:220]}")
        lines += ["", "CALL ABHI TAK:"]
        for m in turns:
            role = "User" if (m.get("role") == "user") else "Swara"
            content = str(m.get("content") or "").strip()
            if content:
                lines.append(f"{role}: {content}")
        # history me aakhri user msg already ho sakta hai (vobiz_stream appends
        # before _think) — duplicate mat karo.
        ut = (user_text or "").strip()
        if ut and not (
            turns
            and turns[-1].get("role") == "user"
            and str(turns[-1].get("content", "")).strip() == ut
        ):
            lines.append(f"User: {ut}")
        lines.append("Swara:")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # KB-grounding — top-2 niche + client facts for this turn (executor)
    # ------------------------------------------------------------------ #
    async def _kb_facts(self, user_text: str) -> list[str]:
        """Top-2 grounding facts from the niche + client KB for this user turn.
        Runs in an executor with a short timeout so a slow/empty/cold KB never
        stalls the spoken reply. Returns [] on anything unusual."""
        ut = (user_text or "").strip()
        if len(ut) < 3:
            return []
        kb = _get_kb()
        if kb is None:
            return []

        namespaces = [self.niche]
        if self.client_id:
            namespaces.append(f"client:{self.client_id}")

        def _query() -> list[dict[str, Any]]:
            hits: list[dict[str, Any]] = []
            for ns in namespaces:
                try:
                    hits.extend(kb.retrieve(ut, k=_KB_TOP_K, namespace=ns) or [])
                except Exception:
                    pass
            return hits

        try:
            loop = asyncio.get_event_loop()
            hits = await asyncio.wait_for(loop.run_in_executor(None, _query), timeout=_KB_TIMEOUT_S)
        except Exception:
            return []

        # gate weak/empty, dedupe, keep top-2 by score
        hits = [
            h
            for h in (hits or [])
            if (h.get("score") or 0.0) >= _KB_MIN_SCORE and str(h.get("text") or "").strip()
        ]
        hits.sort(key=lambda h: h.get("score", 0.0), reverse=True)
        facts: list[str] = []
        seen = set()
        for h in hits:
            t = str(h["text"]).strip()
            sig = t.lower()[:80]
            if sig in seen:
                continue
            seen.add(sig)
            facts.append(t)
            if len(facts) >= _KB_TOP_K:
                break
        return facts

    # ------------------------------------------------------------------ #
    # LLM backends — Gemini (multi-key rotation) + Groq (free fallback)
    # ------------------------------------------------------------------ #
    async def _gemini_reply(self, prompt: str) -> str:
        """Gemini reply with multi-key rotation. On a quota/429 error rotate to
        the next key and retry ONCE. "" on timeout/other failure / no Gemini key
        (free_ai chain already handled it)."""
        if self._genai is None:
            return ""
        for attempt in range(2):
            key = self._active_key() or (settings.gemini_api_key or "").strip()
            try:
                if key:
                    self._genai.configure(api_key=key)
                model = self._genai.GenerativeModel(self.model)
                # Hard latency cap: phone par 6s+ ka silence = dead call.
                response = await asyncio.wait_for(
                    model.generate_content_async(prompt, generation_config=dict(_GEN_CONFIG)),
                    timeout=_REPLY_TIMEOUT_S,
                )
                return self._clean((getattr(response, "text", "") or "").strip())
            except Exception as e:
                if attempt == 0 and self._is_quota_error(e) and self._key_count() > 1:
                    self._advance_key(key)
                    logger.warning("[telecaller-brain] Gemini quota — rotated key, retrying")
                    continue
                logger.warning(f"[telecaller-brain] Gemini reply failed: {e}")
                return ""
        return ""

    async def _free_llm(self, prompt: str) -> str:
        """Free-AI fallback brain (Cerebras → Groq → OpenRouter) via the shared
        free_ai.chat chain. The full telecaller prompt is sent as a single user
        message so the persona/rules carry over. "" when no provider / failure."""
        try:
            from app.voice_agent import free_ai
        except Exception:
            return ""
        try:
            text, provider = await free_ai.chat(
                system="",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=int(_GEN_CONFIG["max_output_tokens"]),
                temperature=float(_GEN_CONFIG["temperature"]),
            )
            if text:
                logger.info(
                    f"[telecaller-brain] free-AI fallback via {provider} (Gemini unavailable)"
                )
            return self._clean(text)
        except Exception as e:
            logger.warning(f"[telecaller-brain] free-AI fallback failed: {e}")
            return ""

    @staticmethod
    def _clean(text: str) -> str:
        """TTS-safe + HARD BREVITY: strip role prefixes/markdown, collapse
        whitespace, AND cap to ~2 sentences / 28 words (phone par lambi reply =
        bura UX; QA-tester ne 36-word replies pakdi thi). Last reliable safety
        net even if the model ignores the prompt's length rule."""
        t = (text or "").strip()
        t = re.sub(r"^(swara|agent|assistant)\s*:\s*", "", t, flags=re.IGNORECASE)
        t = t.replace("*", "").replace("`", "").replace("#", "")
        t = re.sub(r"\s+", " ", t).strip()
        if not t:
            return t
        # 1-2 sentences max (Hindi danda + . ? !)
        parts = re.split(r"(?<=[।.?!])\s+", t)
        if len(parts) > 2:
            t = " ".join(parts[:2]).strip()
        # hard word cap (~28) — trim at a clause boundary if possible
        words = t.split()
        if len(words) > 28:
            t = " ".join(words[:28]).rstrip(" ,;—-")
            if not re.search(r"[।.?!]$", t):
                t += "?"
        return t


__all__ = ["TelecallerBrain"]
