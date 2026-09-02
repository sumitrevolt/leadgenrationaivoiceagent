"""
LatencyOptimizer — sub-second perceived-latency layer (LiveKit/Retell-style).

This module is a PURE-PYTHON, zero-external-service add-on that the voice
pipeline can lean on to *feel* instant. It bundles the four 2026 best-practice
techniques that the best realtime voice agents use, none of which need a network
call to work:

  1. RESPONSE / PROMPT CACHING (`ResponseCache`)
     An LRU+TTL cache keyed on a *normalized* utterance, so FAQ-like questions
     ("kitna hai?", "Kitna hai", "  kitna   hai ??") all collapse to one key and
     return an INSTANT answer — skipping the LLM entirely (also cuts cost).

  2. FIRST-SENTENCE TTS CHUNKING (`FirstSentenceChunker`)
     Splits the LLM reply so the FIRST sentence is handed to TTS immediately
     while the rest is still being generated. Speaking begins on chunk #1, which
     drops *perceived* latency 3-5x — the caller hears audio long before the full
     reply exists. Hindi danda "।" + "."/"?"/"!" aware.

  3. PARTIAL-TRANSCRIPT STREAMING (`PartialTranscriptBuffer`)
     Accumulates partial STT pieces and decides — via a stable-text + silence
     endpoint heuristic — when the user's turn is *done*, so partials can be fed
     to the LLM early instead of waiting for a final transcript.

  4. PARALLEL WARMUP + METRICS (`LatencyOptimizer` / `TurnTimer`)
     A facade tying it together, with TTFT (time-to-first-token/audio) and total
     latency tracking plus a cache hit-rate summary, and an optional `prewarm`
     hook to spin providers up before the first real turn.

Everything is defensive: nothing here raises on bad input, and it runs with the
Mock providers (zero deps) exactly like the rest of the voice_agent package.

Usage example (cache hit + first-sentence chunking)::

    import asyncio
    from app.voice_agent.latency import get_optimizer

    async def main():
        opt = get_optimizer()

        async def generate(utterance: str) -> str:
            # pretend this is a slow LLM call
            await asyncio.sleep(0.4)
            return "Haan ji bilkul. Hamara AI marketing plan 1999 ka hai. Book karein?"

        # First time: MISS -> calls generate, caches the answer.
        text, timer = await opt.fast_respond(generate, "Price kitna hai?")
        print("MISS:", timer.cache_hit, round(timer.ttft_ms, 1), "ms")

        # Same question (different casing/punct): HIT -> instant, no LLM.
        text, timer = await opt.fast_respond(generate, "price kitna hai")
        print("HIT :", timer.cache_hit, round(timer.ttft_ms, 1), "ms")

        # Start TTS on the FIRST sentence while the rest is still pending:
        first, rest = opt.chunker.split_for_tts(text)
        print("speak now:", first)        # -> TTS immediately
        print("queue   :", rest)          # -> synthesize while bot already talks

        print(opt.metrics())              # avg ttft, cache hit-rate, etc.

    asyncio.run(main())
"""

import asyncio
import re
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from typing import (
    Any,
)

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# =============================================================================
# RESPONSE / PROMPT CACHE  (LRU + TTL)
# =============================================================================

# Filler words stripped during normalization so semantically-equal utterances
# collapse to the same cache key (Hinglish-aware). Kept small + safe.
_FILLERS = {
    "uh",
    "um",
    "uhh",
    "umm",
    "hmm",
    "ah",
    "eh",
    "er",
    "well",
    "actually",
    "basically",
    "like",
    "so",
    "ok",
    "okay",
    "achha",
    "acha",
    "haan",
    "han",
    "ji",
    "bhai",
    "yaar",
    "matlab",
    "toh",
    "to",
    "na",
    "please",
    "plz",
    "kya",
    "are",
    "arre",
}

# Punctuation incl. the Hindi danda + question mark variants.
_PUNCT_RE = re.compile(r"[.,!?;:\"'`~/\\|()\[\]{}<>।॥…\-_*#@&%$^+=]+")
_WS_RE = re.compile(r"\s+")


@dataclass
class _CacheEntry:
    value: str
    expires_at: float  # monotonic deadline; float("inf") => no TTL


