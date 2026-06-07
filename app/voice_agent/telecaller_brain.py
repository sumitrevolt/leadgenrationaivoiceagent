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
from typing import Any, Dict, List, Optional

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Professional telecaller script dataset (pure-data, import-safe). Guarded so a
# missing/broken module can never stop the brain from initializing — get_script
# then degrades to {} and the prompt falls back to niche-data questions.
try:
    from app.voice_agent.niche_scripts import get_script, NICHE_SCRIPTS
except Exception:  # pragma: no cover - pure-data module, but never break the brain
    NICHE_SCRIPTS: Dict[str, dict] = {}

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

_MAX_HISTORY_TURNS = 8          # last ~8 turns to keep prompt (and latency) small
_GEN_CONFIG = {"temperature": 0.5, "max_output_tokens": 60}  # brevity (phone) — 60 so closes don't truncate
_REPLY_TIMEOUT_S = 6.0          # Gemini se itne me jawab nahi => "" (fallback chain)

# KB-grounding (Qdrant niche + client KB) — phone hot path, so keep it tight:
# top-2 facts, short timeout, low score gate (works for both e5-cosine and
# keyword TF-IDF backends; LLM ko bola jata hai ki sirf relevant ho to use kare).
_KB_TOP_K = 2
_KB_TIMEOUT_S = 1.5
_KB_MIN_SCORE = 0.05


