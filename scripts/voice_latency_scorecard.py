#!/usr/bin/env python3
"""Voice latency scorecard — turn-taking latency + TTFT, p50/p95. FREE/offline.

WHY
---
The live-call "feel" is dominated by two numbers:
  * TTFT  (time-to-first-audio): from the moment the caller STOPS talking to the
    first byte of the bot's reply audio. This is what makes a call feel snappy.
  * TURN  (total turn latency): TTFT + speaking the whole reply (less important
    perceptually, but tracked).

TTFT = endpoint-delay (how long we wait in silence before deciding the turn
ended — the ``TURN_SILENCE_MS`` knob this task tunes) + STT + LLM + first-
sentence TTS. Lowering ``TURN_SILENCE_MS`` from 700 -> ~550 ms directly cuts
TTFT by ~150 ms, but too low clips slow talkers. This scorecard lets you SEE
the trade-off before touching a paid call.

This is FULLY OFFLINE and FREE: no phone, no STT/TTS/LLM API calls. Two modes:

  --mode sim   (default)  Analytic model: samples realistic per-stage latencies
                          (jittered) and the endpoint delay from the CURRENT env
                          (TURN_SILENCE_MS etc.), so you can A/B knobs instantly.
  --mode pipe             Drives the REAL app.voice_agent.pipeline.VoicePipeline
                          with Mock providers to measure framework/overhead. Adds
                          simulated stage sleeps so the numbers are lifelike.

Examples
--------
    python scripts/voice_latency_scorecard.py                 # sim, defaults
    TURN_SILENCE_MS=550 python scripts/voice_latency_scorecard.py
    python scripts/voice_latency_scorecard.py --mode pipe --runs 40
    python scripts/voice_latency_scorecard.py --json          # machine-readable

Tune the simulated free-stack stage latencies via env (ms), defaults reflect
observed Groq-Whisper / Cerebras / EdgeTTS behaviour on the VPS:
    SCORE_STT_MS=600  SCORE_LLM_MS=700  SCORE_TTS_FIRST_MS=420  SCORE_TTS_REST_MS=900
    SCORE_JITTER=0.25            # +/- fraction of random jitter per stage
    SCORE_VAD_OVERHEAD_MS=15     # Silero/RMS per-decision cost (when enabled)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import sys
import time


def _f(name: str, default: float) -> float:
    try:
        raw = os.environ.get(name, "")
        return float(raw) if raw.strip() != "" else default
    except Exception:
        return default


# --- simulated free-stack stage latencies (ms) ----------------------------- #
STT_MS = _f("SCORE_STT_MS", 600.0)  # Groq Whisper-large-v3 short utterance
LLM_MS = _f("SCORE_LLM_MS", 700.0)  # Cerebras gpt-oss-120b first token-ish
TTS_FIRST_MS = _f("SCORE_TTS_FIRST_MS", 420.0)  # EdgeTTS first short sentence
TTS_REST_MS = _f("SCORE_TTS_REST_MS", 900.0)  # remaining sentences (overlaps playback)
JITTER = _f("SCORE_JITTER", 0.25)  # +/- jitter fraction
VAD_OVERHEAD_MS = _f("SCORE_VAD_OVERHEAD_MS", 15.0)


def _endpoint_delay_ms() -> float:
    """The silence we wait through before declaring end-of-turn — the knob being
    tuned. Reads the SAME helper the live code uses so the scorecard reflects the
    real configured value (TURN_SILENCE_MS), with a safe literal fallback."""
    try:
        from app.voice_agent.turn_detector import turn_silence_ms

        return turn_silence_ms(700.0)
    except Exception:
        return _f("TURN_SILENCE_MS", 700.0)


def _vad_enabled() -> bool:
    return os.environ.get("USE_SILERO_VAD", "").strip().lower() in {"1", "true", "yes", "on"}


def _smart_turn_enabled() -> bool:
    return os.environ.get("USE_SMART_TURN", "").strip().lower() in {"1", "true", "yes", "on"}


def _jit(ms: float) -> float:
    """Apply +/- JITTER random noise to a base latency (never negative)."""
    if JITTER <= 0:
        return ms
    return max(0.0, ms * (1.0 + random.uniform(-JITTER, JITTER)))


def _pctl(values: list[float], p: float) -> float:
    """p-th percentile (0-100) via nearest-rank on the sorted list."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (p / 100.0) * (len(s) - 1)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] + (s[hi] - s[lo]) * frac