class ResponseCache:
    """
    LRU cache with optional TTL for repeated / FAQ-like answers.

    The key is the *normalized* user utterance, so "Kitna hai?", "kitna hai" and
    "  KITNA   HAI ??" all map to the same entry and return an INSTANT reply,
    skipping the LLM (and saving cost). Capacity-bounded LRU; expired entries are
    evicted lazily on access.

    Args:
        max_size: max number of cached entries (LRU evicts the oldest).
        ttl_s: seconds an entry stays fresh; None / <=0 => never expires.
    """

    def __init__(self, max_size: int = 256, ttl_s: float | None = 1800.0) -> None:
        self.max_size = max(1, int(max_size))
        self.ttl_s = ttl_s if (ttl_s is None or ttl_s > 0) else None
        self._store: OrderedDict[str, _CacheEntry] = OrderedDict()
        self.hits = 0
        self.misses = 0

    # -- key building ------------------------------------------------------

    @staticmethod
    def normalize(text: str) -> str:
        """
        Turn a raw user utterance into a stable cache key:
        lowercase -> strip punctuation -> drop filler words -> collapse
        whitespace. Empty / None safe (returns "").

        So "Kitna hai?" and "kitna hai" both normalize to "kitna hai" — wait,
        "kitna" is a filler here, so both become "hai". The point is *consistent*
        collapsing, not linguistic perfection: identical utterances always share
        a key. If after filler-stripping nothing remains, we fall back to the
        punctuation-stripped form so the entry is never blank.
        """
        if not text:
            return ""
        low = text.lower().strip()
        # Strip punctuation (incl. danda) to spaces, then collapse whitespace.
        stripped = _PUNCT_RE.sub(" ", low)
        stripped = _WS_RE.sub(" ", stripped).strip()
        if not stripped:
            return ""
        tokens = stripped.split(" ")
        kept = [t for t in tokens if t and t not in _FILLERS]
        if not kept:
            # Everything was a filler -> keep the punctuation-stripped form so
            # distinct filler-only utterances don't all collide to "".
            return stripped
        return " ".join(kept)

    # -- core ops ----------------------------------------------------------

    def _expired(self, entry: _CacheEntry) -> bool:
        return time.monotonic() >= entry.expires_at

    def get(self, key: str) -> str | None:
        """
        Look up an answer by RAW utterance (normalized internally). Returns the
        cached string on a fresh hit, else None. Updates hit/miss counters and
        LRU recency.
        """
        norm = self.normalize(key)
        if not norm:
            self.misses += 1
            return None
        entry = self._store.get(norm)
        if entry is None:
            self.misses += 1
            return None
        if self._expired(entry):
            # Lazy eviction of a stale entry.
            self._store.pop(norm, None)
            self.misses += 1
            return None
        # Fresh hit -> mark most-recently-used.
        self._store.move_to_end(norm)
        self.hits += 1
        return entry.value

    def put(self, key: str, value: str) -> None:
        """
        Cache `value` under the normalized form of RAW utterance `key`. No-ops on
        empty key/value. Enforces LRU capacity and (re)sets the TTL deadline.
        """
        norm = self.normalize(key)
        if not norm or value is None or value == "":
            return
        deadline = float("inf") if self.ttl_s is None else time.monotonic() + self.ttl_s
        if norm in self._store:
            self._store.move_to_end(norm)
        self._store[norm] = _CacheEntry(value=value, expires_at=deadline)
        # Evict oldest until within capacity.
        while len(self._store) > self.max_size:
            self._store.popitem(last=False)

    async def cached_or(self, fn: Callable[[str], Any], utterance: str) -> tuple[str, bool]:
        """
        Return a cached answer for `utterance` if present, else call `fn`
        (sync OR async) to produce one, cache it, and return it.

        Returns (answer, was_cache_hit). `fn` receives the raw utterance and may
        return a str (sync) or an awaitable resolving to str. Never raises: if
        `fn` blows up, returns ("", False).
        """
        cached = self.get(utterance)
        if cached is not None:
            return cached, True
        try:
            result = fn(utterance)
            if asyncio.iscoroutine(result) or isinstance(result, Awaitable):
                result = await result  # type: ignore[assignment]
            answer = result or ""
            answer = answer.strip() if isinstance(answer, str) else str(answer)
        except Exception as e:  # never crash the call
            logger.warning(f"cached_or: generator fn failed: {e}")
            return "", False
        if answer:
            self.put(utterance, answer)
        return answer, False

    # -- diagnostics -------------------------------------------------------

    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return (self.hits / total) if total else 0.0

    def stats(self) -> dict[str, Any]:
        return {
            "size": len(self._store),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hit_rate(), 3),
            "ttl_s": self.ttl_s,
        }

    def clear(self) -> None:
        self._store.clear()
        self.hits = 0
        self.misses = 0


