"""Skill Library — agents ka AUTO-LEARN store (compounding tactic knowledge).

PROBLEM: agents (coordinator/growth_optimizer/channel_experiments) apne runs se
seekh ke kahin SHARE nahi karte the — har engine apni jagah. Yeh library ek
common ledger hai: kaunsa action/tactic kitni baar chala, kitna succeed hua
(Laplace success-rate), aur free-text LESSONS (reflection se ya manual).
Self-improve loop isi se agla action pick karta (epsilon-greedy) aur har
iteration ke baad outcome wapas likhta — learning kabhi rukti nahi.

Free-stack, pure-Python, NO LLM yahan (callers LLM use karke lesson de sakte).
Import-safe, kabhi raise nahi. Stores: data/skill_uses.jsonl + skill_lessons.jsonl.
"""

from __future__ import annotations

import json
import os
import random
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_USES = os.path.join("data", "skill_uses.jsonl")
_LESSONS = os.path.join("data", "skill_lessons.jsonl")
_MAX_ROWS = 5000  # auto-trim guard


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: str) -> list[dict[str, Any]]:
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


def _trim(path: str) -> None:
    """File bahut badi ho jaye to last _MAX_ROWS rakho (best-effort)."""
    try:
        rows = _read(path)
        if len(rows) > _MAX_ROWS:
            keep = rows[-_MAX_ROWS:]
            with open(path, "w", encoding="utf-8") as f:
                for r in keep:
                    f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------- uses


def record_use(skill: str, ok: bool, detail: str = "", ms: float = 0.0, agent: str = "") -> None:
    """Ek tactic/action ka use + outcome record karo. Kabhi raise nahi."""
    try:
        s = (skill or "").strip().lower()
        if not s:
            return
        _append(
            _USES,
            {
                "skill": s[:60],
                "ok": bool(ok),
                "detail": (detail or "")[:300],
                "ms": round(float(ms or 0), 1),
                "agent": (agent or "")[:30],
                "at": _now(),
            },
        )
        if random.random() < 0.02:  # occasional trim
            _trim(_USES)
    except Exception:
        pass


def stats() -> dict[str, dict[str, Any]]:
    """Per-skill: uses, ok-count, Laplace success-rate. Kabhi raise nahi."""
    out: dict[str, dict[str, Any]] = {}
    try:
        for r in _read(_USES):
            s = r.get("skill") or ""
            if not s:
                continue
            d = out.setdefault(s, {"uses": 0, "ok": 0, "rate": 0.0, "last_at": ""})
            d["uses"] += 1
            if r.get("ok"):
                d["ok"] += 1
            d["last_at"] = r.get("at") or d["last_at"]
        for d in out.values():
            d["rate"] = round((d["ok"] + 1) / (d["uses"] + 2), 4)  # Laplace
    except Exception:
        pass
    return out


def best(k: int = 5) -> list[dict[str, Any]]:
    st = stats()
    ranked = sorted(st.items(), key=lambda kv: kv[1]["rate"], reverse=True)
    return [{"skill": s, **d} for s, d in ranked[:k]]


def worst(k: int = 5) -> list[dict[str, Any]]:
    st = stats()
    ranked = sorted(st.items(), key=lambda kv: kv[1]["rate"])
    return [{"skill": s, **d} for s, d in ranked[:k]]


def pick_action(actions: list[str], epsilon: float = 0.3, rng: random.Random | None = None) -> str:
    """Epsilon-greedy pick: 30% explore random, 70% best success-rate.
    Unknown action = neutral 0.5 rate (naya tactic zero pe nahi marta)."""
    rng = rng or random.Random()
    if not actions:
        return ""
    try:
        st = stats()
        if rng.random() < epsilon:
            return rng.choice(actions)
        return max(actions, key=lambda a: st.get(a, {}).get("rate", 0.5))
    except Exception:
        return actions[0]


# ---------------------------------------------------------------- lessons


def record_lesson(topic: str, lesson: str, source: str = "auto", agent: str = "") -> dict[str, Any]:
    """Ek learned lesson save karo (reflection/manual). Kabhi raise nahi.

    PROCEDURAL memory is durable agent-authored text, so it sits behind the same
    governance gate as the other lanes (inert while the memory stack is off).
    """
    # Governance gate (fail-CLOSED, active only while MEMORY_STACK_ENABLED is on):
    # an unreadable do-not-remember authority must not let durable memory grow.
    try:
        from app.platform.memory_governance import durable_writes_allowed

        _g = durable_writes_allowed()
        if not _g["ok"]:
            return {"ok": False, "deferred": True, "code": _g["code"], "error": _g["reason"]}
    except Exception:
        return {
            "ok": False,
            "deferred": True,
            "code": "MEMORY_WRITE_DEFERRED_GOVERNANCE_UNAVAILABLE",
            "error": "governance module unavailable",
        }
    try:
        t = (topic or "general").strip().lower()[:60]
        body = (lesson or "").strip()
        if not body:
            return {"ok": False, "error": "empty lesson"}
        rec = {
            "topic": t,
            "lesson": body[:500],
            "source": source[:20],
            "agent": (agent or "")[:30],
            "at": _now(),
        }
        _append(_LESSONS, rec)
        # ADR-154: dual-write into workforce hub (L2 skill) — fail-open.
        try:
            from app.platform import workforce_memory as _wfm

            _wfm.remember_lesson_bridge(t, body[:500], agent=(agent or "")[:30], source=source[:20])
        except Exception:
            pass
        return {"ok": True, "lesson": rec}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def lessons(topic: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Lessons (latest-first), optional topic keyword-overlap filter."""
    rows = _read(_LESSONS)
    if topic:
        words = {w for w in topic.lower().split() if len(w) > 2}
        scored = []
        for r in rows:
            hay = (str(r.get("topic", "")) + " " + str(r.get("lesson", ""))).lower()
            score = sum(1 for w in words if w in hay)
            if score:
                scored.append((score, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:limit]]
    return rows[-limit:][::-1]


def lessons_snippet(topic: str, k: int = 3) -> str:
    """1-line-per-lesson snippet kisi bhi agent prompt me inject karne ke liye."""
    out = []
    for r in lessons(topic, k):
        out.append(f"- {r.get('lesson', '')}")
    return "\n".join(out)


def summary() -> dict[str, Any]:
    st = stats()
    return {
        "skills_tracked": len(st),
        "total_uses": sum(d["uses"] for d in st.values()),
        "best": best(5),
        "worst": worst(3),
        "recent_lessons": lessons(limit=5),
    }


__all__ = [
    "record_use",
    "stats",
    "best",
    "worst",
    "pick_action",
    "record_lesson",
    "lessons",
    "lessons_snippet",
    "summary",
]