# --------------------------------------------------------------------------- #
# Mode: sim — analytic per-turn model
# --------------------------------------------------------------------------- #
def _sim_turn() -> dict[str, float]:
    """One simulated turn. Returns ttft_ms + turn_ms + the stage breakdown."""
    endpoint = _endpoint_delay_ms()
    # VAD/Smart-Turn add a tiny per-decision overhead but Smart Turn can SHORTEN
    # the effective wait on a clean stop (it confirms the endpoint immediately
    # instead of always burning the full silence window). Model that small win.
    vad = VAD_OVERHEAD_MS if (_vad_enabled() or _smart_turn_enabled()) else 0.0
    if _smart_turn_enabled():
        endpoint *= 0.9  # semantic endpoint trims ~10% off the silence wait on clean stops

    stt = _jit(STT_MS)
    llm = _jit(LLM_MS)
    tts_first = _jit(TTS_FIRST_MS)
    tts_rest = _jit(TTS_REST_MS)

    # TTFT = wait-out-silence + VAD + STT + LLM + first-sentence synth.
    ttft = endpoint + vad + stt + llm + tts_first
    # Full turn ≈ TTFT + speaking the rest (rest synth overlaps playback in the
    # real streaming path; we add a conservative slice of it).
    turn = ttft + tts_rest * 0.6
    return {
        "ttft_ms": ttft,
        "turn_ms": turn,
        "endpoint_ms": endpoint,
        "stt_ms": stt,
        "llm_ms": llm,
        "tts_first_ms": tts_first,
    }


# --------------------------------------------------------------------------- #
# Mode: pipe — drive the real VoicePipeline (Mock providers) + simulated sleeps
# --------------------------------------------------------------------------- #
async def _pipe_turns(runs: int) -> list[dict[str, float]]:
    """Use the actual VoicePipeline in text mode with Mock providers, but wrap
    the providers so each stage sleeps a realistic amount — this measures the
    pipeline's own orchestration overhead on top of the modelled stage costs."""
    try:
        from app.voice_agent.pipeline import VoicePipeline
        from app.voice_agent.providers import MockLLM, MockSTT, MockTTS
    except Exception as e:
        print(f"[pipe mode unavailable: {e}] — falling back to sim mode.", file=sys.stderr)
        return [_sim_turn() for _ in range(runs)]

    class _SlowSTT(MockSTT):
        async def transcribe(self, audio: bytes, **kw) -> str:
            await asyncio.sleep(_jit(STT_MS) / 1000.0)
            return await super().transcribe(audio, **kw)

    class _SlowLLM(MockLLM):
        async def complete(self, messages, **kw) -> str:
            await asyncio.sleep(_jit(LLM_MS) / 1000.0)
            return await super().complete(messages, **kw)

    class _SlowTTS(MockTTS):
        async def synthesize(self, text: str, voice_id=None) -> bytes:
            # first short reply ~ TTS_FIRST; treat whole reply as one synth here.
            await asyncio.sleep(_jit(TTS_FIRST_MS) / 1000.0)
            return await super().synthesize(text, voice_id=voice_id)

    pipe = VoicePipeline(system_prompt="You are a brief sales agent.")
    # inject slow mocks
    pipe._stt = _SlowSTT()
    pipe._llm = _SlowLLM()
    pipe._tts = _SlowTTS()

    lines = [
        "haan boliye",
        "kitna kharcha aayega",
        "thoda mehenga lag raha hai",
        "site visit kab kar sakte hain",
    ]
    out: list[dict[str, float]] = []
    for i in range(runs):
        endpoint = _endpoint_delay_ms()
        if _smart_turn_enabled():
            endpoint *= 0.9
        # simulate the caller's trailing silence we must wait through
        await asyncio.sleep(endpoint / 1000.0)
        t0 = time.perf_counter()
        _reply, metrics = await pipe.run_turn(lines[i % len(lines)])
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        md = metrics.as_dict()
        # TTFT here = endpoint wait + stt + llm + first-sentence tts.
        ttft = endpoint + md.get("stt_ms", 0.0) + md.get("llm_ms", 0.0) + md.get("tts_ms", 0.0)
        out.append(
            {
                "ttft_ms": ttft,
                "turn_ms": endpoint + elapsed_ms,
                "endpoint_ms": endpoint,
                "stt_ms": md.get("stt_ms", 0.0),
                "llm_ms": md.get("llm_ms", 0.0),
                "tts_first_ms": md.get("tts_ms", 0.0),
            }
        )
        pipe.reset()
    return out


