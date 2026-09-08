"""
Per-turn latency metrics for the voice agent (P1 observability).
=================================================================

"Jo measure nahi kar sakte, woh tune nahi kar sakte." Every voice path
(vobiz_stream / phone_stream / pipeline web-call) can stamp a per-turn latency
dict — ``stt_ms``, ``llm_first_ms``, ``tts_first_ms``, ``turn_ms`` (plus any
other ``*_ms`` key) — and hand it here. We:

  * append it as ONE JSON line to ``data/turn_metrics/YYYY-MM-DD.jsonl`` so the
    numbers survive the call and can be rolled up across calls;
  * compute P50/P95/avg/max over ANY ``*_ms`` key via :func:`rollup`, so this
    works for the existing pipeline shape (``total_ms``) AND the stream shape
    (``turn_ms``) without coupling.

Design (matches the rest of the project): import-safe, never raises, and pure
log/measurement — it changes NO call behaviour. Gated by ``TURN_METRICS``
(default ON; set ``TURN_METRICS=0`` to silence the disk writes). Timing uses
``perf_counter`` (monotonic) so it is immune to wall-clock jumps.

Usage (stream path):
    from app.voice_agent.turn_metrics import now_ms, record_turn, rollup

    t0 = now_ms()
    ...                                  # STT / LLM / TTS
    record_turn({
        "path": "vobiz_stream", "niche": niche, "outcome": "ok",
        "stt_ms": stt_ms, "llm_first_ms": llm_first_ms,
        "tts_first_ms": tts_first_ms, "turn_ms": now_ms() - t0,
    })
"""

from __future__ import annotations

import json
import math
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Default location for the daily per-turn metric files (gitignored data/).
DEFAULT_BASE_DIR = os.path.join("data", "turn_metrics")

# Latency keys we know how to roll up. rollup() also auto-discovers any other
# numeric key ending in "_ms", so adding a new metric needs no change here.
KNOWN_MS_KEYS = (
    "stt_ms",
    "stt_final_ms",
    "llm_start_ms",
    "route_select_ms",
    "llm_first_ms",
    "llm_ms",
    "tts_start_ms",
    "tts_first_ms",
    "first_audio_ms",
    "tts_ms",
    "turn_ms",
    "total_ms",
)


@dataclass
class TurnStampBuilder:
    """Structured per-turn stamps relative to speech_end (monotonic ms).

    No secrets or transcript text — ids + numeric stamps only.
    """

    turn_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    generation_id: str | None = None
    speech_end_ms: float = 0.0
    stamps: dict[str, float] = field(default_factory=dict)
    cancelled: bool = False
    interrupted: bool = False
    omniroute_model: str | None = None

    def __post_init__(self) -> None:
        self.stamps.setdefault("speech_end", 0.0)

    def stamp(self, key: str, *, at_ms: float | None = None) -> None:
        """Record a named event relative to speech_end anchor."""
        if key == "speech_end":
            self.stamps[key] = 0.0
            return
        rel = at_ms if at_ms is not None else (now_ms() - self.speech_end_ms)
        self.stamps[key] = round(max(0.0, rel), 1)

    def gap(self, start_key: str, end_key: str) -> float | None:
        a = self.stamps.get(start_key)
        b = self.stamps.get(end_key)
        if _is_number(a) and _is_number(b):
            return round(float(b) - float(a), 1)
        return None

    def build(self, **extra: Any) -> dict[str, Any]:
        rec: dict[str, Any] = {
            "turn_id": self.turn_id,
            "speech_end_ms": 0.0,
        }
        if self.generation_id:
            rec["generation_id"] = self.generation_id
        if self.cancelled:
            rec["cancelled"] = True
        if self.interrupted:
            rec["interrupted"] = True
        if self.omniroute_model:
            rec["omniroute_model"] = self.omniroute_model
        for k, v in self.stamps.items():
            if k == "speech_end":
                continue
            rec[k] = v
        # Derived gaps (ms) — rollup-friendly *_ms keys.
        gap_map = {
            "stt_final_ms": ("speech_end", "stt_final"),
            "llm_start_ms": ("speech_end", "llm_request_started"),
            "route_select_ms": ("llm_request_started", "omniroute_route_selected"),
            "llm_first_ms": ("speech_end", "llm_first_token"),
            "tts_start_ms": ("speech_end", "tts_started"),
            "first_audio_ms": ("speech_end", "first_audio"),
        }
        for out_key, (a, b) in gap_map.items():
            g = self.gap(a, b)
            if g is not None:
                rec[out_key] = g
        rec.update({k: v for k, v in extra.items() if v is not None})
        return rec


