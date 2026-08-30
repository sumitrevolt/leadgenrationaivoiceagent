#!/usr/bin/env python3
"""OmniRoute latency probe — evidence for the OMNIROUTE_ENABLED=1 decision.

WHY THIS EXISTS
---------------
The OmniRoute gateway is live on 127.0.0.1:20128 with 3570 models, but the app
keeps it INERT because ``OMNIROUTE_ENABLED`` is unset. The last loop run in
progress.md lists "OWNER: OMNIROUTE_ENABLED=1 + OMNIROUTE_VOICE=1" as a pending
owner action — with no measured evidence either way.

The project's #1 open product complaint is voice latency:
    prod turn_metrics llm_first = 2189 / 6839 / 6334 ms   (target: p50 < 1000 ms)

This probe produces the numbers the owner needs to decide, without touching any
production flag. It is READ-ONLY with respect to app config.

WHAT IT MEASURES
----------------
TTFT (time to first token) over streaming /v1/chat/completions, because for a
voice agent TTFT is what the caller actually feels — total latency is not.

USAGE
-----
    python scripts/omniroute_latency_probe.py                 # defaults
    python scripts/omniroute_latency_probe.py --iters 5
    python scripts/omniroute_latency_probe.py --models leadgen-project-best,auto/best-fast

Exit codes: 0 = probe completed (even if some models failed), 2 = gateway unreachable.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request

DEFAULT_BASE = os.getenv("OMNIROUTE_BASE_URL", "http://127.0.0.1:20128/v1")
DEFAULT_MODELS = [
    "leadgen-project-best",  # the project's own 50-model flagship combo
    "leadgen-swara-flagship",  # voice path primary (per swara_live route)
    "auto/best-fast",  # gateway generic fast
    "auto/best-reasoning",  # gateway generic reasoning
]

# A realistic short voice-agent turn. Kept small so we measure routing/TTFT,
# not generation length.
PROMPT = "Customer: kitna charge karte ho? Reply in one short Hindi sentence."
SYSTEM = "You are Swara, a friendly Indian sales agent. Reply in 1 short sentence."


def _key() -> str:
    k = os.getenv("OMNIROUTE_API_KEY") or os.getenv("OMNIROUTE_MANAGEMENT_API_KEY", "")
    if not k:
        sys.stderr.write(
            "ERROR: neither OMNIROUTE_API_KEY nor OMNIROUTE_MANAGEMENT_API_KEY is set\n"
        )
        sys.exit(2)
    return k


def gateway_reachable(base: str, key: str) -> int | None:
    """Return model count, or None if unreachable."""
    try:
        req = urllib.request.Request(
            base.rstrip("/") + "/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return len(json.loads(r.read()).get("data", []))
    except Exception as e:  # noqa: BLE001 - probe reports, never crashes
        sys.stderr.write(f"gateway unreachable: {e}\n")
        return None


def probe_once(base: str, key: str, model: str, timeout: float) -> dict:
    """One streaming call. Returns timing dict, or {'error': ...}."""
    payload = {
        "model": model,
        "stream": True,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": PROMPT},
        ],
        "max_tokens": 120,
        "temperature": 0.4,
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
    )

    t0 = time.perf_counter()
    ttft = None
    chunks = 0
    text = ""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                if ttft is None:
                    ttft = (time.perf_counter() - t0) * 1000.0
                    chunks += 1
                    continue
                chunks += 1
                try:
                    d = json.loads(data)
                    for ch in d.get("choices", []):
                        delta = ch.get("delta") or {}
                        text += delta.get("content") or ""
                except json.JSONDecodeError:
                    pass
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read()[:200].decode('utf-8', 'replace')}"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}

    total = (time.perf_counter() - t0) * 1000.0
    return {
        "ttft_ms": round(ttft, 1) if ttft is not None else None,
        "total_ms": round(total, 1),
        "chunks": chunks,
        "chars": len(text),
        "preview": text.strip()[:90],
    }


def pct(vals: list[float], p: float) -> float:
    if not vals:
        return float("nan")
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def main() -> int:
    ap = argparse.ArgumentParser(description="OmniRoute TTFT latency probe")
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS))
    ap.add_argument("--iters", type=int, default=3, help="calls per model")
    ap.add_argument("--timeout", type=float, default=25.0)
    args = ap.parse_args()

    key = _key()
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    print("=" * 74)
    print("OMNIROUTE LATENCY PROBE  (voice TTFT evidence)")
    print("=" * 74)
    print(f"gateway : {args.base}")
    print(f"iters   : {args.iters} per model")
    print("target  : TTFT p50 < 1000 ms   (prod baseline llm_first was 2189/6839/6334 ms)")
    print()

    count = gateway_reachable(args.base, key)
    if count is None:
        print("RESULT: gateway UNREACHABLE — cannot probe.")
        return 2
    print(f"gateway reachable — {count} models advertised\n")

    results: dict[str, list[dict]] = {}
    for model in models:
        runs = []
        for i in range(args.iters):
            r = probe_once(args.base, key, model, args.timeout)
            runs.append(r)
            if "error" in r:
                print(f"  [{model}] iter {i + 1}: ERROR {r['error'][:70]}")
            else:
                print(
                    f"  [{model}] iter {i + 1}: TTFT {r['ttft_ms']} ms | total {r['total_ms']} ms"
                )
        results[model] = runs
        print()

    print("=" * 74)
    print("SUMMARY (TTFT milliseconds)")
    print("=" * 74)
    print(f"{'model':<28}{'ok':>4}{'p50':>10}{'p90':>10}{'min':>10}{'max':>10}{'avg total':>12}")
    print("-" * 74)

    best = None
    for model, runs in results.items():
        ok = [r for r in runs if r.get("ttft_ms") is not None]
        if not ok:
            print(
                f"{model:<28}{'0/' + str(len(runs)):>4}{'—':>10}{'—':>10}{'—':>10}{'—':>10}{'—':>12}"
            )
            continue
        tt = [r["ttft_ms"] for r in ok]
        tot = [r["total_ms"] for r in ok]
        p50 = pct(tt, 0.50)
        print(
            f"{model:<28}{str(len(ok)) + '/' + str(len(runs)):>4}"
            f"{p50:>10.0f}{pct(tt, 0.90):>10.0f}{min(tt):>10.0f}{max(tt):>10.0f}"
            f"{statistics.mean(tot):>12.0f}"
        )
        if best is None or p50 < best[1]:
            best = (model, p50)

    print("-" * 74)
    if best:
        verdict = "MEETS target (<1000ms)" if best[1] < 1000 else "MISSES target (>=1000ms)"
        print(f"\nFastest: {best[0]} @ p50 {best[1]:.0f} ms — {verdict}")
        if best[1] < 2189:
            print(f"vs prod baseline p50-ish 2189 ms -> {2189 - best[1]:.0f} ms faster")
    print("\nNOTE: probe is READ-ONLY. No app flag was changed.")
    print("Flipping OMNIROUTE_ENABLED=1 is a separate, owner-approved decision.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