def _short_hook(hook: str, max_len: int = 90) -> str:
    """pitch_hook ka pehla, chhota hissa — opener me poora English hook lamba
    lagta hai. Split on em-dash/hyphen clause, cap length."""
    h = (hook or "").strip()
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

    def __init__(self, niche: str = "general", client_name: str = "Demo Co",
                 client_id: Optional[str] = None) -> None:
        self.niche = (niche or "general").strip() or "general"
        self.client_name = (client_name or "Demo Co").strip() or "Demo Co"
        self.client_id = (str(client_id).strip() or None) if client_id else None

        # Multi-key rotation pool (free-AI resilience): STT + LLM share a Gemini
        # quota PER KEY, so we rotate to the next key on a quota/429 error. The
        # pool reads GEMINI_API_KEYS then GEMINI_API_KEY — so a single key still
        # works exactly as before.
        try:
            from app.voice_agent.gemini_keys import (
                active_key, advance_key, key_count, is_quota_error,
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

    # ------------------------------------------------------------------ #
    # Niche data (pitch_hook + qualification_questions from app.niches)
    # ------------------------------------------------------------------ #
    def _load_niche(self) -> None:
        data: Dict = {}
        try:
            from app.niches import NICHES

            data = NICHES.get(self.niche) or {}
        except Exception as e:  # niches module broken should not kill calls
            logger.warning(f"[telecaller-brain] niches load failed: {e}")
        self.niche_name = data.get("name") or self.niche.replace("_", " ").title()
        self.pitch_hook = (data.get("pitch_hook") or "").strip()
        qs = data.get("qualification_questions") or []
        self.questions: List[str] = [str(q).strip() for q in qs if str(q).strip()] or list(_GENERIC_QUESTIONS)
        # Numbers the agent is ALLOWED to say — only what niche data provides.
        nums = []
        if data.get("avg_ticket_inr"):
            nums.append(f"typical deal/ticket size: {data['avg_ticket_inr']}")
        if data.get("avg_deal_value"):
            nums.append(f"average deal value: {data['avg_deal_value']}")
        self.allowed_numbers = "; ".join(nums)

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
        numbers_line = self.allowed_numbers or "(koi nahi — matlab tum KOI number/price quote nahi kar sakti)"

        # Compact professional-script reference blocks (style guide — copy-paste nahi).
        opening = (s.get("opening") or "").strip()
        closing = (s.get("closing") or "").strip()
        value_lines = [str(v).strip() for v in (s.get("value_lines") or []) if str(v).strip()]
        value_block = "\n".join(f"- {v}" for v in value_lines) or "- (niche ke hisaab se ek crisp value-line)"
        obj_block = "\n".join(
            f'- Customer: "{_OBJ_HINT.get(k, k)}" -> Tum: {v}'
            for k, v in (s.get("objections") or {}).items() if str(v).strip()
        ) or "- (empathize karo, ek chhoti value-line do, phir aage badho)"
        script_block = (
            (f"Opening (permission-based): {opening}\n" if opening else "")
            + f"Discovery questions (ISI ORDER me, ek turn me sirf EK; jo customer PEHLE bata chuka woh SKIP):\n{q_block}\n"
            + f"Value lines (jab pitch karni ho):\n{value_block}"
            + (f"\nClosing (interest dikhe to appointment/visit/callback BOOK karo): {closing}" if closing else "")
        )

        return f"""Tum "Swara" ho — {self.client_name} ki professional Indian female telecaller. Tum ek TOP professional Indian telecaller ho (noob nahi). Confident, warm, crisp. Customer ke har jawab ko sun ke uske hisab se aage badho — ratta-maar nahi. Tum ek LIVE PHONE CALL par ho (text chat nahi); bhasha natural Hinglish (Hindi-English mix), awaaz bilkul insaan jaisi.

CLIENT: {self.client_name} | NICHE: {self.niche_name}
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
            return (f"Namaste, main Swara bol rahi hoon {self.client_name} ki taraf se. "
                    f"Aapke kaam ki ek choti si baat hai — {hook} — kya main tees second me bata doon?")
        return (f"Namaste, main Swara bol rahi hoon {self.client_name} ki taraf se. "
                "Kya main do minute le sakti hoon?")

    # ------------------------------------------------------------------ #
    # Reply — system prompt + last ~8 turns → ONE short spoken line.
    # ------------------------------------------------------------------ #
    async def reply(self, history: List[Dict[str, str]], user_text: str) -> str:
        """Returns stripped reply text, or "" on ANY failure (caller falls back).

        Pipeline: KB-grounding (niche + client facts) -> free_ai.chat (Cerebras ->
        Groq -> OpenRouter; PRIMARY — free, fast, quota-proof; instant no-op jab
        koi free key set na ho) -> Gemini-direct (multi-key rotation; fallback).
        Repeated-answer guard: bot pichhli line dohraye to ek nudged retry."""
        try:
            ut = (user_text or "").strip()
            facts = await self._kb_facts(ut)
            prompt = self._build_prompt(history, ut, facts)

            text, prov = await self._generate(prompt)

            # REPEATED-ANSWER GUARD — same-as-last-line par nudge + ek retry.
            prev = self._prev_assistant(history)
            if text and prev and self._too_similar(text, prev):
                nudged = prompt.rstrip() + (
                    "\n\n(NOTE: apni pichhli line bilkul mat dohrao — baat aage "
                    "badhao, agla qualification sawaal poochho ya nayi value-line do.)\nSwara:"
                )
                t2, p2 = await self._generate(nudged)
                if t2 and not self._too_similar(t2, prev):
                    text, prov = t2, p2

            text = self._clean(text)   # HARD brevity cap on the final reply
            if text:
                logger.debug(f"[telecaller-brain] reply via {prov}")
            return text or ""
        except Exception as e:
            logger.warning(f"[telecaller-brain] reply failed: {e}")
            return ""

    async def _generate(self, prompt: str) -> tuple:
        """(reply_text, provider). free_ai.chat (Cerebras->Groq->OpenRouter) pehle
        — free keys absent ho to instant ""; phir Gemini-direct (multi-key)."""
        text = await self._free_llm(prompt)
        if text:
            return text, "free_ai"
        text = await self._gemini_reply(prompt)
        return (text, "gemini") if text else ("", "")

    @staticmethod
    def _prev_assistant(history: Optional[List[Dict[str, str]]]) -> str:
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
    def _build_prompt(self, history: List[Dict[str, str]], user_text: str,
                      facts: Optional[List[str]] = None) -> str:
        turns = list(history or [])[-_MAX_HISTORY_TURNS:]
        lines: List[str] = [self.system_prompt]
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
        if ut and not (turns and turns[-1].get("role") == "user"
                       and str(turns[-1].get("content", "")).strip() == ut):
            lines.append(f"User: {ut}")
        lines.append("Swara:")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # KB-grounding — top-2 niche + client facts for this turn (executor)
    # ------------------------------------------------------------------ #
    async def _kb_facts(self, user_text: str) -> List[str]:
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

        def _query() -> List[Dict[str, Any]]:
            hits: List[Dict[str, Any]] = []
            for ns in namespaces:
                try:
                    hits.extend(kb.retrieve(ut, k=_KB_TOP_K, namespace=ns) or [])
                except Exception:
                    pass
            return hits

        try:
            loop = asyncio.get_event_loop()
            hits = await asyncio.wait_for(
                loop.run_in_executor(None, _query), timeout=_KB_TIMEOUT_S
            )
        except Exception:
            return []

        # gate weak/empty, dedupe, keep top-2 by score
        hits = [
            h for h in (hits or [])
            if (h.get("score") or 0.0) >= _KB_MIN_SCORE and str(h.get("text") or "").strip()
        ]
        hits.sort(key=lambda h: h.get("score", 0.0), reverse=True)
        facts: List[str] = []
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
                    model.generate_content_async(
                        prompt, generation_config=dict(_GEN_CONFIG)
                    ),
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
                logger.info(f"[telecaller-brain] free-AI fallback via {provider} (Gemini unavailable)")
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
