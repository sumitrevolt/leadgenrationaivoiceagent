"""RL reward spine (Phase 0) — consolidate existing outcome signals into a
versioned scalar reward log. Logging-only: NO policy/decision change.

Flag-gated (RL_ENGINE), fail-open, idempotent on `ref`, auto-trimmed. Mirrors
the never-raise + INERT-when-unset patterns of eval_gate / lead_usage.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Any

_REWARDS = os.path.join("data", "rl_rewards.jsonl")
_DEV = os.path.join("data", "claude_feedback.jsonl")
_MAX_ROWS = 10000
REWARD_VERSION = "v1"
_DOMAINS = ("voice", "outreach", "funnel", "dev")


def enabled() -> bool:
    return os.environ.get("RL_ENGINE", "").strip().lower() in ("1", "true", "yes", "on")


def _success_threshold() -> float:
    try:
        return float(os.environ.get("RL_SUCCESS_THRESHOLD", "0.5"))
    except Exception:
        return 0.5


def _graduation_n() -> int:
    try:
        return max(10, int(os.environ.get("RL_GRADUATION_N", "200")))
    except Exception:
        return 200


def _clamp(x: float, lo: float, hi: float) -> float:
    try:
        x = float(x)
    except Exception:
        return lo
    if x != x:  # NaN
        return lo
    return max(lo, min(hi, x))


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


# ---------- reward functions (pure) ----------

_VOICE_OUTCOME_W = {
    "appointment": 1.0,
    "qualified": 0.9,
    "interested": 0.7,
    "callback": 0.6,
    "neutral": 0.5,
    "voicemail": 0.4,
    "no_answer": 0.3,
    "busy": 0.3,
    "not_interested": 0.15,
    "wrong_number": 0.1,
    "dnd": 0.0,
    "failed": 0.1,
    "dropped": 0.2,
}


def voice_reward(call: dict[str, Any]) -> float:
    """Map a voice-call outcome to [0,1]. Best-effort over whatever fields are
    present: conversation_quality (0-100), interest_score (0-100), outcome enum,
    qualified bool. qa_violations (list or count) apply a -0.1 each penalty."""
    if not isinstance(call, dict):
        return 0.5
    score = None
    cq = call.get("conversation_quality")
    if isinstance(cq, int | float):
        score = _clamp(float(cq) / 100.0, 0.0, 1.0)
    if score is None:
        isc = call.get("interest_score")
        if isinstance(isc, int | float):
            score = _clamp(float(isc) / 100.0, 0.0, 1.0)
    if score is None:
        oc = str(call.get("outcome", "")).strip().lower()
        if oc in _VOICE_OUTCOME_W:
            score = _VOICE_OUTCOME_W[oc]
    if score is None:
        score = 0.7 if call.get("qualified") else 0.4
    viol = call.get("qa_violations")
    if isinstance(viol, list | tuple):
        score -= 0.1 * len(viol)
    elif isinstance(viol, int | float):
        score -= 0.1 * float(viol)
    return round(_clamp(score, 0.0, 1.0), 4)


_OUTREACH_KIND_W = {
    "signup": 1.0,
    "booked": 1.0,
    "appointment": 0.9,
    "interested": 0.8,
    "reply": 0.6,
    "question": 0.6,
    "inquiry": 0.5,
    "open": 0.3,
    "objection": 0.2,
    "not_interested": -0.3,
    "bounce": -0.5,
    "unsubscribe": -1.0,
    "opt_out": -1.0,
    "complaint": -1.0,
}


def outreach_reward(event: dict[str, Any]) -> float:
    """Map an outreach outcome to [-1,1] from its `kind` (or `intent`)."""
    if not isinstance(event, dict):
        return 0.0
    kind = str(event.get("kind") or event.get("intent") or "").strip().lower()
    return round(_clamp(_OUTREACH_KIND_W.get(kind, 0.0), -1.0, 1.0), 4)


def dev_reward(record: dict[str, Any]) -> float:
    """Map a Claude dev-session outcome to [-1,1]. Single source of truth for
    the dev reward (the Stop hook stores only raw signals; this scores on read)."""
    if not isinstance(record, dict):
        return 0.0
    r = 0.0
    if record.get("user_correction"):
        r -= 0.6
    vp = record.get("verify_pass")
    if vp is True:
        r += 0.4
    elif vp is False:
        r -= 0.4
    tp = record.get("tests_pass")
    if tp is True:
        r += 0.2
    elif tp is False:
        r -= 0.2
    findings = record.get("review_findings")
    if isinstance(findings, int | float):
        r -= 0.05 * float(findings)
    dh = str(record.get("deploy_health", "")).strip().lower()
    if dh in ("ok", "healthy", "200", "production"):
        r += 0.2
    elif dh in ("fail", "unhealthy", "rollback"):
        r -= 0.4
    return round(_clamp(r, -1.0, 1.0), 4)


# ---------- writer ----------


def _read(path: str, n: int | None = None) -> list[dict[str, Any]]:
    try:
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            rows = f.readlines()
        if n:
            rows = rows[-n:]
        out: list[dict[str, Any]] = []
        for ln in rows:
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
        return out
    except Exception:
        return []


def _ref_seen(ref: str, *, path: str, scan: int = 2000) -> bool:
    if not ref:
        return False
    for row in _read(path, n=scan):
        if row.get("ref") == ref:
            return True
    return False


def _trim(path: str) -> None:
    try:
        with open(path, encoding="utf-8") as f:
            rows = f.readlines()
        if len(rows) > _MAX_ROWS:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(rows[-_MAX_ROWS:])
    except Exception:
        pass


def _append(path: str, rec: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    _trim(path)


def record_reward(
    domain: str, arm: str, reward: float, *, ref: str = "", context: dict | None = None
) -> None:
    """Append one versioned reward row. INERT unless RL_ENGINE=1. Never raises.
    Idempotent on `ref`."""
    try:
        if not enabled():
            return
        d = (domain or "").strip().lower()
        if d not in _DOMAINS:
            return
        if ref and _ref_seen(ref, path=_REWARDS):
            return
        rec = {
            "ts": _now(),
            "domain": d,
            "arm": str(arm or "unknown")[:80],
            "reward": _clamp(reward, -1.0, 1.0),
            "reward_version": REWARD_VERSION,
            "ref": str(ref or "")[:120],
            "context": context if isinstance(context, dict) else {},
        }
        _append(_REWARDS, rec)
    except Exception:
        pass


# ---------- readers ----------


def recent(domain: str | None = None, n: int = 50) -> list[dict[str, Any]]:
    rows = _read(_REWARDS)
    if domain:
        rows = [r for r in rows if r.get("domain") == domain]
    return rows[-n:][::-1]


def arm_stats(domain: str) -> dict[str, Any]:
    thr = _success_threshold()
    rows = [r for r in _read(_REWARDS) if r.get("domain") == domain]
    arms: dict[str, dict] = {}
    for r in rows:
        a = r.get("arm", "unknown")
        d = arms.setdefault(a, {"n": 0, "sum": 0.0, "success": 0})
        d["n"] += 1
        rw = float(r.get("reward", 0.0))
        d["sum"] += rw
        if rw >= thr:
            d["success"] += 1
    out: dict[str, Any] = {}
    for a, d in arms.items():
        n = d["n"]
        succ = d["success"]
        out[a] = {
            "n": n,
            "mean_reward": round(d["sum"] / n, 4) if n else 0.0,
            "success_rate": round((succ + 1) / (n + 2), 4),  # Laplace
            "alpha": succ + 1,  # Beta posterior — Phase-1 Thompson will sample this
            "beta": (n - succ) + 1,
        }
    return out


def graduation_status() -> dict[str, Any]:
    grad_n = _graduation_n()
    rows = _read(_REWARDS)
    domains: dict[str, Any] = {}
    for dn in _DOMAINS:
        cnt = sum(1 for r in rows if r.get("domain") == dn)
        domains[dn] = {
            "samples": cnt,
            "graduated": cnt >= grad_n,
            "samples_until_graduation": max(0, grad_n - cnt),
        }
    return {"graduation_n": grad_n, "domains": domains}


def summary() -> dict[str, Any]:
    return {
        "enabled": enabled(),
        "reward_version": REWARD_VERSION,
        "total_rewards": len(_read(_REWARDS)),
        "total_dev_feedback": len(_read(_DEV)),
        "graduation": graduation_status(),
    }


__all__ = [
    "enabled",
    "voice_reward",
    "outreach_reward",
    "dev_reward",
    "record_reward",
    "recent",
    "arm_stats",
    "graduation_status",
    "summary",
    "REWARD_VERSION",
]
