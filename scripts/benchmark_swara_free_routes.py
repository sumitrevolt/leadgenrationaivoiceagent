"""Benchmark free voice LLM routes (direct providers — OmniRoute optional).

Runs sanitized Hindi/Hinglish enterprise-sales prompts against connected free
providers. Writes JSONL evidence to data/voice_route_benchmarks/.

Usage:
  .venv\\Scripts\\python.exe scripts/benchmark_swara_free_routes.py
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

SCENARIOS = [
    ("pricing_main", "Hamara AI marketing plan kitne ka hai? Main wala."),
    ("pricing_combo", "Advanced ya combo plan ka price batao."),
    ("objection_busy", "Abhi busy hoon, baad me call karna."),
    ("objection_price", "2000 me kya milta hai, mehnga lag raha."),
    ("memory_name", "Mera naam Ravi hai. Pehle bola tha marketing chahiye."),
    ("identity", "Tum kaun ho? Company ka naam kya hai?"),
    ("opt_out", "Call mat karna, mera number list se hata do."),
    ("unclear_stt", "Aam shabd Aam shabd"),
    ("features", "WhatsApp aur Google pe post automatic hota hai kya?"),
    ("callback", "Kal subah 11 baje callback kar dena."),
    ("interrupt", "Haan... wait, Instagram pe bhi?"),
    ("hinglish_mix", "Yaar leads nahi aa rahe, kuch organic growth chahiye."),
    ("voice_product", "Alag se AI calling agent bhi hai kya, kitna?"),
    ("competitor", "Local agency 1500 me kar deti hai, tum alag kaise?"),
    ("close_signal", "Theek hai, aaj hi start karwa do."),
    ("service_scope", "Sirf salon ke liye hai ya kisi bhi local business?"),
    ("gst_invoice", "Invoice GST ke saath milega?"),
    ("recording_consent", "Call record ho rahi hai kya?"),
    ("language_switch", "Can you explain in simple Hindi please?"),
    ("hallucination_trap", "Tumne kaha tha free lifetime plan hai na?"),
]

SYSTEM = (
    "You are Swara, AI assistant for LeadsGen AI. Short Hindi/Hinglish. "
    "One question max. Pricing: Main ₹1999/mo, Combo/Advanced ₹5999/mo. "
    "Voice standalone ₹4999/9999/19999. Never invent prices. No markdown."
)


async def _one(provider: str, model: str, user: str) -> dict:
    from app.voice_agent import free_ai

    t0 = time.perf_counter()
    try:
        text, p = await free_ai.chat_provider(
            provider,
            model,
            SYSTEM,
            [{"role": "user", "content": user}],
            max_tokens=90,
            temperature=0.4,
            scope="voice_bench",
            timeout_s=12.0,
        )
        ms = int((time.perf_counter() - t0) * 1000)
        return {
            "provider": provider,
            "model": model,
            "ok": bool(text),
            "latency_ms": ms,
            "text": (text or "")[:240],
            "resolved": p,
        }
    except Exception as e:
        return {
            "provider": provider,
            "model": model,
            "ok": False,
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "error": type(e).__name__,
            "text": "",
        }


def _score(text: str, key: str) -> dict:
    t = (text or "").lower()
    return {
        "has_rupee_or_plan": ("₹" in (text or "") or "1999" in t or "5999" in t or "plan" in t),
        "opener_like": ("namaste" in t and "swara" in t and "baat kar" in t),
        "markdown": any(c in (text or "") for c in ("**", "##", "`")),
        "multi_q": (text or "").count("?") > 1,
        "scenario": key,
    }


async def main() -> None:
    routes = [
        ("gemini", (os.environ.get("VOICE_LLM_MODEL") or "gemini-2.5-flash").strip()),
        ("groq", (os.environ.get("VOICE_GROQ_MODEL") or "llama-3.1-8b-instant").strip()),
        ("cerebras", (os.environ.get("VOICE_CEREBRAS_MODEL") or "gpt-oss-120b").strip()),
        ("nvidia", (os.environ.get("NVIDIA_LLM_MODEL") or "meta/llama-3.1-8b-instruct").strip()),
    ]
    out_dir = Path("data") / "voice_route_benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"bench_{stamp}.jsonl"

    rows = []
    for provider, model in routes:
        for key, utt in SCENARIOS:
            row = await _one(provider, model, utt)
            row["scenario"] = key
            row["scores"] = _score(row.get("text") or "", key)
            rows.append(row)
            print(f"{provider}/{model} {key}: ok={row.get('ok')} {row.get('latency_ms')}ms")

    with out_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Summary table
    print("\n=== SUMMARY ===")
    for provider, model in routes:
        subset = [r for r in rows if r["provider"] == provider]
        oks = sum(1 for r in subset if r.get("ok"))
        lats = [r["latency_ms"] for r in subset if r.get("ok")]
        p50 = sorted(lats)[len(lats) // 2] if lats else None
        invent = sum(1 for r in subset if r.get("scores", {}).get("opener_like"))
        print(f"{provider}/{model}: {oks}/{len(subset)} ok, p50={p50}ms, opener_like={invent}")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    asyncio.run(main())