# =============================================================================
# FIRST-SENTENCE TTS CHUNKER
# =============================================================================

# Sentence terminators: ASCII . ? ! + Hindi danda "।" / double danda "॥".
_SENT_END_CHARS = ".?!।॥"
# A boundary = one-or-more terminators (optionally with trailing quotes/brackets)
# followed by whitespace or end-of-string. Captured so we keep the punctuation.
_SENT_SPLIT_RE = re.compile(r"([.?!।॥]+[\"'’”）)\]]*)(?:\s+|$)")


class FirstSentenceChunker:
    """
    Split an LLM reply into sentence-sized chunks so TTS can start on the FIRST
    one while the rest is still being generated/synthesized.

    Danda-aware ("।"/"॥") plus ASCII "." / "?" / "!". Designed to never lose
    text: concatenating the chunks reproduces the trimmed original content.

    Args:
        min_first_chars: if the very first sentence is shorter than this, the
            next sentence(s) are merged into it so TTS doesn't fire on a tiny,
            awkward fragment (e.g. "Haan."). Keeps the opening natural.
    """

    def __init__(self, min_first_chars: int = 12) -> None:
        self.min_first_chars = max(0, int(min_first_chars))

    def _raw_sentences(self, text: str) -> list[str]:
        """Split into sentences keeping terminating punctuation; whitespace-trim."""
        if not text:
            return []
        text = text.strip()
        if not text:
            return []
        out: list[str] = []
        last = 0
        for m in _SENT_SPLIT_RE.finditer(text):
            end = m.end(1)  # include the punctuation, exclude trailing space
            piece = text[last:end].strip()
            if piece:
                out.append(piece)
            last = m.end()
        # Trailing remainder with no terminator (e.g. a dangling phrase).
        tail = text[last:].strip()
        if tail:
            out.append(tail)
        return out

    def split_for_tts(self, text: str) -> tuple[str, str]:
        """
        Return (first_sentence, remainder).

        `first_sentence` is emitted to TTS IMMEDIATELY; `remainder` is whatever
        is left (possibly "") to synthesize while the bot is already speaking.
        If the first sentence is shorter than `min_first_chars`, following
        sentences are merged in so the opening isn't a tiny fragment.
        """
        sentences = self._raw_sentences(text)
        if not sentences:
            return "", ""
        first = sentences[0]
        idx = 1
        # Grow the first chunk until it's long enough to feel natural.
        while idx < len(sentences) and len(first) < self.min_first_chars:
            first = (first + " " + sentences[idx]).strip()
            idx += 1
        remainder = " ".join(sentences[idx:]).strip()
        return first, remainder

    def stream_chunks(self, text: str) -> Iterator[str]:
        """
        Yield sentence-sized chunks in order, with the first chunk honoring
        `min_first_chars` (so TTS can start on chunk #1). Generator — feed each
        chunk to TTS as it arrives. Empty input yields nothing.
        """
        first, remainder = self.split_for_tts(text)
        if first:
            yield first
        if remainder:
            for s in self._raw_sentences(remainder):
                if s:
                    yield s


# =============================================================================
# PARTIAL-TRANSCRIPT BUFFER  (early-send endpointing)
# =============================================================================