# --------------------------------------------------------------------------- #
def _summary(samples: list[dict[str, float]]) -> dict[str, float]:
    ttft = [s["ttft_ms"] for s in samples]
    turn = [s["turn_ms"] for s in samples]
    return {
        "runs": len(samples),
        "ttft_p50": _pctl(ttft, 50),
        "ttft_p95": _pctl(ttft, 95),
        "ttft_min": min(ttft) if ttft else 0.0,
        "ttft_max": max(ttft) if ttft else 0.0,
        "ttft_mean": statistics.fmean(ttft) if ttft else 0.0,
        "turn_p50": _pctl(turn, 50),
        "turn_p95": _pctl(turn, 95),
        "endpoint_ms": samples[0]["endpoint_ms"] if samples else 0.0,
        "avg_stt_ms": statistics.fmean([s["stt_ms"] for s in samples]) if samples else 0.0,
        "avg_llm_ms": statistics.fmean([s["llm_ms"] for s in samples]) if samples else 0.0,
        "avg_tts_first_ms": (
            statistics.fmean([s["tts_first_ms"] for s in samples]) if samples else 0.0
        ),
    }


def _verdict(ttft_p95: float) -> str:
    if ttft_p95 <= 800:
        return "EXCELLENT (<=800 ms p95 — human-feeling)"
    if ttft_p95 <= 1500:
        return "GOOD (<=1.5 s p95 — acceptable)"
    if ttft_p95 <= 2200:
        return "LAGGY (>1.5 s p95 — callers notice the gap)"
    return "POOR (>2.2 s p95 — feels broken, lower stage latencies / silence)"


def main() -> int:
    ap = argparse.ArgumentParser(description="Voice latency scorecard (FREE/offline).")
    ap.add_argument("--mode", choices=["sim", "pipe"], default="sim")
    ap.add_argument("--runs", type=int, default=30)
    ap.add_argument("--json", action="store_true", help="emit JSON only")
    args = ap.parse_args()

    if args.mode == "pipe":
        samples = asyncio.run(_pipe_turns(args.runs))
    else:
        samples = [_sim_turn() for _ in range(args.runs)]

    s = _summary(samples)

    if args.json:
        print(json.dumps({"mode": args.mode, **s, "verdict": _verdict(s["ttft_p95"])}, indent=2))
        return 0

    print("=" * 60)
    print(f" VOICE LATENCY SCORECARD  (mode={args.mode}, runs={s['runs']})")
    print("=" * 60)
    print(f" Endpoint (silence) wait : {s['endpoint_ms']:.0f} ms   [TURN_SILENCE_MS]")
    print(
        f" Silero VAD={'on' if _vad_enabled() else 'off'}   "
        f"Smart Turn={'on' if _smart_turn_enabled() else 'off'}"
    )
    print("-" * 60)
    print(" Per-stage (avg simulated free-stack):")
    print(f"   STT          : {s['avg_stt_ms']:.0f} ms")
    print(f"   LLM          : {s['avg_llm_ms']:.0f} ms")
    print(f"   TTS (1st sent): {s['avg_tts_first_ms']:.0f} ms")
    print("-" * 60)
    print(" TIME-TO-FIRST-AUDIO (TTFT) — the snappiness number:")
    print(f"   p50 : {s['ttft_p50']:.0f} ms")
    print(f"   p95 : {s['ttft_p95']:.0f} ms")
    print(f"   min/mean/max : {s['ttft_min']:.0f} / {s['ttft_mean']:.0f} / {s['ttft_max']:.0f} ms")
    print("-" * 60)
    print(" FULL TURN latency:")
    print(f"   p50 : {s['turn_p50']:.0f} ms")
    print(f"   p95 : {s['turn_p95']:.0f} ms")
    print("=" * 60)
    print(f" VERDICT : {_verdict(s['ttft_p95'])}")
    print("=" * 60)
    print(
        " Tip: re-run with TURN_SILENCE_MS=550 to A/B the snappier endpoint, and\n"
        "      USE_SMART_TURN=1 to model the semantic-endpoint trim. Lower stage\n"
        "      SCORE_*_MS envs to model a faster STT/LLM. Always confirm on the\n"
        "      FREE web-call (/app/test-call) before changing a paid-call config."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
