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
import os
import re
from typing import Any

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Devanagari→roman normalizer for the romanized deterministic gates (council fix:
# Whisper(hi) emits Devanagari; normalize ONCE so gates fire instead of per-gate
# patching). Import-safe: degrades to identity if the module is missing.
try:
    from app.voice_agent.hinglish_normalize import to_roman
except Exception:  # pragma: no cover

    def to_roman(_t: str) -> str:  # type: ignore[misc]
        return _t or ""

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

# When discovery + niche value/closing lines are all covered, the conversation must
# still ADVANCE — warna agent ko "aage kya karna nahi pata" (dead-air / wahi line
# repeat) ho jaata hai 2-3 turns ke baad. Ye niche-agnostic next-step closers ek
# concrete action pe le jaate hain (callback/follow-up) bina koi invented
# number/price ke. _already_asked se rotate karte hain — kabhi robot-repeat nahi.
_UNIVERSAL_CLOSE = [
    "Toh sir, agla step rakhte hain — ek short callback aaj ya kal, kab theek rahega?",
    "Main aapko details bhej ke ek quick follow-up fix kar deti hoon — subah ya shaam?",
    "Aapki baat clear hai sir — ek next-step call rakhte hain, aaj ya kal convenient?",
]

# ---------------------------------------------------------------------------
# Prompt-injection guard for real-time caller utterances
# ---------------------------------------------------------------------------
# Duplicated (not imported) from agent_memory._INJECTION_MARKERS so this module
# stays import-safe and free from circular-dep risk.  Keep in sync manually if
# agent_memory list grows.
_INJECTION_MARKERS = (
    "ignore previous",
    "ignore all",
    "disregard previous",
    "forget previous",
    "system prompt",
    "your instructions",
    "reveal your",
    "disclose all",
    "pretend to be",
    "act as",
    "you are now",
    "developer mode",
    "jailbreak",
    "override your",
    "bypass your",
    "new instructions",
    "tum ab",
    "purane instructions bhul",
)

_MAX_UTTERANCE_CHARS = 500  # hard cap — prevents context-stuffing via long payloads


def _sanitize_utterance(ut: str) -> str:
    """Strip prompt-injection markers from a caller utterance before it enters
    the LLM prompt.  Three layers:
      1. Truncate to _MAX_UTTERANCE_CHARS (prevents context-stuffing).
      2. Replace each injection marker (case-insensitive) with [...]
         so the surrounding words remain for fluency but the directive is gone.
      3. Return the cleaned string (never raises — returns '' on any edge-case).
    """
    if not ut:
        return ""
    ut = ut[:_MAX_UTTERANCE_CHARS]
    low = ut.lower()
    for marker in _INJECTION_MARKERS:
        if marker in low:
            # Case-insensitive replacement preserving surrounding text
            pattern = re.compile(re.escape(marker), re.IGNORECASE)
            ut = pattern.sub("[...]", ut)
            low = ut.lower()  # re-check on updated string
    return ut


# ---------------------------------------------------------------------------
_MAX_HISTORY_TURNS = 8  # last ~8 turns to keep prompt (and latency) small
_GEN_CONFIG = {
    "temperature": 0.45,
    "max_output_tokens": 56,
}  # brevity (phone) — room for ONE complete answer + question (was 45 = chopped
# mid-sentence "noob" feel); _clean still hard-caps to ~20 words / 2 short vakya
# (talk-listen judge: bot ko ~50-60% se kam bolna chahiye — chhota = tez TTS bhi).
_REPLY_TIMEOUT_S = 8.0  # free LLM chain (Mistral/Groq) — 4.5s = zyada fallback/wrong jawab

# LLM kabhi-kabhi meta/noob phrases bol deta hai — _clean inhe reject karta hai
# taaki script_fallback (professional niche line) turant aaye.
_META_BANNED = (
    "maine pehle",
    "pehle hi poocha",
    "detail nahi suni",
    "samajh nahi payi",
    "thoda unclear",
    "yeh unclear",
    "maaf kijiye",
    "maaf kij",
    "phir se pooch",
    "dobara pooch",
    "main samajh nahi",
    "aapne kaha jo",
    "yeh detail",
    "great choice",
    "bahut sahi decision",
    "wonderful question",
)

# KB-grounding (Qdrant niche + client KB) — phone hot path, so keep it tight:
# top-2 facts, short timeout, score gate. D-12: default raised 0.05 -> 0.35 to cut
# noisy/irrelevant chunks (PRIMARY backend = fastembed cosine). Env-tunable
# (KB_MIN_SCORE) as a safety valve: the keyword/TF-IDF fallback backend scores on a
# different scale, so if grounding starves there, dial it down without a redeploy.
# Worst case = facts=[] -> graceful niche-script fallback (no crash).
_KB_TOP_K = 2
_KB_TIMEOUT_S = 1.5
try:
    _KB_MIN_SCORE = float(os.environ.get("KB_MIN_SCORE", "0.35") or "0.35")
except Exception:
    _KB_MIN_SCORE = 0.35


# D-9 (source-line) + D-10 (talk-listen / objection 3-beat / WhatsApp-gate /
# Hinglish-mirror). Appended to the system prompt (gated CONVO_DISCIPLINE, default
# ON). Kept TIGHT — these are the genuine gaps NOT already in the 17 hard rules.
_CONVO_DISCIPLINE = (
    "\n\nEXTRA DISCIPLINE:\n"
    "A. SUNO ZYADA, BOLO KAM: har turn = ek chhota jawab + ek sawaal, phir CHUP. "
    "Customer se zyada NA bolo (listen >= talk).\n"
    "B. SOURCE: shuru me ek baar jaldi bata do number kahan se mila "
    "(website / inquiry / Google) — cold na lage.\n"
    "C. OBJECTION 3-STEP: (1) pehle agree/empathy (2) ek sawaal se explore "
    "(3) result/number se reframe. Incumbent ya dusri company ko KABHI bura mat "
    "bolo — pucho 'unhe 10 me kitne number doge?', phir us gap pe baat karo.\n"
    "D. WHATSAPP-GATE: 'WhatsApp pe bhej do' aaye to pehle EK qualifying sawaal "
    "pucho (kya chahiye / kab / budget), phir bhejne ka kaho — blindly mat bhejo.\n"
    "E. HINGLISH MIRROR: caller ka exact Hindi-English mix aur formality copy karo; "
    "demo/budget/slot/plan jaise tech-shabd English me; word-by-word literal Hindi "
    "translation (sahayata/uplabdh/pradan jaisa) BANNED — natural bolchaal."
)


def _latest_trainer_hint() -> str:
    """Latest Meera trainer suggestions → one-line briefing for system prompt.
    Reads last entry from data/trainer_suggestions.jsonl. Never raises."""
    try:
        import json as _json

        path = os.path.join("data", "trainer_suggestions.jsonl")
        if not os.path.isfile(path):
            return ""
        last_line = ""
        with open(path, encoding="utf-8") as _f:
            for line in _f:
                if line.strip():
                    last_line = line.strip()
        if not last_line:
            return ""
        rec = _json.loads(last_line)
        hints = rec.get("suggestions") or []
        if not hints:
            return ""
        return " | ".join(str(h)[:100] for h in hints[:2])
    except Exception:
        return ""


def _convo_discipline_enabled() -> bool:
    """CONVO_DISCIPLINE gate (default ON). Set 0 to disable the D-9/D-10 block."""
    return (os.environ.get("CONVO_DISCIPLINE", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _marketing_plan_price_line(plan_key: str = "starter") -> str:
    """Marketing price line from packages.py, so voice never quotes stale pricing."""
    fallback = "AI Marketing Automation Rs 1,999 mahine se"
    try:
        from app.marketing.packages import get_packages

        key = (plan_key or "starter").strip().lower()
        for pkg in get_packages(include_trial=False):
            if str(pkg.get("key") or "").lower() != key:
                continue
            price = int(pkg.get("price_inr_month") or 0)
            name = str(pkg.get("name") or "Starter").replace("Marketing ", "").strip()
            if price > 0:
                return f"{name} Rs {price:,} mahine se"
    except Exception:
        pass
    return fallback


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
    _en = (
        " your ",
        " the ",
        " before ",
        " with ",
        " every ",
        " you ",
        " not ",
        " of ",
        " who ",
        " and ",
        "qualified",
        "homeowners",
        "borrowers",
        "patients",
        "aspirants",
        "suppliers",
        "inquiries",
        "booked",
        "replaced",
        "calendar",
    )
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
_KB_LOADED_AT = 0.0


def _get_kb():
    """Cached, bootstrapped KnowledgeBase (None agar bootstrap fail).

    D-12: optional TTL refresh — set `KB_REFRESH_SEC` (default 0 = never, current
    behaviour) to re-bootstrap the singleton after that many seconds so KB data
    changes are picked up without a restart. Opt-in keeps the hot path unchanged
    by default (re-bootstrap is synchronous, so use a generous TTL like 3600)."""
    global _KB_SINGLETON, _KB_TRIED, _KB_LOADED_AT
    import time

    try:
        ttl = float(os.environ.get("KB_REFRESH_SEC", "0") or "0")
    except Exception:
        ttl = 0.0
    if _KB_TRIED and ttl > 0 and (time.time() - _KB_LOADED_AT) >= ttl:
        _KB_TRIED = False  # TTL elapsed -> allow one re-bootstrap on this call
    if _KB_TRIED:
        return _KB_SINGLETON
    _KB_TRIED = True
    try:
        from app.voice_agent.kb_loader import bootstrap_default_kb

        _KB_SINGLETON = bootstrap_default_kb()
        _KB_LOADED_AT = time.time()
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
        self,
        niche: str = "general",
        client_name: str = "Demo Co",
        client_id: str | None = None,
        voice_role: str = "telecaller",
    ) -> None:
        self.niche = (niche or "general").strip() or "general"
        self.client_name = (client_name or "Demo Co").strip() or "Demo Co"
        self.client_id = (str(client_id).strip() or None) if client_id else None
        try:
            from app.voice_agent.voice_roles import normalize_role

            self.voice_role = normalize_role(voice_role)
        except Exception:
            self.voice_role = "telecaller"
        # Agent memory (cross-session lead recall) subject — None by DEFAULT.
        # 🔒 SECURITY: client_id ko default subject MAT banao — warna ek client ke
        # SAARE leads ek hi bucket (lead:<client_id>) share karte => Lead A ka PII
        # (budget/identity) Lead B ki call me recall+inject ho sakta. Per-lead memory
        # ke liye call-session set_memory_subject(<lead_id/caller_phone>) bulaaye; jab
        # tak na bulaaye memory INERT (safe). AGENT_MEMORY flag OFF => waise bhi no-op.
        self.memory_subject: str | None = None
        self._interest_confirmed = False
        self._discovery_skip = 0

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
        # Booking/reception roles: append appointment-tool hint when focused on slots.
        try:
            from app.voice_agent.voice_roles import build_role_system_prompt, is_booking_focused

            role_prompt = build_role_system_prompt(
                self.voice_role,
                client_name=self.client_name,
                niche_name=self.niche_name,
                niche_script_context=getattr(self, "niche_script_context", ""),
                discovery_questions=self.questions,
            )
            if role_prompt:
                self.system_prompt = role_prompt
            if is_booking_focused(self.voice_role):
                book_note = (
                    "\n\nAPPOINTMENT TOOLS: jab caller date/time agree kare to "
                    "book_appointment / check_availability use karo (sim mode bhi OK)."
                )
                if book_note not in self.system_prompt:
                    self.system_prompt += book_note
        except Exception:
            pass
        # POLITE-NO hard rule (D-8) — append the India 2-strike de-escalation rule
        # so the LLM honours it on edge cases too (the deterministic gate in reply()
        # is the hard backstop). Gated SOFTNO_DEESCALATE (default ON).
        try:
            from app.voice_agent.intent_softno import SYSTEM_RULE, enabled as _softno_on

            if _softno_on() and SYSTEM_RULE not in self.system_prompt:
                self.system_prompt += SYSTEM_RULE
        except Exception:
            pass
        # D-9 source-line + D-10 talk-listen/objection/whatsapp/Hinglish discipline.
        try:
            if _convo_discipline_enabled() and _CONVO_DISCIPLINE not in self.system_prompt:
                self.system_prompt += _CONVO_DISCIPLINE
        except Exception:
            pass
        # H3: inject Meera's latest trainer suggestions (closed learning loop).
        # Reads data/trainer_suggestions.jsonl (latest entry). Gated
        # TRAINER_FEEDBACK (default ON). Best-effort: never crashes brain init.
        try:
            if os.environ.get("TRAINER_FEEDBACK", "1").strip().lower() not in ("0", "false", "no"):
                hint = _latest_trainer_hint()
                if hint:
                    self.system_prompt += f"\n\nTRAINER NOTE (Meera):\n{hint}"
        except Exception:
            pass
        # Obsidian brain: past call patterns for this niche
        try:
            from app.platform import obsidian_sync as _obs

            _niche_ctx = _obs.brain_context(f"{self.niche or ''} voice call qualification", k=2)
            if _niche_ctx:
                self.system_prompt = self.system_prompt + "\n\n" + _niche_ctx
        except Exception:
            pass
        logger.info(
            f"[telecaller-brain] ready niche={self.niche} role={self.voice_role} "
            f"model={self.model} gemini_keys={self._key_count()} "
            f"free_ai={self._free_ai_providers or 'none'} client_id={self.client_id}"
        )

    def set_memory_subject(self, subject_id: str | None) -> None:
        """Call-session per-lead memory subject set kare (e.g. lead_id / phone).
        AGENT_MEMORY flag OFF ho to iska koi asar nahi (recall/remember no-op)."""
        if subject_id:
            self.memory_subject = str(subject_id).strip() or self.memory_subject

    def confirm_interest(self) -> None:
        """Platform pitch: customer ne interest confirm kar diya — discovery-only mode."""
        if self._interest_confirmed:
            return
        self._interest_confirmed = True
        # yes_praise already asks discovery[0] — skip duplicate on next turn.
        self._discovery_skip = 1 if self.niche == "ai_marketing" else 0
        note = (
            "\n\nPLATFORM NOTE: Customer ne interest confirm kar diya hai — "
            "ab sirf discovery questions aur closing. Dobara pitch ya interest mat poocho."
        )
        if note not in self.system_prompt:
            self.system_prompt += note

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

        return f"""Tum "Swara" ho — {self.client_name} ki senior, professional Indian female telecaller (5+ saal experience). Tum ek experienced business consultant ki tarah baat karti ho: pehle customer ko dhyaan se suno, uski situation samjho, phir uske hisaab se relevant aur confident baat karo — ratta-maar script nahi, robotic nahi. Har jawab specific, warm aur to-the-point. Tum ek LIVE PHONE CALL par ho (text chat nahi); bhasha natural Hinglish (Hindi-English mix), awaaz bilkul insaan jaisi, tone professional aur bharosemand.

CLIENT: {self.client_name} | NICHE: {self.niche_name}{niche_ctx_block}
VALUE LINE (pitch hook): {hook}

PROFESSIONAL SCRIPT (inhi lines/style me baat karo, copy-paste mat karo, natural raho):
{script_block}

OBJECTION HANDLING (agar customer aise bole to aise jawab do, phir aage badho):
{obj_block}

ALLOWED NUMBERS/PRICES (sirf yehi bol sakti ho): {numbers_line}

HARD RULES (har turn, bina exception):
1. Tum phone par ho. Insaan ki tarah baat karo: CHHOTA, seedha, turant. EK reply = 1-2 chhote vakya, MAX ~22 shabd: pehle customer ke sawaal/baat ka seedha jawab, phir (zaroorat ho to) ek chhota sawaal. Monologue/3+ vakya KABHI nahi.
2. KABHI apne baare me meta baat mat karo — "maine pehle poocha", "yeh maine nahi suna", "yeh detail nahi suni", "unclear hai", "thoda unclear", "maaf kijiye" jaisi cheezein BANNED. Bas aage badho.
3. User ka jawab unclear/aadha lage to sirf chhota sa poocho: "ji, zara dobara boliye?" — bas. Lamba explanation kabhi nahi.
4. Ek baar me EK hi sawaal. User ke 2-3 shabd mirror karke turant agla chhota sawaal. Sawaal reply ke END me.
5. Discovery questions UPAR diye order me, ek-ek. Jo user PEHLE bata chuka (history padho) woh sawaal dobara mat poocho — agle pe badho.
6. "Busy hoon" → ek line + do callback time options (jaise "shaam paanch ya kal subah gyarah?").
7. "Interest nahi" → ek chhoti value-line, shukriya, call khatam. Manana/pushy BANNED.
8. Numbers/prices SIRF ALLOWED list ya neeche FACTS se. Apne se koi figure/discount/promise kabhi nahi.
9. User ki bhasha mirror karo. "AI/bot ho?" poochhe to sach: haan AI assistant hoon — phir ek line value.
10. Output me SIRF bola jaane wala text — koi "Swara:" prefix, emoji, markdown, bullet nahi.
11. Hamesha customer ko izzat se 'aap' aur 'sir/madam' bolkar address karo — tone respectful aur professional. KABHI 'tum', 'tu', 'yaar', 'bhai' ya informal slang mat karo.
12. "Zara dobara boliye" poori call me MAX ek baar — baar-baar mat bolo. User ne kuch bhi partial bola ho to usme se jo samjho use karo, seedha agla sawaal.
13. Generic praise BANNED ("bahut achha sir", "great choice", "wonderful") — seedha relevant discovery ya value pe aao.
14. User ne jawab diya ho to uski 2-4 key words repeat karke acknowledge karo, phir agla sawaal (template/ratta nahi).
15. PEHLE JAWAB, PHIR SAWAAL: customer ne kuch poocha ho to uska seedha, clear jawab ek line me do — apni discovery-checklist chalane ke liye uska sawaal IGNORE mat karo. Jawab ke baad hi agla chhota sawaal.
16. FEATURE NAHI, FAYDA: baat customer ke result/fayde me karo, technical feature me nahi — ho sake to unki situation se jod ke ("aap jaise businesses ko isse...").
17. CONFIDENT raho: "shayad", "lagta hai", "pata nahi", "ho sakta hai" jaise unsure shabd avoid karo. Koi number/fact na pata ho to ek clear next-step do (FREE audit/trial jaisa), guess kabhi nahi.
18. DISCOVERY-DONE → CLOSE: jab 2-3 zaroori sawaal pooch liye ho ya unke jawaab history me aa chuke ho, to NAYE discovery sawaal mat dhoondo aur baat ko circle me mat ghumao — seedha ek concrete next-step pe le aao (FREE trial/audit aaj ya kal set karoon? ya appointment/callback slot) aur warmly wrap karo. Interested lage to slot/trial confirm karke band karo; har turn ka ek clear maqsad ho.

GOOD vs BAD (hamesha GOOD jaisa — chhota, human, ek sawaal):

User: Aap exactly karte kya ho?
BAD: Woh sab badiya hai sir, accha aapko abhi customers kahan se aate hain?
GOOD: {hook_short} — aap jaise businesses ka kaam aasaan ho jaata hai; abhi yeh aap kaise manage karte ho?

User: Haan leads aati hain par conversion bahut kam hai.
BAD: Yeh detail maine abhi tak nahi suni thi, lekin aapne conversion ki baat ki jo thodi unclear hai, toh maaf kijiye main phir se poochti hoon...
GOOD: Conversion gap samajh gayi — {first_q}

User: वटाने (aadha/unclear)
BAD: Yeh thoda unclear hai, aapne वटाने kaha jo main samajh nahi payi, maaf kijiye.
GOOD: Ji, zara dobara boliye?

User: Abhi busy hoon.
GOOD: Bilkul, shaam paanch ya kal subah gyarah — kab theek rahega?

User: Nahi, interest nahi hai.
GOOD: Koi baat nahi — "{hook_short}" se clients ko fayda hua. Shukriya, din shubh!"""

    # ------------------------------------------------------------------ #
    # Permission-based opener (Gong: ~11% vs 2.3% generic) — 2 sentences,
    # ends with a yes/no question. Used by vobiz_stream._opening_line().
    # ------------------------------------------------------------------ #
    def opening_line(self) -> str:
        # Role-specific opener first (receptionist/booking → custom; telecaller → None).
        try:
            from app.voice_agent.voice_roles import build_role_opening

            role_opener = build_role_opening(
                self.voice_role,
                client_name=self.client_name,
                niche_name=self.niche_name,
            )
            if role_opener:
                return role_opener
        except Exception:
            pass
        # PARITY with vobiz_stream._opening_line_raw() — the phone path already
        # opens correctly; the web-call path uses THIS method, so it must follow the
        # SAME chain or every vertical niche opens with the wrong platform pitch
        # (real-estate/solar/insurance call greeting "Instagram Facebook FREE trial"
        # = the original "agent noob baat kar rahi" bug).
        # 1) Platform-pitch niche (ai_marketing) → deterministic 3-part intro seg-0.
        try:
            from app.voice_agent.platform_pitch import is_platform_pitch, opening_segments

            if is_platform_pitch(self.niche):
                segs = opening_segments()
                if segs:
                    return segs[0]
        except Exception:
            pass
        # 2) Professional niche-script opening (researched, niche-specific, permission
        #    based, ends in a yes/no question) — placeholders filled + female-voice align.
        try:
            from app.voice_agent.niche_scripts import get_script

            opening = (get_script(self.niche).get("opening") or "").strip()
            if opening:
                opening = (
                    opening.replace("[Company]", self.client_name)
                    .replace("[Name]", "Swara")
                    .replace("[Project]", "hamare project")
                    .replace("[project]", "hamare project")
                    .replace("raha hoon", "rahi hoon")
                )
                return opening
        except Exception:
            pass
        # 3) NICHES pitch_hook template fallback (no LLM/genai — opener stays instant).
        try:
            hook = _short_hook(self.pitch_hook)
            if hook:
                return (
                    f"Namaste, main Swara bol rahi hoon {self.client_name} ki taraf se. "
                    f"Aapke kaam ki ek choti si baat hai — {hook} — kya main tees second me bata doon?"
                )
        except Exception:
            pass
        from app.voice_agent.universal_pitch import UNIVERSAL_AGENT_INTRO

        return UNIVERSAL_AGENT_INTRO

    def _mirror_ack(self, ut: str) -> str:
        """Short, professional, VARIED acknowledgment — human consultant feel.

        Purana version "Achha — bijli ka bill —" jaise user ke 3 shabd literally
        parrot karta tha (em-dash echo) — yeh ek classic robotic AI-tell hai jise
        market-leading agents avoid karte. Ab seedha ek varied, izzat-bhara
        confirmer; agla sawaal _fast_path_reply jodta hai. Period MAT use karo —
        _clean() pehle sentence pe cut karta, warna sawaal kat jaaye (em-dash
        ek hi sentence rehta)."""
        acks = (
            "Samajh gayi ji —",
            "Bilkul ji —",
            "Theek hai ji —",
            "Ji —",
            "Achha ji —",
            "Haan ji —",
            "Bilkul samajh gayi —",
            "Sahi baat hai ji —",
            "Aapki baat clear hai —",
            "Bilkul sahi —",
        )
        return acks[len(ut) % len(acks)]

    def _user_substantive(self, ut: str) -> bool:
        low = ut.lower().strip()
        if len(low) >= 8:
            return True
        return low in (
            "haan",
            "ji",
            "yes",
            "nahi",
            "khud",
            "agency",
            "staff",
            "google",
            "trial",
            "busy",
            "meeting",
        ) or any(
            w in low
            for w in (
                "post",
                "marketing",
                "agency",
                "google",
                "trial",
                "busy",
                "mehenga",
                "mahnga",
                "staff",
                "khud",
            )
        )

    def _last_bot_line(self, history: list[dict[str, str]]) -> str:
        for m in reversed(history or []):
            if m.get("role") == "assistant":
                return str(m.get("content") or "").strip()
        return ""

    @staticmethod
    def _looks_like_question(ut: str) -> bool:
        """Customer ne sawaal poocha? — pehle jawab, phir discovery checklist."""
        low = re.sub(r"\s+", " ", to_roman(ut or "").lower()).strip()
        if "?" in ut:
            return True
        qwords = (
            r"\bkya\b",
            r"\bkaise\b",
            r"\bkab\b",
            r"\bkahan\b",
            r"\bkyun\b",
            r"\bkyon\b",
            r"\bkitna\b",
            r"\bkitne\b",
            r"\bprice\b",
            r"\bcost\b",
            r"\bfree\b",
            r"\btrial\b",
            r"\bsamjhao\b",
            r"\bsamjha\b",
            r"\bbatao\b",
            r"\bmatlab\b",
            r"\bexplain\b",
            r"\bdetail\b",
        )
        if any(re.search(pat, low) for pat in qwords):
            return True
        # Devanagari question/intent words — Whisper(hi) outputs native script, so the
        # romanized qwords above miss "क्या"/"कितना"/"कैसे"/"चार्ज" and the customer's
        # question got mis-routed into the discovery script instead of being answered
        # (proven in 2026-06-25 web test-calls). Over-detection here is SAFE: it just
        # routes more turns to the LLM, which answers in context = more professional.
        dev_q = (
            "क्या", "कैसे", "कैसा", "कब", "कहाँ", "कहां", "क्यों", "क्यूँ", "कितना",
            "कितने", "कितनी", "कौन", "मतलब", "समझा", "बता", "चार्ज", "कीमत", "दाम",
            "पैसे", "रुपय", "प्लान", "पैकेज", "सर्विस", "service", "monthly", "yearly",
        )
        return any(w in (ut or "") for w in dev_q)

    def _customer_qa_reply(self, ut: str) -> str:
        """Customer ke sawaal ka seedha jawab — LLM se pehle (free, instant)."""
        low = to_roman(ut or "").lower().strip()
        if not low or not self._looks_like_question(ut):
            return ""
        if any(w in low for w in ("ai ho", "bot ho", "robot", "machine", "real ho")):
            return self._clean(
                "Haan sir, main AI assistant Swara hoon — aapke business leads qualify karne ke liye."
            )
        platform = self.niche == "ai_marketing" or self._interest_confirmed
        if platform:
            if any(
                w in low
                for w in (
                    "kitne ka",
                    "kitna paisa",
                    "kitna lag",
                    "price",
                    "pricing",
                    "mahina",
                    "cost",
                    "rate",
                    "rupaye",
                    "rupee",
                    "₹",
                    # Devanagari (Whisper hi script) — price/plan asks
                    "कितना",
                    "कितने",
                    "चार्ज",
                    "कीमत",
                    "दाम",
                    "पैसे",
                    "रुपय",
                    "प्लान",
                    "पैकेज",
                    "महीन",
                    "monthly",
                    "yearly",
                    "साल",
                )
            ):
                return self._clean(
                    f"{_marketing_plan_price_line('starter')} — roz posts, ads, Google boost AI se; "
                    "7 din FREE trial bhi hai."
                )
            if any(
                w in low
                for w in (
                    "kya karte",
                    "kya hai ye",
                    "kya hota",
                    "kaise kaam",
                    "samjhao",
                    "samjha",
                    "matlab kya",
                    "explain",
                    "detail me",
                    # "kya kya service/feature provide karte ho" — most-asked discovery
                    # sawaal tha jo roman me kisi keyword se match NAHI hota tha → throttled
                    # LLM pe gir ke deflect ho jaata ("dobara boliye"/"detail bhej deti
                    # hoon" = noob). Yeh seedhe-jawaab branch me route karo (2026-06-27).
                    "kya kya",
                    "service",
                    "services",
                    "feature",
                    "features",
                    "kya provide",
                    "kya offer",
                    "kya milta",
                    "kya milega",
                    "kya deti",
                    "kya dete",
                    "kya cheez",
                    "kaam kya",
                    "sab kya",
                    # Devanagari (Whisper hi script) — what-do-you-do asks
                    "क्या कर",
                    "क्या क्या",
                    "क्या है",
                    "क्या होता",
                    "कैसे काम",
                    "समझा",
                    "मतलब",
                    "सर्विस",
                    "सेवा",
                    "फीचर",
                    "फ़ीचर",
                )
            ):
                return self._clean(
                    "Simple sir — Instagram Facebook WhatsApp pe posts aur ads AI banati hai, "
                    "Google pe upar aana, inquiry follow-up — sab automatic, aap dhanda pe focus."
                )
            if any(w in low for w in ("free trial", "trial", "demo", "try karna")):
                return self._clean("Haan sir — 7 din FREE trial, bina card. Aaj setup kar doon ya kal?")
            if any(w in low for w in ("google", "gbp", "listing", "profile", "search pe")):
                return self._clean(
                    "Google Business audit + fix suggestions dete hain — search pe upar aane me madad, "
                    "reviews ke reply drafts bhi."
                )
            if any(w in low for w in ("cancel", "band karna", "paise wapas", "refund")):
                return self._clean(
                    "Monthly plan hai — cancel anytime. Pehle 7 din FREE trial se result dekho, pressure nahi."
                )
            if any(w in low for w in ("kitne din", "result kab", "time lagega", "kab tak")):
                return self._clean(
                    "Pehle posts aur audit 24-48 ghante me ready — roz ka content subah ~7 baje portal me."
                )
            if any(w in low for w in ("social", "instagram", "facebook", "whatsapp", "post", "ads")):
                return self._clean(
                    "Roz ke posts aur ads AI banati hai — aapki industry aur city ke hisaab se, "
                    "aap sirf approve ya copy-paste karo."
                )
        # IMPORTANT: pehle yahan HAR question pe value_lines[0] dump hota tha — yahi
        # "confused/noob" ka root tha (real_estate me "loan milega?"/"location
        # kahan?"/"possession kab?" SAB pe ek hi irrelevant line + repeat). Ab koi
        # specific keyword match na ho to "" return — sawaal LLM handle karega
        # (full prompt + niche script context + KB facts + history se contextual,
        # competitor-jaisa fluent jawab). Deterministic shortcut sirf genuinely
        # known cases (AI-identity, price, platform FAQs) ke liye rakha.
        return ""

    def _repeats_recent(
        self, text: str, history: list[dict[str, str]], lookback: int = 4
    ) -> bool:
        """True agar `text` recent assistant line jaisa ho — canned-repeat se bachne
        ke liye. Repeat hone wale shortcut ko "" deke LLM elaborate kara dete hain."""
        if not text:
            return False
        asst = [
            str(m.get("content") or "")
            for m in (history or [])
            if m.get("role") == "assistant"
        ]
        return any(self._too_similar(text, prev) for prev in asst[-lookback:])

    def _fast_path_reply(self, history: list[dict[str, str]], ut: str) -> str:
        """Deterministic pro replies — LLM se pehle (latency + repeat guard)."""
        low = to_roman(ut or "").lower().strip()
        qa = self._customer_qa_reply(ut)
        # Canned FAQ answer sirf tab do jab woh recent line repeat na kare; warna
        # "" -> LLM us follow-up ko context se elaborate kare (repeat-loop fix).
        if qa and not self._repeats_recent(qa, history):
            return qa
        try:
            from app.voice_agent.niche_scripts import get_script

            s = get_script(self.niche) or {}
        except Exception:
            s = {}

        if any(w in low for w in ("trial", "free trial", "demo", "test karna", "try karna")):
            return self._clean(
                "Bilkul sir — 7 din ka FREE trial hai, bina credit card. "
                "Aaj setup kar doon ya kal subah?"
            )
        if any(w in low for w in ("busy", "meeting", "abhi nahi", "time nahi")):
            return self._clean("Samajh gayi sir — shaam paanch baje ya kal subah gyarah, kab theek rahega?")
        if any(w in low for w in ("mehenga", "mahnga", "costly", "zyada paisa", "budget zyada")):
            obj = (s.get("objections") or {}).get("mehenga") or ""
            if obj:
                return self._clean(str(obj))
        if any(w in low for w in ("agency", "pehle se agency")):
            obj = (s.get("objections") or {}).get("pehle_se_hai") or ""
            if obj:
                return self._clean(str(obj))
        if self._interest_confirmed or self.niche == "ai_marketing":
            for key, words in (
                ("soch_ke", ("soch", "baad me", "kal baat")),
                ("abhi_nahi", ("abhi nahi", "not now", "baad me call")),
                ("bharosa", ("bharosa", "trust", "vishwas")),
            ):
                if any(w in low for w in words):
                    obj = (s.get("objections") or {}).get(key) or ""
                    if obj:
                        return self._clean(str(obj))
        if "kaun ho" in low or "aap kaun" in low or "who are you" in low:
            return self._clean(
                "Main Swara hoon LeadGen AI se — chhote business ke liye AI marketing platform, posts aur Google profile automatic."
            )
        if any(w in low for w in ("ai ho", "bot ho", "robot", "machine", "real ho")):
            return self._clean(
                "Haan sir, main AI assistant Swara hoon — aapke business leads qualify karne ke liye."
            )
        if any(w in low for w in ("whatsapp", "send kar", "bhej do", "message kar")):
            return self._clean(
                "Bilkul sir, WhatsApp pe bhej dungi — pehle bataiye aapko leads chahiye ya content?"
            )

        # User ne discovery ka jawab diya → mirror + agla unasked sawaal (sawaal ho to skip).
        # LLM-first nudge (council): auto-advance discovery sirf CHHOTE direct jawab pe;
        # lambe/rich turn LLM ko do (woh acknowledge + naturally weave kare) — robotic
        # script-march ka fix.
        if (
            self._user_substantive(ut)
            and not self._looks_like_question(ut)
            and len(low.split()) <= 7
        ):
            nxt = self._next_discovery_line(history)
            last = self._last_bot_line(history)
            if nxt and "?" in nxt:
                # Agar last bot line already yehi sawaal tha, seedha next do.
                if self._already_asked(nxt, history) or (
                    last and self._too_similar(nxt, last)
                ):
                    disc = [d for d in (s.get("discovery") or self.questions or []) if d]
                    for q in disc:
                        if not self._already_asked(q, history):
                            nxt = self._clean(q)
                            break
                ack = self._mirror_ack(ut)
                combined = f"{ack} {nxt}".strip()
                if "?" not in combined:
                    combined = f"{combined} {nxt}"
                return self._clean(combined)
        return ""

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
            # POLITE-NO 2-strike de-escalation (D-8): caller ka 2nd soft refusal =>
            # push BAND, graceful async-exit. Deterministic backstop (no LLM call),
            # runs BEFORE fast-path/LLM so the trust-rule always wins. Gated
            # SOFTNO_DEESCALATE (default ON); any error = no change.
            try:
                from app.voice_agent import intent_softno

                if intent_softno.should_deescalate(history, ut):
                    logger.debug("[telecaller-brain] polite-no de-escalation (2nd soft refusal)")
                    return intent_softno.deescalation_reply(self.niche, self.client_name)
            except Exception:
                pass
            fast = self._fast_path_reply(history, ut)
            if fast:
                return fast

            # OPENER RESPONSE CACHE (gated VOICE_RESPONSE_CACHE) — first-turn-only.
            # Hit returns ~50ms instead of paying 7-8s LLM round-trip on templated
            # openers ("haan boliye", "namaste", etc.). Mid-conversation = never
            # cached (context-bleed risk). Fail-open at every layer.
            _cache_eligible = self._opener_cache_eligible(history, ut)
            if _cache_eligible:
                _cached = await self._opener_cache_lookup(ut)
                if _cached:
                    logger.debug("[telecaller-brain] opener cache HIT")
                    return _cached

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
                text, prov = await asyncio.wait_for(
                    self._generate(prompt), timeout=_REPLY_TIMEOUT_S
                )
            except Exception:
                text, prov = "", ""

            # REPEAT GUARD — nudge-retry (2nd LLM call) HATA diya: wo per-turn latency
            # ~6s tak badha deta tha ("reply nahi deta" feel = dead-air). Repeat/empty/
            # re-greet ab seedha script_fallback se handle (instant + niche discovery-Q).
            prev = self._prev_assistant(history)
            text = self._fill(
                self._clean(text)
            )  # brevity cap + placeholder fill ([Company] leak guard)
            # RE-GREETING GUARD — LLM cold/first-turn pe niche opening PARROT kar deta
            # (user ke sawaal ka jawab nahi, sirf dobara greet → "reply nahi deta" feel).
            # Non-first turn pe greeting-like reply = chhodo, script ka asli
            # discovery-question do taaki conversation aage badhe.
            _spoken = sum(1 for m in (history or []) if (m.get("role") or "") == "assistant")
            _regreet = bool(text and _spoken >= 1 and self._looks_like_greeting(text))
            # SCRIPT FALLBACK: LLM throttled/slow/empty/re-greet -> niche-script ka
            # agla PROFESSIONAL sawaal (instant, niche-specific, kabhi repeat nahi).
            if not text or _regreet or (prev and self._too_similar(text, prev)):
                # User ne specific sawaal poocha tha par LLM jawab nahi de paaya →
                # script ka random value-line (non-sequitur "noob" feel) ki jagah
                # honest acknowledge + next-step. Sirf jab fast-path/QA ne na pakda.
                if self._looks_like_question(ut) and not self._customer_qa_reply(ut):
                    gq = self._graceful_question_fallback(history)
                    if gq:
                        return gq
                sc = self._script_fallback(history)
                if sc:
                    return sc
            if text:
                logger.debug(f"[telecaller-brain] reply via {prov}")
                # OPENER CACHE STORE — store GENUINE LLM reply for next first-turn
                # caller in this niche (fire-and-forget, never blocks the response).
                if _cache_eligible:
                    _t = asyncio.create_task(self._opener_cache_store(ut, text))
                    _t.add_done_callback(lambda t: t.cancelled() or t.exception())
            return text or self._safe_fallback(history)
        except Exception as e:
            logger.warning(f"[telecaller-brain] reply failed: {e}")
            return self._script_fallback(history) or self._safe_fallback(history)

    async def reply_stream_sentences(self, history: list[dict[str, str]], user_text: str):
        """Yield spoken sentences as LLM streams (USE_LLM_STREAM_TTS path).

        Falls back to one-shot reply() as a single yield on any failure.
        """
        from app.voice_agent.llm_stream_tts import iter_sentences_from_tokens

        try:
            ut = (user_text or "").strip()
            # POLITE-NO 2-strike de-escalation (D-8) — same backstop as reply(),
            # yielded as a single sentence so the stream path also de-escalates.
            try:
                from app.voice_agent import intent_softno

                if intent_softno.should_deescalate(history, ut):
                    yield intent_softno.deescalation_reply(self.niche, self.client_name)
                    return
            except Exception:
                pass
            fast = self._fast_path_reply(history, ut)
            if fast:
                yield fast
                return
            facts = await self._kb_facts(ut)
            prompt = self._build_prompt(history, ut, facts)
            from app.voice_agent import free_ai

            async def _tokens():
                async for t in free_ai.chat_stream(
                    system="",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=int(_GEN_CONFIG["max_output_tokens"]),
                    temperature=float(_GEN_CONFIG["temperature"]),
                    profile="realtime",
                ):
                    yield t

            got = False
            async for sent in iter_sentences_from_tokens(_tokens()):
                cleaned = self._fill(self._clean(sent))
                if cleaned:
                    got = True
                    yield cleaned
            if got:
                return
        except Exception as e:
            logger.debug("[telecaller-brain] reply_stream_sentences skip: %s", e)
        one = await self.reply(history, user_text)
        if one:
            yield one

    async def reply_with_tools(
        self, history: list[dict[str, str]], user_text: str, registry: object
    ) -> tuple[str, dict | None]:
        """VOICE_TOOLS path (gated; the caller checks the flag) — generate ONE
        turn that is EITHER a spoken Hinglish line OR an in-call tool call.

        Returns ``(spoken_text, tool_call)`` where exactly one is meaningful:
          * ``tool_call`` = ``{"name", "args"}`` when the LLM emitted a CALL line
            (parsed by function_calling.parse_tool_call);
          * ``spoken_text`` = the cleaned reply otherwise.

        Fully ISOLATED from reply()/reply_stream_sentences — the default voice
        behaviour is byte-identical when VOICE_TOOLS is off (this method is simply
        never invoked). Never raises: any failure degrades to a normal reply()."""
        try:
            from app.voice_agent.function_calling import parse_tool_call
            from app.voice_agent.voice_tools import tools_instruction

            ut = (user_text or "").strip()
            facts = await self._kb_facts(ut)
            prompt = self._build_prompt(
                history, ut, facts, extra_system=tools_instruction(registry)
            )
            try:
                raw, _prov = await asyncio.wait_for(
                    self._generate(prompt), timeout=_REPLY_TIMEOUT_S
                )
            except Exception:
                raw = ""
            raw = (raw or "").strip()
            if raw:
                call = parse_tool_call(raw)
                if call and call.get("name"):
                    logger.info(f"[telecaller-brain] tool-call: {call.get('name')}")
                    return "", call
            spoken = self._fill(self._clean(raw)) if raw else ""
            if not spoken:
                spoken = self._script_fallback(history) or self._safe_fallback(history)
            return spoken, None
        except Exception as e:
            logger.debug(f"[telecaller-brain] reply_with_tools fallback: {e}")
            try:
                return (await self.reply(history, user_text)), None
            except Exception:
                return "", None

    # Agent KABHI chup na rahe — LLM slow/empty + script-fallback bhi khali ho to
    # ek safe Hinglish clarify/ack line do (silence = worst UX; test me "NO REPLY" bug).
    _SAFE_LINES = (
        "Achha sir, thoda detail me bataaiye?",
        "Samajh gayi sir — aage bataye?",
        "Ji sir, sun rahi hoon — boliye?",
    )
    _CLARIFY_LINE = "Ji sir, ek baar phir short me boliye?"

    def _safe_fallback(self, history: list[dict[str, str]]) -> str:
        try:
            hist = history or []
            clarify_used = any(
                "dobara boliye" in str(m.get("content") or "").lower()
                or "phir short" in str(m.get("content") or "").lower()
                for m in hist
                if m.get("role") == "assistant"
            )
            if not clarify_used and len(hist) >= 2:
                return self._CLARIFY_LINE
            n = sum(1 for m in hist if (m.get("role") or "") == "assistant")
            return self._SAFE_LINES[n % len(self._SAFE_LINES)]
        except Exception:
            return "Ji sir, boliye?"

    # User ne SPECIFIC sawaal poocha par KB/LLM jawab nahi de paaya (e.g. niche KB
    # seed nahi, ya fact available nahi) — aise me script ka random value-line
    # dump karna = non-sequitur ("metro kitni door?" -> "pre-launch discount" =
    # confused/noob). Iski jagah honest acknowledge + concrete next-step do (koi
    # fact invent NAHI, rule-8 safe). Rotate + repeat-skip taaki robotic na lage.
    _GRACEFUL_Q = (
        "Achha sawaal sir — iski poori detail main aapko bhej deti hoon; ek short follow-up aaj ya kal rakh lein?",
        "Ji sir — ye main confirm karke aapko share kar deti hoon; chahein to ek quick callback fix kar dein?",
        "Bilkul sir — exact jaankari nikaal ke bhej deti hoon; tab tak aapka koi aur sawaal ho to boliye?",
    )

    def _graceful_question_fallback(self, history: list[dict[str, str]]) -> str:
        # Sirf EK baar per call — "main detail bhej deti hoon" baar-baar = evasive
        # (ek aur tarah ka noob). Pehle unanswerable-sawaal pe honest ack; uske baad
        # script_fallback call ko aage (discovery/closing) le jaaye.
        used = any(
            ("bhej deti hoon" in str(m.get("content") or "").lower())
            or ("share kar deti hoon" in str(m.get("content") or "").lower())
            for m in (history or [])
            if m.get("role") == "assistant"
        )
        if used:
            return ""
        return self._clean(self._GRACEFUL_Q[0])

    @staticmethod
    def _looks_like_greeting(text: str) -> bool:
        """Reply niche-opening jaisa hai? (Namaste + greeting-phrase). Non-first turn
        pe ye re-greeting = bug; script discovery-question se replace karte."""
        t = (text or "").lower()
        intro = (
            "namaste" in t
            or "hello" in t
            or "main swara" in t
            or "swara bol" in t
            or "ki taraf se" in t
            or "ai assistant" in t
        )
        if not intro:
            return False
        markers = (
            "30 second",
            "tees second",
            "2 minute",
            "do minute",
            "ek minute de",
            "baat kar sakti",
            "baat kar sakta",
            "baat kar lein",
            "time milega",
            "theek hai na",
            "denge?",
            "de sakte",
        )
        if any(m in t for m in markers):
            return True
        return bool(
            re.search(r"\bbol\s+(rahi|raha|rahe)\b", t)
            or "se baat kar rahi" in t
            or "se baat kar raha" in t
            or "aapse" in t
        )

    def _fill(self, text: str) -> str:
        """Template placeholders ([Company]/[Name]/[Project]) ko real values se
        replace — LLM kabhi script opening parrot kare to "[Company]" raw na bole
        (test: solar reply me "[Company]" leak hua tha). Never-raise."""
        try:
            t = text or ""
            if "[" not in t:
                return t
            t = (
                t.replace("[Company]", self.client_name or "hamari company")
                .replace("[Name]", "Swara")
                .replace("[Project]", "hamare project")
                .replace("[City]", "aapke area")
            )
            # ANY leftover [placeholder] the LLM/KB parroted (e.g. the SOURCE rule's
            # "[website/inquiry]" / "[Google/website/inquiry]") must NEVER be spoken
            # raw — TTS bolega "bracket Google slash website..." = noob (live call
            # 2026-06-26). Strip the bracket token, then tidy doubled spaces + the
            # orphan space-before-punct it can leave behind.
            if "[" in t:
                t = re.sub(r"\[[^\]]*\]", "", t)
                t = re.sub(r"\s+([,.?!।])", r"\1", t)
                t = re.sub(r"\s{2,}", " ", t).strip()
            return t
        except Exception:
            return text or ""

    @staticmethod
    def _question_signature(q: str) -> set[str]:
        """Discovery question ka chhota token-set — repeat-detect ke liye."""
        t = re.sub(r"[^a-z0-9ऀ-ॿ ]", " ", (q or "").lower())
        stop = {
            "aap",
            "ap",
            "apne",
            "hai",
            "hain",
            "kya",
            "ka",
            "ke",
            "ki",
            "ko",
            "me",
            "se",
            "ya",
            "aur",
            "abhi",
            "kitna",
            "kitni",
            "kahan",
            "kaise",
            "the",
            "a",
            "an",
        }
        return {w for w in t.split() if len(w) > 2 and w not in stop}

    def _already_asked(self, question: str, history: list[dict[str, str]]) -> bool:
        """Bot ne ye sawaal (ya bahut similar) pehle poocha?"""
        sig = self._question_signature(question)
        if not sig:
            return False
        for m in reversed(history or []):
            if m.get("role") != "assistant":
                continue
            prev = str(m.get("content") or "")
            ps = self._question_signature(prev)
            if not ps:
                continue
            overlap = len(sig & ps) / max(len(sig | ps), 1)
            if overlap >= 0.55 or question.strip().lower() in prev.lower():
                return True
        return False

    def _next_discovery_line(self, history: list[dict[str, str]]) -> str:
        """Pehla unasked discovery → value → close."""
        try:
            from app.voice_agent.niche_scripts import get_script

            s = get_script(self.niche) or {}
        except Exception:
            s = {}
        disc = [d for d in (s.get("discovery") or self.questions or []) if d]
        skip = int(getattr(self, "_discovery_skip", 0) or 0)
        if skip > 0:
            disc = disc[skip:]
        vals = [v for v in (s.get("value_lines") or []) if v]
        closing = (s.get("closing") or "").strip()
        for q in disc:
            if not self._already_asked(q, history):
                return self._clean(q)
        for v in vals:
            if not self._already_asked(v, history):
                return self._clean(v)
        if closing and not self._already_asked(closing, history):
            return self._clean(closing)
        # Discovery + value + niche-closing sab ho chuke → conversation ROKO mat:
        # ek concrete next-step do (warna "aage kya" = dead-air ya wahi line repeat).
        for c in _UNIVERSAL_CLOSE:
            if not self._already_asked(c, history):
                return self._clean(c)
        # Absolute last resort — phir bhi kabhi blank nahi.
        return self._clean(closing) if closing else self._clean(_UNIVERSAL_CLOSE[0])

    def _script_fallback(self, history: list[dict[str, str]]) -> str:
        """Deterministic professional line from the niche script (no LLM).
        Skips discovery questions already asked in history."""
        line = self._next_discovery_line(history)
        if line:
            return line
        try:
            from app.voice_agent.niche_scripts import get_script

            s = get_script(self.niche) or {}
        except Exception:
            return ""
        closing = (s.get("closing") or "").strip()
        return self._clean(closing) if closing else ""

    @staticmethod
    def _voice_gemini_primary() -> bool:
        """VOICE-SCOPED Gemini-primary flag — makes ONLY the telecaller brain prefer
        Gemini (smarter convo) WITHOUT flipping the platform-wide free_ai chain
        (global GEMINI_PRIMARY would route marketing/agents to Gemini too). Set
        VOICE_GEMINI_PRIMARY=1 when a healthy GEMINI_API_KEYS pool backs the voice."""
        if (os.environ.get("VOICE_GEMINI_PRIMARY", "0") or "0").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        ):
            return True
        # Admin "Voice Keys" page can enable it at runtime (no .env / restart).
        try:
            from app.voice_agent.gemini_keys import runtime_voice_primary

            return runtime_voice_primary()
        except Exception:
            return False

    @staticmethod
    def _voice_response_cache_enabled() -> bool:
        """VOICE_RESPONSE_CACHE — wraps the OPENER turn (history_len==0) in
        semantic_cache (L1 exact + L2 semantic via Qdrant + Redis). Hit returns
        ~50ms instead of paying the 7-8s LLM round-trip for templated openers.
        Mid-conversation NEVER cached (context-bleed risk). Default OFF =
        byte-identical; requires SEMANTIC_CACHE=1 too. Diagnosed 2026-06-26:
        SEMANTIC_CACHE=1 was already set in prod but Redis had 0 cache keys
        because the voice brain never called semantic_complete."""
        return (os.environ.get("VOICE_RESPONSE_CACHE", "0") or "0").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

    def _opener_cache_eligible(
        self, history: list[dict[str, str]] | None, ut: str
    ) -> bool:
        """First-USER-turn-only cache eligibility. Conservative gates so we never
        serve a context-dependent line to the wrong call. The bot's auto-greeting
        sits in history as an assistant message BEFORE the first user reply —
        so we count user messages, not total messages (else the cache would
        never fire in practice — 2026-06-26 first-deploy bug)."""
        if not self._voice_response_cache_enabled():
            return False
        if not ut or len(ut) < 5:  # "haan"/"ok" too generic to safely match
            return False
        user_msgs = sum(
            1 for m in (history or []) if (m.get("role") or "") == "user"
        )
        if user_msgs > 0:  # not the first user turn → context-bleed risk
            return False
        try:
            from app.cache.semantic_cache import is_enabled

            return is_enabled()  # SEMANTIC_CACHE flag must also be ON
        except Exception:
            return False

    async def _opener_cache_lookup(self, ut: str) -> str | None:
        """Return cached opener reply (L1 exact then L2 semantic) or None.
        Best-effort, never raises, never blocks longer than the underlying
        timeouts in semantic_cache."""
        try:
            from app.cache.semantic_cache import (
                _default_backend,
                _l1_key,
                _min_sim,
                _normalize,
                _safe_embed,
                _safe_thread,
                _store_timeout,
            )

            be = _default_backend()
            scope = f"voice:opener:{self.niche}"
            norm = _normalize(ut)
            l1key = _l1_key(scope, norm)
            hit = await be.l1_get(l1key)
            if hit:
                return hit
            vec = await _safe_embed(be, norm)
            if vec is not None:
                found = await _safe_thread(
                    be.vsearch, vec, scope, timeout=_store_timeout()
                )
                if found and (found.get("response") or "").strip():
                    if float(found.get("score") or 0.0) >= _min_sim():
                        return found["response"]
        except Exception:
            pass
        return None

    async def _opener_cache_store(self, ut: str, reply_text: str) -> None:
        """Store fresh LLM-generated opener reply (best-effort fire-and-forget)."""
        try:
            import time as _time

            from app.cache.semantic_cache import (
                _default_backend,
                _l1_key,
                _normalize,
                _safe_embed,
                _safe_thread,
                _store_timeout,
                _ttl,
            )

            if not reply_text or not reply_text.strip():
                return
            be = _default_backend()
            scope = f"voice:opener:{self.niche}"
            norm = _normalize(ut)
            l1key = _l1_key(scope, norm)
            await be.l1_set(l1key, reply_text, _ttl())
            vec = await _safe_embed(be, norm)
            if vec is not None:
                await _safe_thread(
                    be.vupsert,
                    vec,
                    scope,
                    norm,
                    reply_text,
                    _time.time(),
                    timeout=_store_timeout(),
                )
        except Exception:
            pass

    @staticmethod
    def _voice_llm_race() -> bool:
        """VOICE_LLM_RACE — fire Gemini + free_ai in PARALLEL, first non-empty wins,
        cancel the loser. Cuts worst-case turn latency from ~16s (sequential 8s+8s)
        to MIN(gemini,free_ai) ≈ 2-5s typical. Diagnosed 2026-06-26 from live-prod
        agent_tester scorecard (7-17s tail + 2x NO-REPLY at 12s). Default OFF =
        byte-identical sequential behaviour."""
        return (os.environ.get("VOICE_LLM_RACE", "0") or "0").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

    async def _generate_raced(self, prompt: str) -> tuple[str, str]:
        """Fire Gemini and free_ai concurrently; first non-empty wins. Loser is
        cancelled. Inherits the outer _REPLY_TIMEOUT_S deadline from reply()'s
        asyncio.wait_for, so this never extends total latency — only shrinks it.
        Never raises; returns ("","") on dual-fail (caller falls to script)."""
        g_task = asyncio.create_task(self._gemini_reply(prompt))
        f_task = asyncio.create_task(self._free_llm(prompt))
        labels = {g_task: "gemini", f_task: "free_ai"}
        pending: set = {g_task, f_task}
        try:
            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for t in done:
                    try:
                        text = (t.result() or "").strip()
                    except Exception:
                        text = ""
                    if text:
                        for p in pending:
                            p.cancel()
                        return text, labels[t]
            return "", ""
        finally:
            for t in (g_task, f_task):
                if not t.done():
                    t.cancel()

    async def _generate(self, prompt: str) -> tuple:
        """(reply_text, provider). VOICE_LLM_RACE=1 → race both backends in parallel
        (first non-empty wins). Else GEMINI_PRIMARY/VOICE_GEMINI_PRIMARY decides
        sequential order; default = free_ai.chat (Mistral->Groq->...) first."""
        from app.config import settings

        if self._voice_llm_race():
            return await self._generate_raced(prompt)

        use_gemini_first = getattr(settings, "gemini_primary", False) or self._voice_gemini_primary()

        if use_gemini_first:
            text = await self._gemini_reply(prompt)
            if text:
                return text, "gemini"
            text = await self._free_llm(prompt)
            return (text, "free_ai") if text else ("", "")
        else:
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

    def _voice_lessons_block(self) -> str:
        """Past live-call mistakes from skill_library (Meera voice_learn)."""
        try:
            from app.platform.skill_library import lessons_snippet

            snip = lessons_snippet(f"voice_{self.niche}", k=3)
            if not snip.strip():
                snip = lessons_snippet("voice_general", k=2)
            if snip.strip():
                return f"PAST CALL LESSONS (in galtiyan mat dobara karo):\n{snip}"
        except Exception:
            pass
        return ""

    # ------------------------------------------------------------------ #
    # Prompt assembly (system + KB facts + recent turns)
    # ------------------------------------------------------------------ #
    def _build_prompt(
        self,
        history: list[dict[str, str]],
        user_text: str,
        facts: list[str] | None = None,
        extra_system: str = "",
    ) -> str:
        turns = list(history or [])[-_MAX_HISTORY_TURNS:]
        lines: list[str] = [self.system_prompt]
        # VOICE_TOOLS path injects the in-call action instruction here (after the
        # system prompt, before history). Default "" = byte-identical prompt.
        if extra_system:
            lines.append(extra_system)
        vl = self._voice_lessons_block()
        if vl:
            lines.append(vl)
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
        # Sanitize first: strip prompt-injection markers + enforce length cap
        # before the utterance enters the LLM context window.
        ut = _sanitize_utterance((user_text or "").strip())
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
                    hits.extend(kb.retrieve(ut, k=_KB_TOP_K, namespace=ns, rerank=False) or [])
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
        # Agentic RAG fallback: plain retrieve ne kuch nahi diya + USE_AGENTIC_RAG=1
        if not facts and os.environ.get("USE_AGENTIC_RAG", "").strip() in ("1", "true", "yes", "on"):
            try:
                from app.agents.agentic_rag import get_agentic_rag

                primary_ns = namespaces[0] if namespaces else "default"
                ar = await asyncio.wait_for(
                    get_agentic_rag().answer(ut, namespace=primary_ns, k=_KB_TOP_K),
                    timeout=8.0,
                )
                if isinstance(ar, dict) and ar.get("grounded") and (ar.get("answer") or "").strip():
                    facts = [(ar["answer"] or "").strip()]
            except Exception:
                pass
        return facts

    # ------------------------------------------------------------------ #
    # LLM backends — Gemini (multi-key rotation) + Groq (free fallback)
    # ------------------------------------------------------------------ #
    async def _gemini_reply(self, prompt: str) -> str:
        """Gemini reply — Vertex AI (Cloud subscription) pehle, then API-key fallback.
        "" on timeout/other failure (free_ai chain handles the rest)."""
        # --- 1) Vertex AI path (Google Cloud subscription, no per-key quota) ---
        try:
            from app.voice_agent.free_ai import _vertex_available, _vertex_bearer_token, _vertex_base_url
            if _vertex_available():
                from openai import AsyncOpenAI  # type: ignore
                token = await _vertex_bearer_token()
                if token:
                    model_name = getattr(settings, "default_llm", None) or self.model or "gemini-2.5-flash"
                    client = AsyncOpenAI(api_key=token, base_url=_vertex_base_url(), timeout=_REPLY_TIMEOUT_S)
                    resp = await asyncio.wait_for(
                        client.chat.completions.create(
                            model=model_name,
                            messages=[{"role": "user", "content": prompt}],
                            max_tokens=int(_GEN_CONFIG.get("max_output_tokens", 150)),
                            temperature=float(_GEN_CONFIG.get("temperature", 0.7)),
                        ),
                        timeout=_REPLY_TIMEOUT_S,
                    )
                    text = (resp.choices[0].message.content or "").strip()
                    if text:
                        logger.info("[telecaller-brain] Gemini Vertex AI reply OK")
                        return self._clean(text)
        except Exception as e:
            logger.warning(f"[telecaller-brain] Gemini Vertex failed: {e}")

        # --- 2) API-key path (google.generativeai, multi-key rotation) ---
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
                profile="realtime",
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
    def _has_meta_junk(text: str) -> bool:
        """True if reply contains banned meta/noob telecaller phrases."""
        low = (text or "").lower()
        return any(b in low for b in _META_BANNED)

    @staticmethod
    def _clean(text: str) -> str:
        """TTS-safe + HARD BREVITY: strip role prefixes/markdown, collapse
        whitespace, cap to 1–2 COMPLETE sentences / ~28 words (phone par lambi reply =
        bura UX). Meta/noob phrases => '' (caller uses script_fallback)."""
        t = (text or "").strip()
        t = re.sub(r"^(swara|agent|assistant)\s*:\s*", "", t, flags=re.IGNORECASE)
        # Small models kabhi poora transcript continue kar dete hain ("...kya?
        # User: ... Swara: ..."). Pehle embedded role-marker pe kaat do — Swara ka
        # sirf PEHLA turn spoken hota hai (warna TTS dono side bol dega = noob).
        t = re.split(
            r"\b(?:user|swara|agent|assistant|customer|client|caller)\s*:",
            t,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip()
        t = t.replace("*", "").replace("`", "").replace("#", "")
        t = re.sub(r"\s+", " ", t).strip()
        # Small free models kabhi-kabhi reasoning/meta leak karte hain ek
        # un-closed parenthetical me ("...karte ho? (Lagta hai ki user?"). Aisa
        # dangling "(...." (bina closing ')') cut kar do — warna TTS junk bolega.
        if "(" in t and ")" not in t:
            t = t[: t.index("(")].strip()
        t = re.sub(r"\s+", " ", t).strip()
        if not t:
            return t
        if TelecallerBrain._has_meta_junk(t):
            return ""
        # 1. Sentence cap: keep up to 2 COMPLETE sentences.
        parts = re.split(r"(?<=[।.?!])\s+", t)
        if len(parts) > 2:
            t = " ".join(parts[:2]).strip()
        # 2. Soft word cap (~28) — if 2 sentences exceed, drop the 2nd partial
        #    and keep only the 1st complete sentence. NEVER mid-thought trim.
        words = t.split()
        if len(words) > 28:
            t = parts[0].strip() if parts else t
        # 3. NEVER append fake punctuation — sentence-boundary split keeps complete
        #    sentences only. If something is still dangling, the caller handles it.
        return t


__all__ = ["TelecallerBrain"]
