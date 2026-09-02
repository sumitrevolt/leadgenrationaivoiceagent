"""Agent trajectory learning — Ruflo SONA "learn from successful traces" parity.

Idea (free-stack): har agent-run ka pura trace (action + steps + outcome + reward)
record karo. Jo runs ACTUALLY chale (high reward) unhe replay-hint me ground karke
future runs ko unke jaisa bias do, aur saare winning traces ko ek training-dataset
ke roop me export karo (local ML brains fine-tune karne ke liye — Hermes/Ruflo
trajectory export pattern).

Design (project patterns):
  - `enabled()` sirf AUTOMATIC trajectory-grounding ko gate karta — default OFF =
    zero behaviour change. Saare helper (record/best/replay/export) khud hamesha
    safe-callable hain (admin endpoint + tests ke liye).
  - Store = data/agent_trajectories.jsonl (append-only, JSONL — self_improve jaisa).
  - Export default → data/exports/trajectories_dataset.jsonl.
  - Kabhi raise nahi karta — koi error / file missing / corrupt line → graceful skip.

Flag: TRAJECTORY_LEARN=1
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STORE = os.path.join("data", "agent_trajectories.jsonl")
_DEFAULT_EXPORT = os.path.join("data", "exports", "trajectories_dataset.jsonl")

_HINT_STEP_CAP = 240  # ek step ka char-cap replay-hint me


def enabled() -> bool:
    """Gates AUTOMATIC trajectory grounding. Helper functions flag-independent."""
    return (os.getenv("TRAJECTORY_LEARN") or "").strip().lower() in ("1", "true", "yes")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return rows


def _append(path: str, rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def record_trajectory(
    action: str,
    steps: list[dict],
    outcome: str,
    reward: float = 0.0,
    meta: dict | None = None,
) -> str:
    """Ek pura agent-run trace record karo → data/agent_trajectories.jsonl.

    Returns trace id (empty string sirf agar action khali ho). Never raises.
    """
    act = (action or "").strip()
    if not act:
        return ""
    tid = uuid.uuid4().hex[:12]
    try:
        r = float(reward or 0.0)
    except Exception:
        r = 0.0
    rec = {
        "id": tid,
        "action": act[:200],
        "steps": list(steps or []),
        "outcome": (outcome or "")[:2000],
        "reward": r,
        "meta": dict(meta or {}),
        "at": _now().isoformat(),
    }
    _append(_STORE, rec)
    return tid


def best_trajectories(action: str, k: int = 3) -> list[dict]:
    """Us action ke top-k traces (reward desc, fir recency desc). Never raises."""
    act = (action or "").strip()
    if not act:
        return []
    try:
        kk = max(1, min(int(k or 3), 50))
    except Exception:
        kk = 3
    rows = [r for r in _read_jsonl(_STORE) if (r.get("action") or "") == act]

    def _sort_key(r: dict[str, Any]) -> tuple[float, str]:
        try:
            rew = float(r.get("reward") or 0.0)
        except Exception:
            rew = 0.0
        return (rew, str(r.get("at") or ""))

    rows.sort(key=_sort_key, reverse=True)
    return rows[:kk]


def _steps_to_text(steps: list[dict]) -> str:
    """Steps ko compact human-readable lines me badlo (replay-hint ke liye)."""
    lines: list[str] = []
    for i, s in enumerate(steps or [], start=1):
        if isinstance(s, dict):
            # common keys try karo, warna pura dict compact-dump
            label = s.get("step") or s.get("action") or s.get("tool") or s.get("name") or ""
            detail = s.get("detail") or s.get("input") or s.get("result") or ""
            if label or detail:
                piece = f"{label}: {detail}".strip(": ").strip()
            else:
                piece = json.dumps(s, ensure_ascii=False, default=str)
        else:
            piece = str(s)
        lines.append(f"{i}. {piece[:_HINT_STEP_CAP]}")
    return "\n".join(lines)


def replay_hint(action: str, max_chars: int = 1200) -> str:
    """Best traces se compact grounding-hint banao (future run ko bias dene ke liye).

    Empty string agar us action ka koi trace na ho. Never raises.
    """
    try:
        cap = max(120, int(max_chars or 1200))
    except Exception:
        cap = 1200
    best = best_trajectories(action, k=3)
    if not best:
        return ""
    out: list[str] = []
    used = 0
    for t in best:
        rew = round(float(t.get("reward") or 0.0), 2)
        head = f"# Past winning run (reward {rew})"
        body = _steps_to_text(t.get("steps") or [])
        outcome = (t.get("outcome") or "").strip()
        block = head + "\n" + body
        if outcome:
            block += f"\nOutcome: {outcome[:_HINT_STEP_CAP]}"
        if used + len(block) > cap:
            break
        out.append(block)
        used += len(block)
    if not out:
        return ""
    return (
        "Yeh past me jo runs actually kaam kar gaye — inke jaisa approach follow karo:\n\n"
        + "\n\n".join(out)
    )


def export_dataset(out_path: str | None = None, min_reward: float = 0.5) -> dict:
    """Winning traces ko JSONL training-dataset me likho (local ML brains fine-tune).

    Har row: {prompt, completion, reward}. Returns {ok, count, path}. Never raises.
    """
    path = out_path or _DEFAULT_EXPORT
    try:
        thresh = float(min_reward)
    except Exception:
        thresh = 0.5
    try:
        rows = _read_jsonl(_STORE)
        winners = []
        for r in rows:
            try:
                rew = float(r.get("reward") or 0.0)
            except Exception:
                rew = 0.0
            if rew >= thresh:
                winners.append((r, rew))
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        count = 0
        with open(path, "w", encoding="utf-8") as f:
            for r, rew in winners:
                rec = {
                    "prompt": r.get("action") or "",
                    "context": (r.get("meta") or {}),
                    "completion": r.get("outcome") or "",
                    "steps": r.get("steps") or [],
                    "reward": rew,
                }
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                count += 1
        return {"ok": True, "count": count, "path": path}
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("export_dataset failed: %s", e)
        return {"ok": False, "count": 0, "path": path, "error": str(e)[:200]}


__all__ = [
    "enabled",
    "record_trajectory",
    "best_trajectories",
    "replay_hint",
    "export_dataset",
]