def now_ms() -> float:
    """Monotonic millisecond clock for measuring durations (NOT wall-clock)."""
    return time.perf_counter() * 1000.0


def enabled() -> bool:
    """True unless TURN_METRICS is explicitly disabled. Default ON because this
    is pure measurement (no behaviour change) and being blind is the bigger risk."""
    return (os.environ.get("TURN_METRICS", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _is_number(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool) and not _is_nan(v)


def _is_nan(v: Any) -> bool:
    try:
        return isinstance(v, float) and math.isnan(v)
    except Exception:
        return False


def percentile(values: Iterable[float], p: float) -> float | None:
    """Linear-interpolation percentile (numpy-style). ``p`` in [0, 100].
    Returns None for an empty input. Never raises."""
    try:
        xs = sorted(float(v) for v in values if _is_number(v))
    except Exception:
        return None
    if not xs:
        return None
    if len(xs) == 1:
        return round(xs[0], 1)
    k = (len(xs) - 1) * (max(0.0, min(100.0, p)) / 100.0)
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return round(xs[int(k)], 1)
    val = xs[lo] + (xs[hi] - xs[lo]) * (k - lo)
    return round(val, 1)


def rollup(records: Iterable[dict]) -> dict:
    """Aggregate P50/P95/avg/max/n for every ``*_ms`` key found across records.

    Returns ``{"count": N, "metrics": {key: {p50, p95, avg, max, n}}}``. Only
    keys with at least one numeric value appear. Never raises."""
    try:
        recs = [r for r in records if isinstance(r, dict)]
    except Exception:
        recs = []
    buckets: dict[str, list[float]] = {}
    for r in recs:
        for key, val in r.items():
            if not (isinstance(key, str) and key.endswith("_ms")):
                continue
            if _is_number(val):
                buckets.setdefault(key, []).append(float(val))
    metrics: dict[str, dict] = {}
    for key, vals in buckets.items():
        if not vals:
            continue
        metrics[key] = {
            "p50": percentile(vals, 50),
            "p95": percentile(vals, 95),
            "avg": round(sum(vals) / len(vals), 1),
            "max": round(max(vals), 1),
            "n": len(vals),
        }
    # Stable order: known keys first (in declared order), then any extras sorted.
    ordered = {k: metrics[k] for k in KNOWN_MS_KEYS if k in metrics}
    for k in sorted(metrics):
        if k not in ordered:
            ordered[k] = metrics[k]
    return {"count": len(recs), "metrics": ordered}


def _clean_record(rec: dict) -> dict:
    """Drop None values + ensure a ts; keep it JSON-serialisable + small."""
    out: dict[str, Any] = {}
    if "ts" not in rec:
        out["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for k, v in rec.items():
        if v is None:
            continue
        if _is_number(v):
            out[k] = round(float(v), 1) if isinstance(v, float) else v
        elif isinstance(v, str | bool | int):
            out[k] = v
        else:
            out[k] = str(v)
    return out


def record_turn(rec: dict, *, base_dir: str | None = None) -> bool:
    """Append one per-turn metric line to ``{base_dir}/YYYY-MM-DD.jsonl``.

    Gated by :func:`enabled` (TURN_METRICS). Best-effort / never raises — a
    persist failure must never break a live call. Returns True if written."""
    if not enabled():
        return False
    if not isinstance(rec, dict) or not rec:
        return False
    try:
        clean = _clean_record(rec)
        out_dir = base_dir or DEFAULT_BASE_DIR
        os.makedirs(out_dir, exist_ok=True)
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = os.path.join(out_dir, day + ".jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(clean, ensure_ascii=False) + "\n")
        return True
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"turn_metrics: record failed ({e}).")
        return False


def load_day(date_str: str | None = None, *, base_dir: str | None = None) -> list[dict]:
    """Read all per-turn metric records for a day (UTC). Never raises."""
    out: list[dict] = []
    try:
        out_dir = base_dir or DEFAULT_BASE_DIR
        day = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = os.path.join(out_dir, day + ".jsonl")
        if not os.path.exists(path):
            return out
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"turn_metrics: load failed ({e}).")
    return out


def summarize_day(date_str: str | None = None, *, base_dir: str | None = None) -> dict:
    """Rollup (P50/P95/...) over a whole day's turns. For ops/CLI/dashboards."""
    return rollup(load_day(date_str, base_dir=base_dir))


__all__ = [
    "now_ms",
    "enabled",
    "percentile",
    "rollup",
    "record_turn",
    "load_day",
    "summarize_day",
    "TurnStampBuilder",
    "DEFAULT_BASE_DIR",
    "KNOWN_MS_KEYS",
]
