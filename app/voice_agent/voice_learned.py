"""
Curated 'learned good replies' store — Component 3 of the voice smart-fix bundle.
================================================================================

CLOSES the learn-from-calls loop. Today `web_call_learn → voice_self_improve`
already turns a real failing-call turn into a better candidate reply behind a
`promotion_gate`, but the admin "promote" action only flipped a JSONL status field
— nothing reached the live agent (dead-end). Now a PROMOTED proposal is recorded
here as a niche-tagged good example, and `telecaller_brain` injects the top-N for
the current niche into its system prompt — so a human-approved correction from a
real call actually improves the live agent.

GUARDRAILS: only the admin promote path writes here (gated by `promotion_gate` +
`require_admin`); never a blind/auto write. Bounded to top-N per niche so the prompt
stays small (root-cause #2: 8B models under a heavy prompt). Gated
`VOICE_LEARNED_INJECT` (default ON). Every function never raises.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STORE = os.path.join("data", "voice_learned.jsonl")
_MAX_PER_NICHE = 8  # keep the store small + the prompt short
_INJECT_N = 3  # how many examples to inject into the prompt


def enabled() -> bool:
    """VOICE_LEARNED_INJECT gate (default ON). Set 0 to stop injecting learned replies."""
    return (os.environ.get("VOICE_LEARNED_INJECT", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _load() -> list[dict]:
    out: list[dict] = []
    try:
        if os.path.isfile(_STORE):
            with open(_STORE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        continue
    except Exception:
        return []
    return out


def _save(rows: list[dict]) -> None:
    try:
        with open(_STORE, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    except Exception:
        pass


def record(niche: str, user: str, good: str) -> bool:
    """Append an admin-approved (niche, user, good) example; prune to top-N per niche.
    Returns True on write. Never raises. (Called only from the gated promote path.)"""
    try:
        niche = (str(niche or "general")).strip() or "general"
        good = str(good or "").strip()[:600]
        if not good:
            return False
        rows = _load()
        rows.append(
            {
                "niche": niche,
                "user": str(user or "").strip()[:400],
                "good": good,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        )
        # prune: keep the most recent _MAX_PER_NICHE per niche (preserve order)
        seen: dict[str, int] = {}
        kept_rev: list[dict] = []
        for r in reversed(rows):
            n = str(r.get("niche") or "general")
            if seen.get(n, 0) >= _MAX_PER_NICHE:
                continue
            seen[n] = seen.get(n, 0) + 1
            kept_rev.append(r)
        _save(list(reversed(kept_rev)))
        logger.info("voice_learned: recorded approved example for niche=%s", niche)
        return True
    except Exception:
        return False


def examples_for(niche: str, n: int = _INJECT_N) -> list[dict]:
    """Most-recent approved examples for a niche (empty if disabled/none). Never raises."""
    try:
        if not enabled():
            return []
        niche = (str(niche or "general")).strip() or "general"
        rows = [
            r
            for r in _load()
            if str(r.get("niche") or "") == niche and (r.get("good") or "").strip()
        ]
        return rows[-max(1, int(n)) :] if rows else []
    except Exception:
        return []


def hint_for(niche: str, n: int = _INJECT_N) -> str:
    """A short few-shot 'good replies' block for the system prompt ('' if none)."""
    try:
        ex = examples_for(niche, n)
        if not ex:
            return ""
        lines: list[str] = []
        for e in ex:
            u = (e.get("user") or "").strip()
            g = (e.get("good") or "").strip()
            if not g:
                continue
            lines.append(
                f'- Customer: "{u}" -> accha jawab: "{g}"' if u else f'- Accha jawab: "{g}"'
            )
        return "\n".join(lines)
    except Exception:
        return ""


__all__ = ["enabled", "record", "examples_for", "hint_for"]
