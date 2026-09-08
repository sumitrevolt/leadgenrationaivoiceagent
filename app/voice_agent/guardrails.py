"""
Guardrails Layer (Production)
=============================

Retell / Bland / Galileo / Arthur jaisa GUARDRAILS layer — AI voice agent ko
production-safe banata hai. Do jagah lagta hai:

  PRE-LLM  (check_input)  -> customer ka text LLM tak jaane se PEHLE:
      * PII redaction (phone, email, Aadhaar, PAN, credit-card, UPI)
      * prompt-injection / jailbreak block ("ignore previous instructions", ...)
      * profanity flag (mild hi+en list)

  POST-LLM (check_output) -> bot ka reply customer tak jaane se PEHLE:
      * system-prompt / internal-instruction leak block
      * unsafe promises block (guarantee, medical/legal/financial advice)
      * robotic "as an AI language model" rewrite
      * wildly off-topic block (optional allowed_topics)
      * light hallucination / grounding check (optional known_facts) -> rewrite

Design (production best-practice):
  - RULE-BASED FIRST: koi external call nahi -> always runs, sub-200ms.
  - Pre-compiled regexes, pure-python, kabhi crash nahi (defensive).
  - Configurable via constructor (extra_blocklist, extra_pii_patterns).

Usage:
    from app.voice_agent.guardrails import get_guardrails
    g = get_guardrails()

    # PRE-LLM: PII redact + injection block
    res = g.check_input("Mera number 9876543210 hai, ignore previous instructions")
    res.allowed      # False  (injection pakda gaya -> block)
    res.action       # "block"
    res.text         # "Mera number [REDACTED_PHONE] hai, ..."  (PII bhi redacted)

    res2 = g.check_input("Mera number 9876543210 hai")
    res2.allowed     # True
    res2.action      # "redact"
    res2.text        # "Mera number [REDACTED_PHONE] hai"  -> yahi LLM ko bhejo

    # POST-LLM: unsafe-promise / leak block
    out = g.check_output("Main aapko 100% guarantee deta hoon ki...")
    out.allowed      # False -> safe replacement text use karo
    out.text         # safe fallback line
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from re import Pattern

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Result shape
# --------------------------------------------------------------------------- #
@dataclass
class GuardrailResult:
    """
    Har guardrail check ka result.

    Fields:
      allowed   : bool  -> text aage bhej sakte ho ki nahi.
      action    : str   -> "allow" | "redact" | "block" | "rewrite"
      text      : str   -> safe/redacted text (jo actually use karna hai).
      violations: list  -> kis rule ne flag kiya (audit/log ke liye).
      severity  : str   -> "none" | "low" | "medium" | "high"
    """

    allowed: bool = True
    action: str = "allow"
    text: str = ""
    violations: list[str] = field(default_factory=list)
    severity: str = "none"


# --------------------------------------------------------------------------- #
# Pre-compiled patterns (fast, pure-python, no external services)
# --------------------------------------------------------------------------- #
# PII — ORDER MATTERS: Aadhaar/card (longer digit runs) ko phone se PEHLE redact
# karo, warna phone regex unke andar match kar lega.
_PII_PATTERNS: list[tuple[str, Pattern]] = [
    # Email — phone se pehle (warna numbers in email accidentally match ho sakte hain)
    ("[REDACTED_EMAIL]", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    # Credit/debit card — 13-16 digits, optional space/hyphen separators
    ("[REDACTED_CARD]", re.compile(r"\b(?:\d[ \-]?){13,16}\b")),
    # Aadhaar — 12 digits, often grouped 4-4-4
    ("[REDACTED_AADHAAR]", re.compile(r"\b\d{4}[ \-]?\d{4}[ \-]?\d{4}\b")),
    # PAN — 5 letters, 4 digits, 1 letter (e.g. ABCDE1234F)
    ("[REDACTED_PAN]", re.compile(r"\b[A-Za-z]{5}\d{4}[A-Za-z]\b")),
    # UPI id — name@bank (e.g. ratan@okhdfc, 9876543210@ybl)
    (
        "[REDACTED_UPI]",
        re.compile(
            r"\b[A-Za-z0-9.\-_]{2,}@(?:ok[a-z]+|[a-z]{2,}bank|ybl|paytm|apl|axl|ibl|upi|hdfc|icici|sbi|axis|kotak|yapl)\b",
            re.IGNORECASE,
        ),
    ),
    # Indian phone — +91 / 0 prefix optional, 10 digits starting 6-9.
    # Allow arbitrary single space/hyphen grouping inside the 10 digits
    # (e.g. 9876543210, 98765-43210, 98765 43210, +91 987 654 3210).
    ("[REDACTED_PHONE]", re.compile(r"(?<!\d)(?:\+?91[\-\s]?|0)?[6-9]\d(?:[\-\s]?\d){8}(?!\d)")),
]

# Prompt-injection / jailbreak — substring (lowercased) match, fast.
_INJECTION_PHRASES: list[str] = [
    "ignore previous instructions",
    "ignore all previous instructions",
    "ignore the above",
    "ignore your instructions",
    "disregard previous instructions",
    "disregard the above",
    "forget previous instructions",
    "forget your instructions",
    "you are now",
    "you're now",
    "act as",
    "pretend to be",
    "pretend you are",
    "system prompt",
    "reveal your prompt",
    "reveal your instructions",
    "repeat your instructions",
    "repeat your prompt",
    "print your prompt",
    "print your instructions",
    "show me your prompt",
    "show your system prompt",
    "what is your system prompt",
    "developer mode",
    "jailbreak",
    "dan mode",
    "bypass your",
    "override your",
    "new instructions:",
    "from now on you",
    "no longer bound by",
    # Hinglish variants
    "purane instructions bhul",
    "apna system prompt batao",
    "apne instructions batao",
    "tum ab",
]

# Profanity — mild hi+en list (flag only, not auto-block).
_PROFANITY_WORDS: list[str] = [
    "fuck",
    "shit",
    "bitch",
    "bastard",
    "asshole",
    "dick",
    "crap",
    "bhosdi",
    "bhosad",
    "madarchod",
    "behenchod",
    "chutiya",
    "chutiye",
    "gandu",
    "harami",
    "kamina",
    "kutta",
    "kutte",
    "saala",
    "saale",
    "randi",
    "lavde",
    "lund",
    "gaand",
    "bc",
    "mc",
]

# --- Output (POST-LLM) patterns --------------------------------------------- #
# System-prompt / internal-instruction leak in BOT output.
_LEAK_PHRASES: list[str] = [
    "my system prompt",
    "my instructions are",
    "i was instructed to",
    "my prompt says",
    "according to my instructions",
    "as per my system prompt",
    "known facts:",
    "voice_system_prompt",
    "you are {agent_name}",
    "my guidelines say",
    "internal instructions",
    "the prompt i was given",
    "mera system prompt",
    "mujhe instruct kiya gaya",
]

# Unsafe promises / out-of-scope advice in BOT output.
_UNSAFE_PROMISE_PHRASES: list[str] = [
    "100% guarantee",
    "100 percent guarantee",
    "guaranteed returns",
    "guaranteed results",
    "guaranteed profit",
    "we guarantee",
    "i guarantee",
    "i promise you",
    "definitely cure",
    "will cure",
    "money back guaranteed",
    "risk free",
    "no risk",
    "zero risk",
    "double your money",
    "assured returns",
    # Hinglish
    "guarantee deta",
    "guarantee deti",
    "pakka faayda",
    "pakka profit",
    "100% pakka",
    "definitely thik ho jaoge",
]

# Medical / legal / financial advice trigger words (out of a sales agent's scope).
_ADVICE_TRIGGERS: list[str] = [
    "you should take",
    "i recommend taking",
    "prescribe",
    "diagnosis",
    "legal advice",
    "you must sue",
    "tax loophole",
    "evade tax",
    "invest all your",
    "guaranteed investment",
    "stop your medication",
    "dawai band",
    "medicine band kar",
    "tax bacha",
    "kanooni salah",
]

# Robotic phrases — rewrite (strip), not block.
_ROBOTIC_PHRASES: list[str] = [
    "as an ai language model",
    "as an ai",
    "i am an ai language model",
    "i'm just a language model",
    "i am unable to",
    "i cannot fulfill",
    "as a large language model",
    "i'm sorry, but as an ai",
]

# Safe fallback lines (jab output block ho jaye).
_SAFE_OUTPUT_FALLBACK = (
    "Maaf kijiye, woh detail main yahin confirm nahi kar sakti — "
    "main aapke liye humari team se exact info confirm karwa deti hoon."
)
_SAFE_REWRITE_FALLBACK = (
    "Achha sawaal — exact detail main aapke liye team se confirm karwa deti hoon."
)


# --------------------------------------------------------------------------- #
# Guardrails
# --------------------------------------------------------------------------- #
class Guardrails:
    """
    Rule-based, sub-200ms guardrails for the voice agent.

    Defensive by design: koi bhi check exception de to woh check skip ho jata hai
    (fail-open for the specific rule) — poora pipeline kabhi crash nahi karta.

    Args:
        extra_blocklist     : extra injection/jailbreak phrases (lowercased match).
        extra_pii_patterns  : list of (replacement, compiled_or_str_regex) tuples.
        extra_profanity     : extra profanity words to flag.
        block_profanity     : agar True -> profanity bhi block kare (default flag-only).
    """

    def __init__(
        self,
        extra_blocklist: list[str] | None = None,
        extra_pii_patterns: list[tuple[str, object]] | None = None,
        extra_profanity: list[str] | None = None,
        block_profanity: bool = False,
    ):
        self.block_profanity = block_profanity

        # PII patterns (copy base + caller extras, compiling any str patterns).
        self._pii_patterns: list[tuple[str, Pattern]] = list(_PII_PATTERNS)
        for repl, pat in extra_pii_patterns or []:
            try:
                compiled = pat if hasattr(pat, "search") else re.compile(str(pat))
                self._pii_patterns.append((repl, compiled))
            except Exception as e:  # pragma: no cover
                logger.debug(f"skip bad extra_pii_pattern {pat!r}: {e}")

        self._injection = list(_INJECTION_PHRASES) + [p.lower() for p in (extra_blocklist or [])]
        self._profanity = list(_PROFANITY_WORDS) + [p.lower() for p in (extra_profanity or [])]
        # Profanity word-boundary regex (precompiled once).
        try:
            self._profanity_re = (
                re.compile(
                    r"\b(" + "|".join(re.escape(w) for w in self._profanity) + r")\b",
                    re.IGNORECASE,
                )
                if self._profanity
                else None
            )
        except Exception:  # pragma: no cover
            self._profanity_re = None

    # ----------------------- PII redaction ----------------------- #
    def redact_pii(self, text: str) -> str:
        """
        Reusable PII redaction (logs / transcripts ke liye bhi).
        Phone, email, Aadhaar, PAN, credit-card, UPI -> [REDACTED_*].
        Kabhi crash nahi — error pe original text wapas.
        """
        if not text:
            return text or ""
        out = text
        for repl, pat in self._pii_patterns:
            try:
                out = pat.sub(repl, out)
            except Exception as e:  # pragma: no cover
                logger.debug(f"PII pattern skip ({repl}): {e}")
        return out

    def redact_for_logs(self, text: str) -> str:
        """
        Stronger redaction for stored logs / observability.
        PII ke alawa: lambe digit-runs (>=6) aur '@handle' jaise tokens bhi maskk
        karta hai, taaki accidental leakage na ho.
        """
        if not text:
            return text or ""
        out = self.redact_pii(text)
        try:
            # Koi bhi 6+ digit run mask karo (account no, otp, ids).
            out = re.sub(r"(?<!\[)(?<!\w)\d{6,}(?!\w)", "[REDACTED_NUM]", out)
            # Bacha hua koi @handle (jo UPI list me na ho) mask karo.
            out = re.sub(r"(?<!\w)@[A-Za-z0-9._\-]{2,}", "[REDACTED_HANDLE]", out)
        except Exception as e:  # pragma: no cover
            logger.debug(f"redact_for_logs extra step skip: {e}")
        return out

    # ----------------------- PRE-LLM ----------------------- #
    def check_input(self, text: str) -> GuardrailResult:
        """
        PRE-LLM check. Customer ka text LLM tak jaane se pehle:
          1. PII redact
          2. prompt-injection / jailbreak -> BLOCK
          3. profanity -> flag (ya block agar block_profanity=True)

        Returns GuardrailResult jisme `text` = redacted text (LLM ko yahi bhejo).
        """
        try:
            original = text or ""
            violations: list[str] = []

            # 1) PII redact (hamesha — chahe block ho ya na ho)
            redacted = self.redact_pii(original)
            if redacted != original:
                violations.append("pii_redacted")

            low = original.lower()

            # 2) Injection / jailbreak -> high severity block
            hit = self._first_match(low, self._injection)
            if hit:
                violations.append(f"prompt_injection:{hit}")
                return GuardrailResult(
                    allowed=False,
                    action="block",
                    text=redacted,
                    violations=violations,
                    severity="high",
                )

            # 3) Profanity -> flag (ya block)
            prof = self._profanity_hit(low)
            if prof:
                violations.append(f"profanity:{prof}")
                if self.block_profanity:
                    return GuardrailResult(
                        allowed=False,
                        action="block",
                        text=redacted,
                        violations=violations,
                        severity="medium",
                    )

            if "pii_redacted" in violations:
                return GuardrailResult(
                    allowed=True,
                    action="redact",
                    text=redacted,
                    violations=violations,
                    severity="medium" if prof else "low",
                )
            if prof:
                return GuardrailResult(
                    allowed=True,
                    action="allow",
                    text=redacted,
                    violations=violations,
                    severity="low",
                )
            return GuardrailResult(
                allowed=True,
                action="allow",
                text=redacted,
                violations=[],
                severity="none",
            )
        except Exception as e:  # pragma: no cover
            logger.debug(f"check_input failed-open: {e}")
            return GuardrailResult(
                allowed=True,
                action="allow",
                text=text or "",
                violations=["guardrail_error"],
                severity="none",
            )

    # ----------------------- POST-LLM ----------------------- #
    def check_output(
        self,
        text: str,
        allowed_topics: list[str] | None = None,
        known_facts: list[str] | None = None,
    ) -> GuardrailResult:
        """
        POST-LLM check. Bot ka reply customer tak jaane se pehle:
          * system-prompt / internal-instruction leak -> BLOCK
          * unsafe promises (guarantee, medical/legal/financial advice) -> BLOCK
          * robotic "as an AI language model" -> REWRITE (strip)
          * wildly off-topic (allowed_topics diye to) -> BLOCK
          * light hallucination check (known_facts diye to) -> REWRITE suggest

        Returns GuardrailResult jisme `text` = safe text (yahi bolo).
        """
        try:
            original = (text or "").strip()
            if not original:
                return GuardrailResult(
                    allowed=True,
                    action="allow",
                    text="",
                    violations=[],
                    severity="none",
                )
            low = original.lower()
            violations: list[str] = []

            # 1) System-prompt / instruction leak -> hard block
            leak = self._first_match(low, _LEAK_PHRASES)
            if leak:
                violations.append(f"system_leak:{leak}")
                return GuardrailResult(
                    allowed=False,
                    action="block",
                    text=_SAFE_OUTPUT_FALLBACK,
                    violations=violations,
                    severity="high",
                )

            # 2) Unsafe promises -> block
            promise = self._first_match(low, _UNSAFE_PROMISE_PHRASES)
            if promise:
                violations.append(f"unsafe_promise:{promise}")
                return GuardrailResult(
                    allowed=False,
                    action="block",
                    text=_SAFE_OUTPUT_FALLBACK,
                    violations=violations,
                    severity="high",
                )

            # 3) Out-of-scope medical/legal/financial advice -> block
            advice = self._first_match(low, _ADVICE_TRIGGERS)
            if advice:
                violations.append(f"out_of_scope_advice:{advice}")
                return GuardrailResult(
                    allowed=False,
                    action="block",
                    text=_SAFE_OUTPUT_FALLBACK,
                    violations=violations,
                    severity="high",
                )

            safe = original

            # 4) Robotic phrases -> rewrite (strip), block nahi
            robo = self._first_match(low, _ROBOTIC_PHRASES)
            if robo:
                violations.append(f"robotic:{robo}")
                safe = self._strip_phrases(safe, _ROBOTIC_PHRASES)
                if not safe.strip():
                    safe = _SAFE_REWRITE_FALLBACK

            # 5) Wildly off-topic -> block (sirf jab allowed_topics diye hon)
            if allowed_topics:
                if self._is_off_topic(low, allowed_topics):
                    violations.append("off_topic")
                    return GuardrailResult(
                        allowed=False,
                        action="block",
                        text=_SAFE_OUTPUT_FALLBACK,
                        violations=violations,
                        severity="medium",
                    )

            # 6) Light hallucination / grounding -> softer "rewrite" suggestion
            if known_facts and self._unsupported_number_claim(safe, known_facts):
                violations.append("possible_hallucination")
                return GuardrailResult(
                    allowed=True,
                    action="rewrite",
                    text=safe,
                    violations=violations,
                    severity="low",
                )

            if violations:
                # sirf robotic-strip type changes the —> rewrite/allow
                action = "rewrite" if safe != original else "allow"
                return GuardrailResult(
                    allowed=True,
                    action=action,
                    text=safe,
                    violations=violations,
                    severity="low",
                )
            return GuardrailResult(
                allowed=True,
                action="allow",
                text=safe,
                violations=[],
                severity="none",
            )
        except Exception as e:  # pragma: no cover
            logger.debug(f"check_output failed-open: {e}")
            return GuardrailResult(
                allowed=True,
                action="allow",
                text=text or "",
                violations=["guardrail_error"],
                severity="none",
            )

    # ----------------------- internal helpers ----------------------- #
    @staticmethod
    def _first_match(low_text: str, phrases: list[str]) -> str | None:
        """Pehla phrase jo low_text me WHOLE-WORD mile. None agar koi nahi.
        BUGFIX (2026-07-05): substring match legit turns ko injection samajh ke
        block kar deta tha ("exact assessment" me "act as" -> allowed=False ->
        NaturalDialogManager deflect). Word-boundary lookarounds se fix (trailing
        ':' wale phrase "new instructions:" ke liye \\b ki jagah (?<!\\w)/(?!\\w))."""
        for p in phrases:
            if not p:
                continue
            try:
                if re.search(r"(?<!\w)" + re.escape(p) + r"(?!\w)", low_text):
                    return p
            except Exception:
                if p in low_text:  # regex edge-case → safe substring fallback
                    return p
        return None

    def _profanity_hit(self, low_text: str) -> str | None:
        if self._profanity_re is None:
            return None
        try:
            m = self._profanity_re.search(low_text)
            return m.group(0) if m else None
        except Exception:  # pragma: no cover
            return None

    @staticmethod
    def _strip_phrases(text: str, phrases: list[str]) -> str:
        out = text
        for p in phrases:
            try:
                out = re.sub(re.escape(p), "", out, flags=re.IGNORECASE)
            except Exception:  # pragma: no cover
                continue
        # double spaces / leftover punctuation cleanup
        out = re.sub(r"\s{2,}", " ", out)
        out = re.sub(r"^\s*[,\.\-:;]+\s*", "", out)
        return out.strip()

    @staticmethod
    def _is_off_topic(low_text: str, allowed_topics: list[str]) -> bool:
        """
        Bahut halka off-topic check: agar reply lamba hai AUR kisi bhi allowed
        topic keyword ka zikr nahi -> off-topic maano. Chhoti acknowledgements
        ("haan", "theek hai") ko off-topic nahi ginte.
        """
        words = low_text.split()
        if len(words) < 8:  # short ack/answers ko chhodo
            return False
        for t in allowed_topics:
            t = (t or "").lower().strip()
            if t and t in low_text:
                return False
        return True

    @staticmethod
    def _unsupported_number_claim(text: str, known_facts: list[str]) -> bool:
        """
        Light grounding check: agar output me koi specific number/% claim hai jo
        kisi known_fact me literally maujood nahi -> possibly hallucinated.
        Pure heuristic (false-positive avoid karne ke liye soft 'rewrite' deta hai).
        """
        try:
            nums = re.findall(r"\d+(?:\.\d+)?%?", text or "")
            if not nums:
                return False
            facts_blob = " ".join(known_facts or []).lower()
            for n in nums:
                # Pure year/time-ish small tokens ko ignore mat karo blindly;
                # bas check karo number known_facts me hai ki nahi.
                if n.lower() not in facts_blob:
                    return True
            return False
        except Exception:  # pragma: no cover
            return False


# --------------------------------------------------------------------------- #
# Module singleton
# --------------------------------------------------------------------------- #
_GUARDRAILS_SINGLETON: Guardrails | None = None


def get_guardrails(**kwargs) -> Guardrails:
    """
    Process-wide singleton Guardrails instance (lazy).
    kwargs sirf pehli baar par lagte hain (constructor config).
    """
    global _GUARDRAILS_SINGLETON
    if _GUARDRAILS_SINGLETON is None:
        try:
            _GUARDRAILS_SINGLETON = Guardrails(**kwargs)
        except Exception as e:  # pragma: no cover
            logger.warning(f"Guardrails init fallback (defaults): {e}")
            _GUARDRAILS_SINGLETON = Guardrails()
    return _GUARDRAILS_SINGLETON


__all__ = ["Guardrails", "GuardrailResult", "get_guardrails"]