class PartialTranscriptBuffer:
    """
    Accumulate partial STT hypotheses and decide when the user's turn is done so
    partials can be sent to the LLM *early* (instead of waiting for the final
    transcript). The endpoint heuristic: the latest partial has been STABLE
    (unchanged) AND silence has lasted past a threshold.

    Args:
        silence_ms_threshold: silence (ms since last text change) that, combined
            with a stable transcript, signals end-of-turn.
        min_chars: don't commit on tiny/blank partials (avoids false triggers).
        stable_repeats: how many consecutive identical partials count as
            "stable" (debounces flickering STT output).
    """

    def __init__(
        self,
        silence_ms_threshold: float = 600.0,
        min_chars: int = 2,
        stable_repeats: int = 2,
    ) -> None:
        self.silence_ms_threshold = float(silence_ms_threshold)
        self.min_chars = max(0, int(min_chars))
        self.stable_repeats = max(1, int(stable_repeats))
        self._current = ""
        self._stable_count = 0

    def reset(self) -> None:
        """Clear buffer for the next user turn."""
        self._current = ""
        self._stable_count = 0

    @property
    def text(self) -> str:
        """The latest accumulated partial transcript."""
        return self._current

    def update(self, partial: str) -> str:
        """
        Feed a new partial transcript. We treat each `partial` as the best
        current hypothesis for the whole utterance (typical streaming-STT shape):
        a longer/changed partial replaces the buffer; an identical one bumps the
        stability counter. Returns the current accumulated text.
        """
        if partial is None:
            return self._current
        partial = partial.strip()
        if not partial:
            return self._current
        if partial == self._current:
            self._stable_count += 1
        else:
            self._current = partial
            self._stable_count = 1
        return self._current

    def should_commit(self, partial: str, silence_ms: float) -> bool:
        """
        Endpoint heuristic: update with `partial`, then return True if the user's
        turn looks DONE — i.e. the transcript is non-trivial, has been stable for
        `stable_repeats`, and silence has lasted >= `silence_ms_threshold`.

        Call this on every partial/silence tick; commit (send to LLM) when True.
        """
        text = self.update(partial)
        if len(text) < self.min_chars:
            return False
        if self._stable_count < self.stable_repeats:
            return False
        return float(silence_ms) >= self.silence_ms_threshold

    def commit(self) -> str:
        """Return the final transcript and reset the buffer for the next turn."""
        final = self._current
        self.reset()
        return final


# =============================================================================
# TURN TIMER  (TTFT + total latency)
# =============================================================================


@dataclass
class TurnTimer:
    """
    Per-turn latency record. TTFT = time-to-first-token/audio: the moment the
    user could first perceive a response (first LLM token, or first TTS chunk
    handed off). `total_ms` is the full turn. `cache_hit` flags an instant
    cached answer.
    """

    start: float = field(default_factory=time.monotonic)
    ttft_ms: float = 0.0
    total_ms: float = 0.0
    cache_hit: bool = False
    _ttft_marked: bool = field(default=False, repr=False)

    def mark_first(self) -> float:
        """Record TTFT at the first token/audio chunk. Idempotent per turn."""
        if not self._ttft_marked:
            self.ttft_ms = (time.monotonic() - self.start) * 1000.0
            self._ttft_marked = True
        return self.ttft_ms

    def finish(self) -> float:
        """Record total turn latency; if TTFT was never marked, mark it now."""
        now = time.monotonic()
        if not self._ttft_marked:
            self.ttft_ms = (now - self.start) * 1000.0
            self._ttft_marked = True
        self.total_ms = (now - self.start) * 1000.0
        return self.total_ms

    def as_dict(self) -> dict[str, Any]:
        return {
            "ttft_ms": round(self.ttft_ms, 1),
            "total_ms": round(self.total_ms, 1),
            "cache_hit": self.cache_hit,
        }


# =============================================================================
# LATENCY OPTIMIZER  (facade)
# =============================================================================


