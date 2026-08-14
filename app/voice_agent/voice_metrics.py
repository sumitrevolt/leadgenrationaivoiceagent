"""
Objective voice-eval metrics — FREE, dependency-free (pure stdlib).

Upgrades agent_tester's heuristics (double/empty/slow) with measurable numbers
grounded in standard speech evaluation (WER/CER, latency percentiles, round-trip WER).  # nosecurity: eval-ref-in-comment
Skill: `.claude/skills/voice-eval-metrics/SKILL.md`.

Import-safe — kabhi raise nahi (project rule). No torch/jiwer/numpy: WER = word-level
Levenshtein, percentiles = stdlib. Bigger ASR/TTS evals me jiwer/speechbrain plug
kar sakte ho, par baseline scoring ke liye yeh kaafi + zero-dep.

Usage:
    from app.voice_agent.voice_metrics import wer, latency_summary, roundtrip_wer
    wer("turn on the lights", "turn on the light")        # 0.25
    latency_summary([120, 340, 980, 210])                  # {p50,p95,p99,mean,n,max}
    roundtrip_wer(texts, synth_fn=edge_tts, transcribe_fn=groq_whisper)
"""

from __future__ import annotations

import re
import string
from typing import Callable, Iterable, Sequence

# ASR/streaming targets (ph06/17 2026 reference) — agar number inse bahar = regression flag
WER_HUMAN_PARITY = 0.05  # <5% read-speech = human parity
ROUNDTRIP_WER_FLAG = 0.10  # TTS line >10% = intelligibility issue
BARGE_IN_TARGET_MS = 150.0  # user-interrupt → assistant-mute target


def normalize_text(s: str) -> str:
    """Lowercase, punctuation-strip, whitespace-collapse. ALWAYS before scoring
    (cardinal rule 1) — aur jo rule use kiya woh report karo."""
    if not s:
        return ""
    s = s.lower().strip()
    s = s.translate(str.maketrans("", "", string.punctuation))
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _edit_distance(ref: Sequence, hyp: Sequence) -> int:
    """Levenshtein (substitutions + deletions + insertions). O(n*m), token or char."""
    n, m = len(ref), len(hyp)
    if n == 0:
        return m
    if m == 0:
        return n
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[m]


def wer(reference: str, hypothesis: str, *, normalize: bool = True) -> float:
    """Word Error Rate = (S+D+I)/N over words. 0.0 = perfect. Empty ref → 0.0 if
    hyp also empty else 1.0."""
    ref = (normalize_text(reference) if normalize else reference).split()
    hyp = (normalize_text(hypothesis) if normalize else hypothesis).split()
    if not ref:
        return 0.0 if not hyp else 1.0
    return _edit_distance(ref, hyp) / len(ref)


def cer(reference: str, hypothesis: str, *, normalize: bool = True) -> float:
    """Character Error Rate — tone/segmentation-ambiguous languages (Hindi/Mandarin)
    ke liye WER se behtar."""
    ref = normalize_text(reference) if normalize else reference
    hyp = normalize_text(hypothesis) if normalize else hypothesis
    if not ref:
        return 0.0 if not hyp else 1.0
    return _edit_distance(ref, hyp) / len(ref)


def percentile(values: Sequence[float], p: float) -> float:
    """Linear-interpolated percentile (p in 0..100). Empty → 0.0."""
    if not values:
        return 0.0
    xs = sorted(values)
    if len(xs) == 1:
        return float(xs[0])
    k = (len(xs) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return float(xs[lo] + (xs[hi] - xs[lo]) * (k - lo))


def latency_summary(samples_ms: Sequence[float]) -> dict:
    """P50/P95/P99 + mean/max/n. CARDINAL RULE 2: latency me average nahi,
    distribution report karo (tail = real UX)."""
    vals = [float(x) for x in samples_ms if x is not None]
    if not vals:
        return {"n": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0, "max": 0.0}
    return {
        "n": len(vals),
        "p50": round(percentile(vals, 50), 1),
        "p95": round(percentile(vals, 95), 1),
        "p99": round(percentile(vals, 99), 1),
        "mean": round(sum(vals) / len(vals), 1),
        "max": round(max(vals), 1),
    }


def vaqi_summary(
    *,
    latencies_ms: Sequence[float] = (),
    turns_total: int = 0,
    missed_count: int = 0,
    interruptions_total: int | None = None,
    premature_interruptions: int | None = None,
) -> dict:
    """VAQI (Voice Agent Quality Index) — Deepgram's 3-leg conversational
    responsiveness score: Interruptions / Missed responses / Latency.

    ``missed_count`` = turns where the agent produced zero reply (NO_REPLY).
    Interruption fields are optional and stay ``None`` until a caller has real
    barge-in telemetry (our text-mode self-test harness has no overlapping
    audio, so it can only ever report latency + missed-response; live-call
    telemetry — once wired via Tracer.record_interruption — fills these in)."""
    latency = latency_summary(latencies_ms)
    missed_rate = round(missed_count / turns_total, 3) if turns_total else None
    interruption_rate = None
    if interruptions_total:
        interruption_rate = round((premature_interruptions or 0) / interruptions_total, 3)
    return {
        "latency": latency,
        "turns_total": turns_total,
        "missed_count": missed_count,
        "missed_response_rate": missed_rate,
        "interruptions_total": interruptions_total,
        "premature_interruptions": premature_interruptions,
        "interruption_rate": interruption_rate,
    }


def roundtrip_wer(
    texts: Iterable[str],
    synth_fn: Callable[[str], object],
    transcribe_fn: Callable[[object], str],
    *,
    flag_threshold: float = ROUNDTRIP_WER_FLAG,
) -> dict:
    """TTS intelligibility — FREE (Whisper over EdgeTTS). text → synth → transcribe →
    WER vs original. >threshold wale prompts = Swara woh line clearly nahi bol rahi.
    synth_fn/transcribe_fn caller deta (EdgeTTS + Groq-whisper already wired)."""
    rows = []
    for t in texts:
        try:
            audio = synth_fn(t)
            recog = transcribe_fn(audio)
            w = wer(t, recog)
        except Exception as e:  # never-raise: ek text fail = skip, baaki chalein
            rows.append({"text": t, "wer": None, "error": str(e)[:120]})
            continue
        rows.append({"text": t, "wer": round(w, 3), "flagged": w > flag_threshold})
    scored = [r["wer"] for r in rows if r.get("wer") is not None]
    return {
        "mean_wer": round(sum(scored) / len(scored), 3) if scored else None,
        "flagged": [r["text"] for r in rows if r.get("flagged")],
        "rows": rows,
    }


def score_asr(pairs: Iterable[tuple[str, str]]) -> dict:
    """Aggregate WER+CER over (reference, hypothesis) transcript pairs.
    CARDINAL RULE 3: aggregate accented/Hindi failure chhupata — caller slice-wise
    (Hinglish vs English-heavy) bula ke compare kare."""
    pairs = list(pairs)
    if not pairs:
        return {"n": 0, "wer": 0.0, "cer": 0.0}
    wers = [wer(r, h) for r, h in pairs]
    cers = [cer(r, h) for r, h in pairs]
    return {
        "n": len(pairs),
        "wer": round(sum(wers) / len(wers), 3),
        "cer": round(sum(cers) / len(cers), 3),
        "worst": sorted(
            ({"ref": r, "hyp": h, "wer": round(w, 3)} for (r, h), w in zip(pairs, wers)),
            key=lambda d: -d["wer"],
        )[:5],
    }
