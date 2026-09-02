"""
Voice Self-Test (built-in) — one on-demand health + quality scorecard for Swara.
================================================================================

Project me voice-QA ke alag-alag engines already the, par sab sirf NIGHTLY (Arjun,
``VOICE_EVAL_AUTO``) ya MANUAL CLI se chalte the — koi ek "abhi chala ke dekho"
self-test nahi tha. Yeh module wahi GAP bharta hai: ek hi call me poora voice
stack apne aap ko test karta hai aur ek structured scorecard deta hai.

Compose karta hai (rebuild NAHI — wire-not-build):
  * personas — ``eval_suite.run_suite`` (brain=None, rule-based = FREE + deterministic,
    no network): conversation-logic regression (double/repeat/pushy/goodbye/outcome).
  * stack    — live AI-stack probes jo isse ek *voice* test banate hain, na ki sirf
    logic test: TTS (EdgeTTS synth → bytes>0), STT (free_stt provider availability),
    LLM (free_ai ek chhota ping — OPT-IN, free-tier ceiling bachane ke liye).
  * live     — ``live_eval.eval_recent_calls`` (local transcripts, no network):
    pichhli REAL calls ki quality + D-13 qa_checks findings.

Safety (3 prod-down lessons ka respect):
  * Har network-probe OFF-LOOP / bounded (``asyncio.wait_for`` async ke liye,
    ``asyncio.to_thread`` blocking model-load ke liye) — ek dead provider bhi
    request ko hang na kare.
  * Import-safe (lazy imports), KABHI raise nahi karta — har component apna
    ``ok``/``error`` deta hai. Hard deadline har probe pe + caller pe.
  * Read-only, koi side-effect nahi (eval_gate recording sirf jab live_eval
    khud apne ``EVAL_GATE`` flag pe ON ho).

Run (no keys needed — personas + stack TTS/STT, LLM off):
    python -m app.voice_agent.self_test
    python -m app.voice_agent.self_test --llm        # LLM ping bhi (free-tier kharcha)
or import:
    from app.voice_agent.self_test import run_voice_self_test
    report = await run_voice_self_test(personas=True, stack=True, live=True, llm=False)
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)


_TTS_PROBE_LINE = "Namaste, main Swara bol rahi hoon. Yeh ek self-test hai."
_TTS_VOICE = "hi-IN-SwaraNeural"


# --------------------------------------------------------------------------- #
# Component 1 — persona conversation suite (free, deterministic, no network)
# --------------------------------------------------------------------------- #
async def _run_personas(niche: str, deadline_s: float) -> dict[str, Any]:
    """eval_suite ko brain=None (rule-based) factory ke saath chalao. Pure logic —
    no LLM/network. Returns pass_rate + by_persona + failing-persona notes."""
    t0 = time.time()
    try:
        from app.voice_agent.eval_suite import run_suite
        from app.voice_agent.natural_dialog import NaturalDialogManager

        def _factory():
            # brain=None + use_llm_fallback=False intent → GENUINELY network-free:
            # warna NaturalDialogManager ek live-LLM IntentDetector banata hai jo har
            # turn Gemini call karta (flaky + slow → nightly Arjun isiliye 300s budget
            # rakhta). On-demand self-test ko fast + free + deterministic rakhna hai.
            intent = None
            try:
                from app.voice_agent.intent_detector import IntentDetector

                intent = IntentDetector(use_llm_fallback=False)
            except Exception:  # pragma: no cover - import fail → __init__ rule-based fallback
                intent = None
            return NaturalDialogManager(niche=niche, brain=None, intent_detector=intent)

        report = await asyncio.wait_for(run_suite(_factory), timeout=deadline_s)
        failing = [
            {"persona": r.persona, "outcome": r.outcome, "notes": r.notes}
            for r in report.runs
            if not r.passed
        ]
        return {
            "ok": report.pass_rate >= 0.7,
            "pass_rate": round(report.pass_rate, 3),
            "passed": report.passed,
            "failed": report.failed,
            "by_persona": dict(report.by_persona),
            "failing": failing,
            "ms": int((time.time() - t0) * 1000),
        }
    except TimeoutError:
        return {"ok": False, "error": "timeout", "ms": int((time.time() - t0) * 1000)}
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("self_test personas error: %s", exc)
        return {"ok": False, "error": repr(exc)[:200], "ms": int((time.time() - t0) * 1000)}


# --------------------------------------------------------------------------- #
# Component 2 — live AI-stack probes (network → each bounded + graceful)
# --------------------------------------------------------------------------- #
async def _probe_tts(deadline_s: float) -> dict[str, Any]:
    """EdgeTTS se ek Hindi line synth karke audio-bytes gino. EdgeTTS async hai
    (loop block nahi karta) — wait_for hi kaafi bound hai. Key nahi chahiye."""
    t0 = time.time()
    try:
        import edge_tts

        async def _synth() -> int:
            comm = edge_tts.Communicate(_TTS_PROBE_LINE, _TTS_VOICE)
            total = 0
            async for ch in comm.stream():
                if ch.get("type") == "audio":
                    total += len(ch.get("data") or b"")
            return total

        nbytes = await asyncio.wait_for(_synth(), timeout=deadline_s)
        return {
            "ok": nbytes > 0,
            "audio_bytes": nbytes,
            "voice": _TTS_VOICE,
            "ms": int((time.time() - t0) * 1000),
        }
    except TimeoutError:
        return {"ok": False, "error": "timeout", "ms": int((time.time() - t0) * 1000)}
    except Exception as exc:
        logger.debug("self_test tts probe error: %s", exc)
        return {"ok": False, "error": repr(exc)[:200], "ms": int((time.time() - t0) * 1000)}


async def _probe_stt(deadline_s: float) -> dict[str, Any]:
    """STT manager construct ho jaata hai aur kaun-se providers available hain —
    yahi probe (actual transcribe ke liye audio chahiye, isliye sirf availability).
    Manager-init blocking model-load kar sakta → to_thread me wrap."""
    t0 = time.time()
    try:
        from app.voice_agent.free_stt import get_free_stt

        mgr = await asyncio.wait_for(get_free_stt(), timeout=deadline_s)
        providers: list[str] = []
        for attr in ("providers", "available_providers", "_providers", "chain"):
            val = getattr(mgr, attr, None)
            if isinstance(val, (list, tuple)) and val:
                providers = [str(p) for p in val][:12]
                break
        return {
            "ok": mgr is not None,
            "manager": type(mgr).__name__ if mgr is not None else None,
            "providers": providers,
            "ms": int((time.time() - t0) * 1000),
        }
    except TimeoutError:
        return {"ok": False, "error": "timeout", "ms": int((time.time() - t0) * 1000)}
    except Exception as exc:
        logger.debug("self_test stt probe error: %s", exc)
        return {"ok": False, "error": repr(exc)[:200], "ms": int((time.time() - t0) * 1000)}


async def _probe_llm(deadline_s: float) -> dict[str, Any]:
    """free_ai chain ko ek chhota ping bhejo (max_tokens chhota). OPT-IN — har run
    free-tier ka ek token jalaata hai, isliye default OFF."""
    t0 = time.time()
    try:
        from app.voice_agent.free_ai import chat

        text, provider = await asyncio.wait_for(
            chat(
                "Reply with the single word: pong.",
                [{"role": "user", "content": "ping"}],
                max_tokens=8,
                temperature=0.0,
                profile="realtime",
            ),
            timeout=deadline_s,
        )
        ok = bool((text or "").strip())
        return {
            "ok": ok,
            "provider": provider or None,
            "sample": (text or "").strip()[:80],
            "ms": int((time.time() - t0) * 1000),
        }
    except TimeoutError:
        return {"ok": False, "error": "timeout", "ms": int((time.time() - t0) * 1000)}
    except Exception as exc:
        logger.debug("self_test llm probe error: %s", exc)
        return {"ok": False, "error": repr(exc)[:200], "ms": int((time.time() - t0) * 1000)}


async def _run_stack(llm: bool, deadline_s: float) -> dict[str, Any]:
    """TTS + STT (+ optional LLM) probes — concurrently, har ek apne bound ke saath."""
    tasks = {"tts": _probe_tts(deadline_s), "stt": _probe_stt(deadline_s)}
    if llm:
        tasks["llm"] = _probe_llm(deadline_s)
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    out: dict[str, Any] = {}
    for key, res in zip(tasks.keys(), results):
        if isinstance(res, Exception):
            out[key] = {"ok": False, "error": repr(res)[:200]}
        else:
            out[key] = res
    probed = [v for v in out.values() if isinstance(v, dict)]
    out["ok"] = bool(probed) and all(v.get("ok") for v in probed)
    return out


# --------------------------------------------------------------------------- #
# Component 3 — recent LIVE-call quality (local jsonl, no network)
# --------------------------------------------------------------------------- #
async def _run_live(n: int, deadline_s: float) -> dict[str, Any]:
    """live_eval se pichhli N real calls score karo (deterministic, no network)."""
    t0 = time.time()
    try:
        from app.agents import live_eval

        res = await asyncio.wait_for(
            asyncio.to_thread(live_eval.eval_recent_calls, n), timeout=deadline_s
        )
        n_calls = int(res.get("n") or 0)
        return {
            "ok": True,
            "calls_scored": n_calls,
            "mean_score": res.get("mean_score"),
            "total_qa_findings": res.get("total_qa_findings"),
            "gate_decision": (res.get("gate") or {}).get("decision"),
            "has_data": n_calls > 0,
            "ms": int((time.time() - t0) * 1000),
        }
    except TimeoutError:
        return {
            "ok": True,
            "error": "timeout",
            "has_data": False,
            "ms": int((time.time() - t0) * 1000),
        }
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("self_test live error: %s", exc)
        return {
            "ok": True,
            "error": repr(exc)[:200],
            "has_data": False,
            "ms": int((time.time() - t0) * 1000),
        }


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
def _verdict(report: dict[str, Any]) -> tuple[float, str]:
    """Weighted overall score (0..1) over the components that actually ran, +
    a status string. Components jo run hi nahi hue, weight se bahar."""
    parts: list[tuple[float, float]] = []  # (weight, score)
    personas = report.get("personas")
    if isinstance(personas, dict) and "pass_rate" in personas:
        parts.append((0.5, float(personas.get("pass_rate") or 0.0)))
    stack = report.get("stack")
    if isinstance(stack, dict):
        probed = [v for k, v in stack.items() if isinstance(v, dict) and k != "ok"]
        if probed:
            ok_frac = sum(1 for v in probed if v.get("ok")) / len(probed)
            parts.append((0.3, ok_frac))
    live = report.get("live")
    if isinstance(live, dict) and live.get("has_data") and live.get("mean_score") is not None:
        parts.append((0.2, float(live.get("mean_score") or 0.0)))

    if not parts:
        return 0.0, "fail"
    total_w = sum(w for w, _ in parts)
    score = round(sum(w * s for w, s in parts) / total_w, 3) if total_w else 0.0
    if score >= 0.85:
        status = "ok"
    elif score >= 0.6:
        status = "degraded"
    else:
        status = "fail"
    return score, status


async def run_voice_self_test(
    *,
    personas: bool = True,
    stack: bool = True,
    live: bool = True,
    llm: bool = False,
    niche: str = "solar",
    live_n: int = 5,
    deadline_s: float = 60.0,
) -> dict[str, Any]:
    """Built-in voice self-test — ek scorecard.

    Args:
        personas: rule-based persona conversation suite chalao (free, deterministic).
        stack:    live TTS/STT probes (LLM tab jab ``llm=True``).
        live:     pichhli ``live_n`` real calls ki quality (local transcripts).
        llm:      LLM ping probe (OPT-IN — free-tier token jalaata hai).
        niche:    persona suite kis niche pe (default ``solar``).
        deadline_s: per-component hard deadline (seconds).

    Returns:
        ``{ok, score, status, personas, stack, live, ms}`` — KABHI raise nahi karta.
    """
    t0 = time.time()
    report: dict[str, Any] = {}
    if personas:
        report["personas"] = await _run_personas(niche, deadline_s)
    if stack:
        report["stack"] = await _run_stack(llm, deadline_s)
    if live:
        report["live"] = await _run_live(live_n, deadline_s)

    score, status = _verdict(report)
    report["score"] = score
    report["status"] = status
    report["ok"] = status != "fail"
    report["ms"] = int((time.time() - t0) * 1000)
    return report


# --------------------------------------------------------------------------- #
# CLI — python -m app.voice_agent.self_test [--llm] [--niche solar]
# --------------------------------------------------------------------------- #
async def _main(argv: list[str]) -> int:
    llm = "--llm" in argv
    niche = "solar"
    if "--niche" in argv:
        try:
            niche = argv[argv.index("--niche") + 1]
        except Exception:
            pass

    rep = await run_voice_self_test(personas=True, stack=True, live=True, llm=llm, niche=niche)

    print("=" * 64)
    print(f" VOICE SELF-TEST — niche={niche}  llm={'on' if llm else 'off'}")
    print("=" * 64)
    p = rep.get("personas") or {}
    if p:
        print(
            f" personas : {'OK ' if p.get('ok') else 'BAD'}  "
            f"pass_rate={p.get('pass_rate')}  ({p.get('passed')}/{(p.get('passed') or 0) + (p.get('failed') or 0)})"
            + (f"  error={p.get('error')}" if p.get("error") else "")
        )
        for f in p.get("failing") or []:
            print(f"            - FAIL {f.get('persona')}: {f.get('notes')}")
    s = rep.get("stack") or {}
    if s:
        for key in ("tts", "stt", "llm"):
            v = s.get(key)
            if isinstance(v, dict):
                extra = (
                    v.get("audio_bytes")
                    or v.get("provider")
                    or v.get("manager")
                    or v.get("error")
                    or ""
                )
                print(
                    f" {key:<8} : {'OK ' if v.get('ok') else 'BAD'}  {extra}  ({v.get('ms', '?')}ms)"
                )
    lv = rep.get("live") or {}
    if lv:
        print(
            f" live     : {lv.get('calls_scored', 0)} calls scored  "
            f"mean={lv.get('mean_score')}  findings={lv.get('total_qa_findings')}  "
            f"gate={lv.get('gate_decision')}"
        )
    print("-" * 64)
    print(
        f" SCORE={rep.get('score')}  STATUS={str(rep.get('status')).upper()}  ({rep.get('ms')}ms)"
    )
    print("=" * 64)
    return 0 if rep.get("ok") else 1


if __name__ == "__main__":  # pragma: no cover
    import sys

    raise SystemExit(asyncio.run(_main(sys.argv[1:])))


__all__ = ["run_voice_self_test"]