class LatencyOptimizer:
    """
    Facade tying caching + first-sentence chunking + partial-transcript
    endpointing + TTFT metrics into one place the pipeline can call.

    Holds rolling aggregate metrics (avg TTFT, avg total, cache hit-rate) so you
    can prove the latency wins. Pure-python, never raises on bad input.
    """

    def __init__(
        self,
        cache: ResponseCache | None = None,
        chunker: FirstSentenceChunker | None = None,
        partial_buffer: PartialTranscriptBuffer | None = None,
    ) -> None:
        self.cache = cache or ResponseCache()
        self.chunker = chunker or FirstSentenceChunker()
        self.partial_buffer = partial_buffer or PartialTranscriptBuffer()

        # Rolling metrics across turns.
        self._turns = 0
        self._ttft_sum = 0.0
        self._total_sum = 0.0
        self._cache_hits = 0

        # Pre-synthesized greeting AUDIO cache (key -> TTS audio bytes). Lets a new
        # call stream its opening line INSTANTLY (no synth on the critical path) for
        # a sub-300ms TTFT. Populated via presynthesize_greetings() at warmup.
        self._audio_cache: dict[str, bytes] = {}

    # -- warmup ------------------------------------------------------------

    def prewarm(self, providers: Any | None = None) -> None:
        """
        Optional, no-op-safe parallel-warmup hook. Touches provider singletons so
        the first REAL turn doesn't pay construction/connection cost. Accepts a
        ProviderRegistry, an iterable of providers, or None (auto-resolve the
        module registry). Never raises.
        """
        try:
            reg = providers
            if reg is None:
                from app.voice_agent.providers import get_registry

                reg = get_registry()
            # If it's a registry, eagerly build each provider (cached thereafter).
            for getter in ("get_stt", "get_tts", "get_llm"):
                fn = getattr(reg, getter, None)
                if callable(fn):
                    try:
                        fn()
                    except Exception as e:
                        logger.debug(f"prewarm {getter} skipped: {e}")
            logger.debug("LatencyOptimizer prewarm complete.")
        except Exception as e:
            logger.debug(f"prewarm no-op (providers unavailable): {e}")

    # -- timer factory + metrics recording --------------------------------

    def start_turn(self) -> TurnTimer:
        """Create a fresh TurnTimer for a turn."""
        return TurnTimer()

    def record(self, timer: TurnTimer) -> None:
        """Fold a finished TurnTimer into rolling aggregate metrics."""
        if not timer._ttft_marked or timer.total_ms == 0.0:
            timer.finish()
        self._turns += 1
        self._ttft_sum += timer.ttft_ms
        self._total_sum += timer.total_ms
        if timer.cache_hit:
            self._cache_hits += 1

    def metrics(self) -> dict[str, Any]:
        """
        Aggregate latency summary: turn count, avg TTFT, avg total, and cache
        hit-rate (combining timer-level hits with the cache's own counters).
        """
        turns = self._turns or 1
        return {
            "turns": self._turns,
            "avg_ttft_ms": round(self._ttft_sum / turns, 1),
            "avg_total_ms": round(self._total_sum / turns, 1),
            "turn_cache_hit_rate": round(self._cache_hits / turns, 3),
            "cache": self.cache.stats(),
        }

    def reset_metrics(self) -> None:
        self._turns = 0
        self._ttft_sum = 0.0
        self._total_sum = 0.0
        self._cache_hits = 0

    # -- pre-synthesized greeting audio cache (instant first-token) --------

    def cache_audio(self, key: str, audio: bytes) -> None:
        """Store pre-synthesized audio bytes under `key` (e.g. a niche name)."""
        if key and isinstance(audio, (bytes, bytearray)) and audio:
            self._audio_cache[str(key)] = bytes(audio)

    def get_cached_audio(self, key: str) -> bytes | None:
        """Retrieve pre-synthesized audio bytes for `key`, or None if not cached."""
        return self._audio_cache.get(str(key or ""))

    def has_cached_audio(self, key: str) -> bool:
        return str(key or "") in self._audio_cache

    def audio_cache_keys(self) -> list[str]:
        return list(self._audio_cache.keys())

    async def presynthesize_greetings(self, tts: Any, greetings: dict[str, str]) -> int:
        """Pre-synthesize + cache greeting audio for many keys (niche -> text).

        `tts` = a TTS provider with `synthesize(text)` (sync or async) -> bytes
        (the project's `registry.get_tts()`). Best-effort: koi fail ho to skip.
        Returns how many greetings got cached. Never raises.
        """
        cached = 0
        for key, text in (greetings or {}).items():
            if not key or not text or self.has_cached_audio(key):
                continue
            try:
                audio = tts.synthesize(text)
                if asyncio.iscoroutine(audio) or isinstance(audio, Awaitable):
                    audio = await audio  # type: ignore[assignment]
                if isinstance(audio, (bytes, bytearray)) and audio:
                    self.cache_audio(key, bytes(audio))
                    cached += 1
            except Exception as e:
                logger.debug(f"presynth greeting '{key}' skipped: {e}")
        if cached:
            logger.info(
                f"🔊 LatencyOptimizer: pre-cached {cached} greeting clip(s) for instant TTFT."
            )
        return cached

    # -- the end-to-end fast path -----------------------------------------

    async def fast_respond(
        self,
        generate_fn: Callable[[str], Any],
        utterance: str,
        kb: Any | None = None,
    ) -> tuple[str, TurnTimer]:
        """
        Produce a reply for `utterance` on the lowest-latency path and return
        (text, TurnTimer). Order:

            1. CACHE  — normalized lookup; on hit, return INSTANTLY (no LLM).
            2. KB     — optional knowledge-base instant answer (see below).
            3. LLM    — call `generate_fn` (sync or async), then cache the result.

        TTFT is marked the moment an answer first exists (cache/KB = immediate;
        LLM = when `generate_fn` returns). The result is recorded into rolling
        metrics. Never raises — on failure returns ("", timer).

        `kb` may be:
          * a callable `kb(utterance) -> Optional[str]` (sync or async), or
          * an object with a `.lookup(utterance)` / `.get(utterance)` method.
        Return a non-empty string for an instant answer, else None to fall
        through to the LLM. Instant KB answers are cached too.
        """
        timer = self.start_turn()

        # 1) CACHE — the fastest path.
        cached = self.cache.get(utterance)
        if cached is not None:
            timer.cache_hit = True
            timer.mark_first()
            timer.finish()
            self.record(timer)
            return cached, timer

        # 2) KB — optional instant answer before paying for the LLM.
        kb_answer = await self._try_kb(kb, utterance)
        if kb_answer:
            timer.mark_first()
            timer.finish()
            self.cache.put(utterance, kb_answer)
            self.record(timer)
            return kb_answer, timer

        # 3) LLM — generate, then cache for next time.
        text, _was_hit = await self.cache.cached_or(generate_fn, utterance)
        timer.mark_first()
        timer.finish()
        self.record(timer)
        return text, timer

    @staticmethod
    async def _try_kb(kb: Any | None, utterance: str) -> str:
        """Resolve an optional KB instant answer. Tolerant + never raises."""
        if kb is None:
            return ""
        try:
            fn = None
            if callable(kb):
                fn = kb
            else:
                for meth in ("lookup", "get", "answer", "match"):
                    cand = getattr(kb, meth, None)
                    if callable(cand):
                        fn = cand
                        break
            if fn is None:
                return ""
            res = fn(utterance)
            if asyncio.iscoroutine(res) or isinstance(res, Awaitable):
                res = await res  # type: ignore[assignment]
            return res.strip() if isinstance(res, str) else ""
        except Exception as e:
            logger.debug(f"KB lookup skipped: {e}")
            return ""


