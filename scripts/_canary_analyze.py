"""Analyze latest call transcript + turn_metrics on prod."""

import json
import statistics
import sys
from pathlib import Path


def p50_p95(vals: list[float]) -> tuple[float | None, float | None]:
    if not vals:
        return None, None
    s = sorted(vals)
    n = len(s)
    p50 = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    p95_idx = min(n - 1, int(n * 0.95))
    return round(p50, 1), round(s[p95_idx], 1)


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def main() -> None:
    today = "2026-07-18"
    tpath = Path(f"/opt/leadgen/data/call_transcripts/{today}.jsonl")
    mpath = Path(f"/opt/leadgen/data/turn_metrics/{today}.jsonl")

    transcripts = load_jsonl(tpath)
    if not transcripts:
        print("NO_TRANSCRIPT", tpath)
        sys.exit(1)

    d = transcripts[-1]
    print("=== TRANSCRIPT ===")
    print("stream_sid", (d.get("stream_sid") or "")[:36])
    print("duration_s", d.get("duration_s"))
    print("app_version", d.get("app_version"))
    print("user_turns", d.get("user_turns"))
    print("barge_count", d.get("barge_count"))

    tr = (d.get("turn_rollup") or {}).get("metrics") or {}
    for k in ("stt_ms", "llm_first_ms", "tts_first_ms", "turn_ms", "first_audio_ms"):
        m = tr.get(k) or {}
        print(f"{k}_p50", m.get("p50"), f"{k}_p95", m.get("p95"), f"{k}_n", m.get("n"))

    metrics = load_jsonl(mpath)
    if metrics:
        # last N records from this stream_sid if possible
        sid = d.get("stream_sid")
        recs = [r for r in metrics if r.get("stream_sid") == sid] or metrics[-20:]
        fields = ["stt_ms", "llm_first_ms", "tts_first_ms", "turn_ms", "first_audio_ms"]
        print("=== TURN_METRICS JSONL ===")
        print("records", len(recs))
        for f in fields:
            vals = [float(r[f]) for r in recs if r.get(f) is not None]
            p50, p95 = p50_p95(vals)
            print(f"{f}_p50", p50, f"{f}_p95", p95, "n", len(vals))

    msgs = d.get("messages") or []
    print("=== LAST MSGS ===")
    for m in msgs[-10:]:
        print(m.get("role"), ":", (m.get("content") or "")[:120])

    tm = d.get("turn_metrics") or []
    if tm:
        routes = [
            r.get("llm_route") or r.get("route") for r in tm if r.get("llm_route") or r.get("route")
        ]
        print("llm_routes", routes[:10])


if __name__ == "__main__":
    main()