def build_niche_greetings(agent_name: str = "Riya") -> dict[str, str]:
    """Hinglish code-switched opening greetings per configured niche (for pre-synth).

    Indian niches ke liye natural, chhota Hinglish greeting — phone-friendly, ek
    sawaal. NICHES na mile to sirf {"general": ...}. Never raises. Koi paid service
    nahi — yeh sirf FREE TTS (EdgeTTS) ke liye text deta hai.
    """
    out: dict[str, str] = {}
    try:
        from app.niches import NICHES

        for key, cfg in (NICHES or {}).items():
            name = (cfg or {}).get("name", key)
            out[str(key)] = (
                f"Namaste! Main {agent_name} bol rahi hoon, ek AI assistant. "
                f"Aapne {name} ke baare mein enquiry ki thi — kya main do minute baat kar sakti hoon?"
            )
    except Exception:
        pass
    out.setdefault(
        "general",
        (
            f"Namaste! Main {agent_name} bol rahi hoon, ek AI assistant. "
            "Aapke business ke leads aur marketing ke baare mein baat karni thi - "
            "kya main do minute le sakti hoon?"
        ),
    )
    return out


# =============================================================================
# MODULE SINGLETON
# =============================================================================

_optimizer: LatencyOptimizer | None = None


def get_optimizer() -> LatencyOptimizer:
    """Get the process-wide LatencyOptimizer singleton (lazy)."""
    global _optimizer
    if _optimizer is None:
        _optimizer = LatencyOptimizer()
    return _optimizer
