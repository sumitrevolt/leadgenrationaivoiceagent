# RL Self-Improvement Flywheel (Phase 0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the data + observability spine of a closed reinforcement-learning reward loop — versioned reward log from existing outcomes + a Claude dev-time reward-capture hook + a read-only admin view — with ZERO behavior change.

**Architecture:** New additive `app/agents/rl/` package whose `reward.py` consolidates already-logged outcomes (voice / outreach / funnel / dev) into one versioned scalar reward written to `data/rl_rewards.jsonl`. Reward is *emitted* from three existing outcome hooks (logging-only — no decision logic touched) and from a Claude `Stop` hook. A read-only `/api/rl/*` API (mirroring `app/api/eval_gate.py`) + one Mission-Control tab surface it. The policy engine (Thompson/contextual/OPE) is deferred behind a sample-count "graduation" gate and NOT built here.

**Tech Stack:** Python 3.12, FastAPI, append-only JSONL (no new deps), pytest. Spec: `docs/superpowers/specs/2026-06-29-rl-self-improvement-flywheel-design.md`.

## Global Constraints

- **Free-stack only** — no new pip dependencies; pure-python (json/os/datetime). Reward stats are Laplace/Beta computed from JSONL.
- **Additive only** — never rewrite `skill_library`, `eval_gate`, `channel_experiments`, `self_improve`, `post_call_hooks`. Add guarded one-liners.
- **Flag-gated, default OFF** — master flag `RL_ENGINE`. Unset ⇒ fully inert (no file writes, endpoints return empty). Aux flags `RL_SUCCESS_THRESHOLD` (default `0.5`), `RL_GRADUATION_N` (default `200`).
- **Fail-open / never-raise** — every emission path wrapped in `try/except: pass`. A reward error must never break a call, email, loop tick, API request, or Claude session.
- **Idempotent** — reward rows dedupe on `ref` (call_sid / run id). Auto-trim each JSONL to last 10000 rows.
- **eval_gate = gate, reward = optimizer** — keep distinct; Phase 0 only writes the reward log, does not couple to eval_gate.
- **Windows = source of truth** — edit with Windows file-tools; Read each file immediately before editing (sandbox mount is stale). Run Python via `.venv\Scripts\python.exe`.
- **duplicate-route-guard** — before adding the router, grep `prefix="/api/rl"` to confirm uniqueness (FastAPI first-route-wins).
- **Hinglish, concise** in any user-facing copy; keep the Mission-Control tab visually consistent with neighbors.

---

### Task 1: RL reward core module (`app/agents/rl/reward.py`)

**Files:**
- Create: `app/agents/rl/__init__.py`
- Create: `app/agents/rl/reward.py`
- Test: `tests/test_rl_reward.py`

**Interfaces:**
- Produces (later tasks rely on these exact signatures):
  - `enabled() -> bool`
  - `voice_reward(call: dict) -> float` (range `[0,1]`)
  - `outreach_reward(event: dict) -> float` (range `[-1,1]`)
  - `dev_reward(record: dict) -> float` (range `[-1,1]`)
  - `record_reward(domain: str, arm: str, reward: float, *, ref: str = "", context: dict | None = None) -> None`
  - `recent(domain: str | None = None, n: int = 50) -> list[dict]`
  - `arm_stats(domain: str) -> dict`
  - `graduation_status() -> dict`
  - `summary() -> dict`
  - module constants `_REWARDS`, `_DEV`, `REWARD_VERSION`, helper `_read(path, n=None)`

- [ ] **Step 1: Write the failing test** — `tests/test_rl_reward.py`

```python
import importlib
import json
import os

import pytest


@pytest.fixture
def rl(tmp_path, monkeypatch):
    """Fresh reward module with isolated data files + flag ON."""
    monkeypatch.setenv("RL_ENGINE", "1")
    import app.agents.rl.reward as reward
    importlib.reload(reward)
    monkeypatch.setattr(reward, "_REWARDS", str(tmp_path / "rl_rewards.jsonl"))
    monkeypatch.setattr(reward, "_DEV", str(tmp_path / "claude_feedback.jsonl"))
    return reward


def test_voice_reward_monotonic(rl):
    assert rl.voice_reward({"outcome": "appointment"}) > rl.voice_reward({"outcome": "not_interested"})
    assert rl.voice_reward({"qualified": True}) > rl.voice_reward({"qualified": False})
    assert rl.voice_reward({"conversation_quality": 90}) > rl.voice_reward({"conversation_quality": 20})
    # qa violations penalize
    assert rl.voice_reward({"interest_score": 80, "qa_violations": 3}) < rl.voice_reward({"interest_score": 80})
    assert 0.0 <= rl.voice_reward({"outcome": "dnd"}) <= 1.0


def test_outreach_reward_signs(rl):
    assert rl.outreach_reward({"kind": "signup"}) > 0
    assert rl.outreach_reward({"kind": "unsubscribe"}) < 0
    assert rl.outreach_reward({"kind": "totally_unknown"}) == 0.0
    assert rl.outreach_reward({"intent": "interested"}) > 0


def test_dev_reward(rl):
    assert rl.dev_reward({"user_correction": True}) < 0
    assert rl.dev_reward({"verify_pass": True, "tests_pass": True, "deploy_health": "ok"}) > 0
    assert -1.0 <= rl.dev_reward({"verify_pass": False, "user_correction": True}) <= 1.0


def test_record_inert_when_off(tmp_path, monkeypatch):
    monkeypatch.delenv("RL_ENGINE", raising=False)
    import app.agents.rl.reward as reward
    importlib.reload(reward)
    monkeypatch.setattr(reward, "_REWARDS", str(tmp_path / "r.jsonl"))
    reward.record_reward("voice", "salon", 0.9, ref="c1")
    assert not os.path.exists(str(tmp_path / "r.jsonl"))


def test_record_writes_and_idempotent(rl):
    rl.record_reward("voice", "salon", 0.9, ref="call-1", context={"niche": "salon"})
    rl.record_reward("voice", "salon", 0.9, ref="call-1")  # duplicate ref ignored
    rows = rl._read(rl._REWARDS)
    assert len(rows) == 1
    assert rows[0]["domain"] == "voice"
    assert rows[0]["reward_version"] == rl.REWARD_VERSION
    assert rows[0]["context"]["niche"] == "salon"


def test_unknown_domain_dropped(rl):
    rl.record_reward("bogus", "x", 0.5, ref="z1")
    assert rl._read(rl._REWARDS) == []


def test_graduation_status(rl):
    for i in range(5):
        rl.record_reward("funnel", "scrape_leads", 0.6, ref=f"r{i}")
    g = rl.graduation_status()
    assert g["domains"]["funnel"]["samples"] == 5
    assert g["domains"]["funnel"]["graduated"] is False
    assert g["domains"]["funnel"]["samples_until_graduation"] == g["graduation_n"] - 5


def test_arm_stats(rl):
    rl.record_reward("outreach", "quora", 0.9, ref="a1")
    rl.record_reward("outreach", "quora", 0.1, ref="a2")
    s = rl.arm_stats("outreach")["quora"]
    assert s["n"] == 2
    assert 0.0 <= s["success_rate"] <= 1.0
    assert s["alpha"] >= 1 and s["beta"] >= 1


def test_never_raises_on_garbage(rl):
    rl.record_reward("voice", None, float("nan"), ref=None)  # must not raise
    assert rl.voice_reward("not-a-dict") == 0.5
    assert rl.outreach_reward(None) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_rl_reward.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agents.rl'`

- [ ] **Step 3: Create the package init**

`app/agents/rl/__init__.py`:

```python
"""RL self-improvement flywheel (Phase 0) — reward spine only.

Logging-only reward consolidation. No policy/decision change. Policy engine
(Thompson / contextual / OPE) is deferred behind a sample-count graduation gate.
See docs/superpowers/specs/2026-06-29-rl-self-improvement-flywheel-design.md.
"""
```

- [ ] **Step 4: Write the implementation** — `app/agents/rl/reward.py`

```python
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
    "appointment": 1.0, "qualified": 0.9, "interested": 0.7, "callback": 0.6,
    "neutral": 0.5, "voicemail": 0.4, "no_answer": 0.3, "busy": 0.3,
    "not_interested": 0.15, "wrong_number": 0.1, "dnd": 0.0, "failed": 0.1, "dropped": 0.2,
}


def voice_reward(call: dict[str, Any]) -> float:
    """Map a voice-call outcome to [0,1]. Best-effort over whatever fields are
    present: conversation_quality (0-100), interest_score (0-100), outcome enum,
    qualified bool. qa_violations (list or count) apply a -0.1 each penalty."""
    if not isinstance(call, dict):
        return 0.5
    score = None
    cq = call.get("conversation_quality")
    if isinstance(cq, (int, float)):
        score = _clamp(float(cq) / 100.0, 0.0, 1.0)
    if score is None:
        isc = call.get("interest_score")
        if isinstance(isc, (int, float)):
            score = _clamp(float(isc) / 100.0, 0.0, 1.0)
    if score is None:
        oc = str(call.get("outcome", "")).strip().lower()
        if oc in _VOICE_OUTCOME_W:
            score = _VOICE_OUTCOME_W[oc]
    if score is None:
        score = 0.7 if call.get("qualified") else 0.4
    viol = call.get("qa_violations")
    if isinstance(viol, (list, tuple)):
        score -= 0.1 * len(viol)
    elif isinstance(viol, (int, float)):
        score -= 0.1 * float(viol)
    return round(_clamp(score, 0.0, 1.0), 4)


_OUTREACH_KIND_W = {
    "signup": 1.0, "booked": 1.0, "appointment": 0.9, "interested": 0.8,
    "reply": 0.6, "question": 0.6, "inquiry": 0.5, "open": 0.3,
    "objection": 0.2, "not_interested": -0.3, "bounce": -0.5,
    "unsubscribe": -1.0, "opt_out": -1.0, "complaint": -1.0,
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
    if isinstance(findings, (int, float)):
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
        with open(path, "r", encoding="utf-8") as f:
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
        with open(path, "r", encoding="utf-8") as f:
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
    "enabled", "voice_reward", "outreach_reward", "dev_reward",
    "record_reward", "recent", "arm_stats", "graduation_status", "summary",
    "REWARD_VERSION",
]
```

- [ ] **Step 5: Run the tests and make sure they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_rl_reward.py -q`
Expected: PASS (all tests green)

- [ ] **Step 6: Commit**

```bash
git add app/agents/rl/__init__.py app/agents/rl/reward.py tests/test_rl_reward.py
git commit -m "feat(rl): Phase-0 reward spine — versioned reward functions + log (flag-gated, fail-open)"
```

---

### Task 2: Register flags (`RL_ENGINE`, `RL_SUCCESS_THRESHOLD`, `RL_GRADUATION_N`)

**Files:**
- Modify: `app/api/automation_flags.py` (the `AUTOMATION_FLAGS` list — append before the closing `]`)
- Modify: `.env.example` (document the flags)

**Interfaces:** none new — makes the flags visible at `GET /api/growth/infra/flags`.

- [ ] **Step 1: Read the file** — Read `app/api/automation_flags.py` (the list ends near line 248 with `]`).

- [ ] **Step 2: Append the flag entries** just before the closing `]` of `AUTOMATION_FLAGS`:

```python
    # --- RL self-improvement flywheel (Phase 0, 2026-06-29) — reward spine only ---
    "RL_ENGINE",  # master gate for reward-log emission + Stop hook + /api/rl (default OFF = fully inert)
    "RL_SUCCESS_THRESHOLD",  # reward >= this counts as a "success" for Beta/Laplace arm stats (default 0.5)
    "RL_GRADUATION_N",  # per-domain samples before Phase-1 policy graduation (default 200; Phase-1 not built yet)
```

- [ ] **Step 3: Document in `.env.example`** — add near the EVAL_GATE block:

```bash
# --- RL self-improvement flywheel (Phase 0) — reward spine, logging-only ---
# Master gate. OFF = no reward rows written, Stop hook no-op, /api/rl returns empty.
RL_ENGINE=0
RL_SUCCESS_THRESHOLD=0.5
RL_GRADUATION_N=200
```

- [ ] **Step 4: Verify import + flag visible**

Run: `.venv\Scripts\python.exe -c "from app.api.automation_flags import AUTOMATION_FLAGS; assert 'RL_ENGINE' in AUTOMATION_FLAGS; print('OK', len(AUTOMATION_FLAGS))"`
Expected: `OK <n>` (no assertion error)

- [ ] **Step 5: Commit**

```bash
git add app/api/automation_flags.py .env.example
git commit -m "feat(rl): register RL_ENGINE / RL_SUCCESS_THRESHOLD / RL_GRADUATION_N flags"
```

---

### Task 3: Loop A wiring — emit reward at 3 existing outcome points (logging-only)

**Files:**
- Modify: `app/marketing/channel_experiments.py` (inside `record_outcome`, after the `_append(_OUTCOMES, …)` call ~line 275)
- Modify: `app/agents/self_improve.py` (in `run_once`, after `_append(_RUNS, rec)` ~line 1443)
- Modify: `app/telephony/post_call_hooks.py` (in `auto_qualify_and_downstream`, after writing `call_qualifications.jsonl` ~line 282)
- Test: `tests/test_rl_reward.py` (add one wiring test via the channel_experiments path)

**Interfaces:**
- Consumes: `app.agents.rl.reward.record_reward`, `.voice_reward`, `.outreach_reward` (Task 1).

- [ ] **Step 1: Write the failing wiring test** — append to `tests/test_rl_reward.py`:

```python
def test_channel_experiments_emits_reward(tmp_path, monkeypatch):
    monkeypatch.setenv("RL_ENGINE", "1")
    import importlib
    import app.agents.rl.reward as reward
    importlib.reload(reward)
    monkeypatch.setattr(reward, "_REWARDS", str(tmp_path / "rl_rewards.jsonl"))

    import app.marketing.channel_experiments as ce
    out = ce.record_outcome("quora", kind="reply")
    assert out["ok"] is True
    rows = reward._read(reward._REWARDS)
    assert any(r["domain"] == "outreach" and r["arm"] == "quora" for r in rows)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_rl_reward.py::test_channel_experiments_emits_reward -q`
Expected: FAIL (no reward row written — wiring absent)

- [ ] **Step 3a: Wire `channel_experiments.record_outcome`** — Read the file, then insert immediately after the `_append(_OUTCOMES, {…})` block and before `return {"ok": True, …}`:

```python
        # RL reward spine (Phase 0, logging-only) — INERT unless RL_ENGINE=1, never raises.
        try:
            from app.agents.rl import reward as _rl_reward

            _rl_reward.record_reward(
                "outreach", ch, _rl_reward.outreach_reward({"kind": kind}),
                ref=f"chexp:{ch}:{kind}:{_now().isoformat()}",
            )
        except Exception:
            pass
```

- [ ] **Step 3b: Wire `self_improve.run_once`** — Read the file, then insert immediately after `_append(_RUNS, rec)` (the line that appends the run record):

```python
    # RL reward spine (Phase 0) — mirror outcome_value into the unified reward log.
    try:
        from app.agents.rl import reward as _rl_reward

        _rl_reward.record_reward(
            "funnel", action, float(rec["outcome_value"]),
            ref=rec["id"], context={"source": rec["source"]},
        )
    except Exception:
        pass
```

- [ ] **Step 3c: Wire `post_call_hooks.auto_qualify_and_downstream`** — Read the file, then insert immediately after the `with open(... "call_qualifications.jsonl" ...)` write block (after the file is written, inside the same `try`):

```python
        # RL reward spine (Phase 0) — voice outcome → unified reward log.
        try:
            from app.agents.rl import reward as _rl_reward

            _rl_reward.record_reward(
                "voice", niche or "general", _rl_reward.voice_reward(q),
                ref=str(call_id or rec.get("ts", "")),
                context={"niche": niche, "city": city},
            )
        except Exception:
            pass
```

- [ ] **Step 4: Run the wiring test + full reward suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_rl_reward.py -q`
Expected: PASS (including `test_channel_experiments_emits_reward`)

- [ ] **Step 5: Verify no behavior change with flag OFF**

Run: `.venv\Scripts\python.exe -c "import os; os.environ.pop('RL_ENGINE', None); import app.marketing.channel_experiments as ce; print(ce.record_outcome('quora', kind='reply')['ok'])"`
Expected: `True` (function still works; no reward file created)

- [ ] **Step 6: Commit**

```bash
git add app/marketing/channel_experiments.py app/agents/self_improve.py app/telephony/post_call_hooks.py tests/test_rl_reward.py
git commit -m "feat(rl): emit reward at voice/outreach/funnel outcome hooks (logging-only, guarded)"
```

---

### Task 4: Read-only admin API (`app/api/rl.py`)

**Files:**
- Create: `app/api/rl.py`
- Modify: `app/main.py` (include the router — grep `eval_gate` to find the include block)
- Test: `tests/test_rl_reward.py` (router-shape smoke test)

**Interfaces:**
- Consumes: `app.agents.rl.reward.{summary, arm_stats, recent, dev_reward, _read, _DEV}`, `app.api.auth_deps.require_admin`.
- Produces: `router` with routes `/api/rl/summary`, `/api/rl/arms`, `/api/rl/recent`, `/api/rl/dev`.

- [ ] **Step 1: Confirm route prefix is unique (duplicate-route-guard)**

Run: `.venv\Scripts\python.exe -c "import subprocess"` — instead grep the repo:
Run (Grep tool): pattern `prefix=\"/api/rl\"` — Expected: zero existing matches.

- [ ] **Step 2: Write the failing smoke test** — append to `tests/test_rl_reward.py`:

```python
def test_rl_router_shape():
    from app.api.rl import router
    paths = {r.path for r in router.routes}
    assert "/api/rl/summary" in paths
    assert "/api/rl/arms" in paths
    assert "/api/rl/recent" in paths
    assert "/api/rl/dev" in paths
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_rl_reward.py::test_rl_router_shape -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.api.rl'`

- [ ] **Step 4: Create `app/api/rl.py`**

```python
"""RL Flywheel admin API (Phase 0) — read-only visibility into the reward spine.

Mirrors app/api/eval_gate.py. No policy control here; observability only.
Admin-gated. INERT data when RL_ENGINE unset (reward.* returns empty).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.agents.rl import reward
from app.api.auth_deps import require_admin

router = APIRouter(prefix="/api/rl", tags=["Infrastructure"])


@router.get("/summary")
async def rl_summary(_user=Depends(require_admin)) -> dict:
    """Totals + per-domain graduation status (samples vs RL_GRADUATION_N)."""
    return reward.summary()


@router.get("/arms")
async def rl_arms(domain: str = "voice", _user=Depends(require_admin)) -> dict:
    """Per-arm n / mean_reward / Laplace success_rate / Beta(alpha,beta)."""
    return {"domain": domain, "arms": reward.arm_stats(domain)}


@router.get("/recent")
async def rl_recent(domain: str = "", n: int = 50, _user=Depends(require_admin)) -> dict:
    """Recent reward rows (optionally filtered by domain)."""
    n = max(1, min(int(n), 500))
    return {"domain": domain or "all", "rows": reward.recent(domain or None, n=n)}


@router.get("/dev")
async def rl_dev(n: int = 50, _user=Depends(require_admin)) -> dict:
    """Recent Claude dev-session feedback, scored on read via reward.dev_reward."""
    n = max(1, min(int(n), 500))
    rows = reward._read(reward._DEV, n=n)
    for r in rows:
        r["reward"] = reward.dev_reward(r)
    return {"count": len(rows), "rows": rows[::-1]}


__all__ = ["router"]
```

- [ ] **Step 5: Include the router in `app/main.py`** — Read `app/main.py`, find where `eval_gate` router is included (grep `eval_gate`), and add alongside it:

```python
    from app.api import rl as rl_api  # RL flywheel (Phase 0, read-only admin)

    app.include_router(rl_api.router)
```

(Match the exact include style used for `eval_gate` in that file — some routers are imported at top and included in a block; follow the neighbor pattern.)

- [ ] **Step 6: Run smoke test + import check**

Run: `.venv\Scripts\python.exe -m pytest tests/test_rl_reward.py::test_rl_router_shape -q`
Expected: PASS
Run: `.venv\Scripts\python.exe -c "import app.main; print('IMPORT_OK')"`
Expected: `IMPORT_OK`

- [ ] **Step 7: Commit**

```bash
git add app/api/rl.py app/main.py tests/test_rl_reward.py
git commit -m "feat(rl): read-only /api/rl admin endpoints (summary/arms/recent/dev)"
```

---

### Task 5: Loop B — Claude dev-time reward-capture (Stop hook + /verify marker + consumption)

**Files:**
- Create: `.claude/hooks/reward_capture.py`
- Modify: `.claude/settings.json` (add a `Stop` hook block)
- Modify: `.claude/commands/verify.md` (write a marker file `data/.claude_last_verify.json` at end of verify)
- Modify: `.claude/commands/learn.md` and `.claude/skills/retro/SKILL.md` (read `data/claude_feedback.jsonl` to reinforce winners / guardrail losers)
- Test: `tests/test_rl_dev_hook.py`

**Interfaces:**
- Produces: `data/claude_feedback.jsonl` rows `{ts, task, verify_pass, tests_pass, review_findings, deploy_health, user_correction}` (no `reward` field — scored on read by `reward.dev_reward`).

- [ ] **Step 1: Write the failing test** — `tests/test_rl_dev_hook.py`:

```python
import json
import os
import subprocess
import sys


def test_reward_capture_writes_when_on(tmp_path):
    env = dict(os.environ, RL_ENGINE="1")
    hook = os.path.abspath(os.path.join(".claude", "hooks", "reward_capture.py"))
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / ".claude_last_verify.json").write_text(
        json.dumps({"pass": True, "tests_pass": True, "deploy_health": "ok"})
    )
    subprocess.run([sys.executable, hook], cwd=str(tmp_path), env=env,
                   input="{}", text=True, timeout=20)
    out = tmp_path / "data" / "claude_feedback.jsonl"
    assert out.exists()
    rec = json.loads(out.read_text().splitlines()[-1])
    assert rec["verify_pass"] is True
    assert rec["tests_pass"] is True


def test_reward_capture_inert_when_off(tmp_path):
    env = dict(os.environ)
    env.pop("RL_ENGINE", None)
    hook = os.path.abspath(os.path.join(".claude", "hooks", "reward_capture.py"))
    (tmp_path / "data").mkdir()
    subprocess.run([sys.executable, hook], cwd=str(tmp_path), env=env,
                   input="{}", text=True, timeout=20)
    assert not (tmp_path / "data" / "claude_feedback.jsonl").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_rl_dev_hook.py -q`
Expected: FAIL — hook file does not exist (subprocess errors / no output file)

- [ ] **Step 3: Create `.claude/hooks/reward_capture.py`**

```python
#!/usr/bin/env python3
"""Stop hook (Phase 0, Loop B) — capture Claude dev-session outcome signals.

Writes ONE raw record to data/claude_feedback.jsonl. The reward SCORE is computed
on READ by app.agents.rl.reward.dev_reward (single source of truth) — this hook
stores only raw signals so it stays dependency-free and fast.

INERT unless RL_ENGINE=1. Fail-open: any error → exit 0, never blocks the session.
Self-contained (no app import) — runs on the Claude Code host with a 10s budget.
"""
import datetime
import json
import os
import sys


def _flag_on() -> bool:
    return os.environ.get("RL_ENGINE", "").strip().lower() in ("1", "true", "yes", "on")


def _read_marker(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def main() -> None:
    try:
        if not _flag_on():
            return
        raw = ""
        try:
            if not sys.stdin.isatty():
                raw = sys.stdin.read()
        except Exception:
            raw = ""
        try:
            sess = json.loads(raw) if raw.strip() else {}
        except Exception:
            sess = {}
        verify = _read_marker(os.path.join("data", ".claude_last_verify.json"))
        rec = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "task": str(sess.get("cwd") or sess.get("session_id") or "")[:120],
            "verify_pass": verify.get("pass"),
            "tests_pass": verify.get("tests_pass"),
            "review_findings": verify.get("review_findings"),
            "deploy_health": verify.get("deploy_health"),
            "user_correction": None,  # set by /learn when the user flags a mistake
        }
        os.makedirs("data", exist_ok=True)
        with open(os.path.join("data", "claude_feedback.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_rl_dev_hook.py -q`
Expected: PASS

- [ ] **Step 5: Register the `Stop` hook in `.claude/settings.json`** — Read the file; inside `"hooks"`, add a sibling key to `"PreToolUse"`:

```json
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "python .claude/hooks/reward_capture.py 2>/dev/null || true", "shell": "bash", "timeout": 10 }
        ]
      }
    ]
```

(Add a comma after the `PreToolUse` array's closing `]` so the JSON stays valid.)

- [ ] **Step 6: Write the verify marker** — in `.claude/commands/verify.md`, add a final instruction so `/verify` records its result:

> After printing the PASS/FAIL report, write `data/.claude_last_verify.json` with `{"pass": <bool>, "tests_pass": <bool>, "review_findings": <int|null>, "deploy_health": <str|null>}` (Windows file-tools). This marker is read by the Stop hook (`reward_capture.py`) to score the session's dev-reward.

- [ ] **Step 7: Wire consumption** — in `.claude/commands/learn.md` and `.claude/skills/retro/SKILL.md`, add a step:

> If `data/claude_feedback.jsonl` exists, read the last ~30 rows. For rows where `dev_reward` (verify_pass + tests_pass + deploy_health, minus user_correction/findings) is high, reinforce the pattern into a `memory/` feedback note or skill snippet. For low-reward rows (user_correction true, verify fail), propose a `guard.py` / `skill_reminder.py` guardrail. This closes Loop B using existing machinery — do NOT build a new dashboard.

- [ ] **Step 8: Validate settings.json is still valid JSON**

Run: `.venv\Scripts\python.exe -c "import json; json.load(open('.claude/settings.json', encoding='utf-8')); print('JSON_OK')"`
Expected: `JSON_OK`

- [ ] **Step 9: Commit**

```bash
git add .claude/hooks/reward_capture.py .claude/settings.json .claude/commands/verify.md .claude/commands/learn.md .claude/skills/retro/SKILL.md tests/test_rl_dev_hook.py
git commit -m "feat(rl): Loop B — Claude dev-session reward-capture Stop hook + /verify marker + retro consumption"
```

---

### Task 6: Observability — "RL Flywheel" tab in Mission Control (`frontend/automation.html`)

**Files:**
- Modify: `frontend/automation.html` (add one tab button + one panel + a fetch/render block, following the existing tab pattern)

**Interfaces:**
- Consumes: `GET /api/rl/summary`, `/api/rl/arms?domain=`, `/api/rl/dev`.

- [ ] **Step 1: Read `frontend/automation.html`** to learn the exact tab pattern (how a tab button maps to a panel, how neighbors `fetch()` admin endpoints and render, whether auth header/credentials are attached).

- [ ] **Step 2: Add the tab button** in the tab strip (match neighbor markup), e.g.:

```html
<button class="tab-btn" onclick="showTab('rlFlywheel')">🎯 RL Flywheel</button>
```

- [ ] **Step 3: Add the panel + render script** (match the file's existing fetch/render idiom — reuse its auth/credentials helper if present):

```html
<div id="rlFlywheel" class="tab-panel" style="display:none">
  <h3>RL Flywheel — reward spine (Phase 0, logging-only)</h3>
  <div id="rlGrad" class="muted">loading…</div>
  <h4>Per-arm reward</h4>
  <label>Domain:
    <select id="rlDomain" onchange="loadRlArms()">
      <option>voice</option><option>outreach</option><option>funnel</option>
    </select>
  </label>
  <table id="rlArms"><thead><tr><th>arm</th><th>n</th><th>mean</th><th>success</th></tr></thead><tbody></tbody></table>
  <h4>Claude dev-feedback</h4>
  <div id="rlDev" class="muted"></div>
</div>
<script>
async function loadRlFlywheel() {
  try {
    const s = await (await fetch('/api/rl/summary', {credentials:'include'})).json();
    const g = s.graduation || {domains:{}};
    document.getElementById('rlGrad').innerHTML = Object.entries(g.domains||{})
      .map(([d,v]) => `<b>${d}</b>: ${v.samples}/${g.graduation_n} `
        + (v.graduated ? '✅ graduated' : `(${v.samples_until_graduation} to go)`)).join(' &nbsp;|&nbsp; ')
      + ` &nbsp; <span class="muted">engine ${s.enabled?'ON':'OFF'} · ${s.total_rewards} rewards</span>`;
    loadRlArms();
    const dev = await (await fetch('/api/rl/dev?n=10', {credentials:'include'})).json();
    document.getElementById('rlDev').textContent = `${dev.count} dev-session rows`;
  } catch (e) { document.getElementById('rlGrad').textContent = 'unavailable'; }
}
async function loadRlArms() {
  const dom = document.getElementById('rlDomain').value;
  const r = await (await fetch('/api/rl/arms?domain='+dom, {credentials:'include'})).json();
  const tb = document.querySelector('#rlArms tbody'); tb.innerHTML = '';
  Object.entries(r.arms||{}).forEach(([a,v]) => {
    tb.innerHTML += `<tr><td>${a}</td><td>${v.n}</td><td>${v.mean_reward}</td><td>${v.success_rate}</td></tr>`;
  });
}
</script>
```

(Ensure the tab's `showTab('rlFlywheel')` also calls `loadRlFlywheel()` — follow how neighbor tabs trigger their loaders; some call the loader inside `showTab`, others on button click.)

- [ ] **Step 4: Verify frontend wiring + routes**

Run: `.venv\Scripts\python.exe scripts/prod_check.py`
Expected: exit 0 — including the frontend onclick/fetch wiring check (every `fetch('/api/rl/...')` resolves to a registered route) and no duplicate `/api/rl` route.

- [ ] **Step 5: Commit**

```bash
git add frontend/automation.html
git commit -m "feat(rl): RL Flywheel observability tab in Mission Control (read-only)"
```

---

### Task 7: Full verify + spec-coverage close-out

**Files:** none (verification only)

- [ ] **Step 1: Run the full reward + hook suites**

Run: `.venv\Scripts\python.exe -m pytest tests/test_rl_reward.py tests/test_rl_dev_hook.py -q`
Expected: PASS

- [ ] **Step 2: Run prod_check + cross_path_audit**

Run: `.venv\Scripts\python.exe scripts/prod_check.py`
Run: `.venv\Scripts\python.exe scripts/cross_path_audit.py`
Expected: both exit 0

- [ ] **Step 3: Import sanity**

Run: `.venv\Scripts\python.exe -c "import app.main; from app.agents.rl import reward; from app.api import rl; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Flag-OFF inertness proof** (the key safety claim)

Run: `.venv\Scripts\python.exe -c "import os; os.environ.pop('RL_ENGINE',None); from app.agents.rl import reward; reward.record_reward('voice','x',0.9,ref='t'); print('inert', reward.summary()['enabled'])"`
Expected: `inert False` and no `data/rl_rewards.jsonl` row added.

- [ ] **Step 5: Commit any final fixes; deployment is a separate explicit step**

Deployment to the VPS is NOT part of this plan. After merge, enabling on the VPS is a one-line `.env` change (`RL_ENGINE=1`) + container recreate, done via the `/ship` flow only when the user asks. Phase 0 is intentionally inert until then.

---

## Self-Review

**Spec coverage:**
- Reward spine (`reward.py`, versioned, idempotent, auto-trim) → Task 1 ✅
- Reward functions voice/outreach/funnel/dev → Task 1 ✅ (`funnel` uses outcome_value passthrough at the wiring site rather than re-importing `compute_outcome_value` — equivalent, avoids a circular import)
- Flags `RL_ENGINE` / `RL_SUCCESS_THRESHOLD` / `RL_GRADUATION_N` → Task 2 ✅
- Loop A emit at post_call_hooks / channel_experiments / self_improve → Task 3 ✅
- eval_gate stays untouched (gate ≠ optimizer) → no task modifies eval_gate ✅
- Read-only `/api/rl/*` mirroring eval_gate → Task 4 ✅
- Loop B Stop hook + claude_feedback.jsonl + consumption via /learn,/retro → Task 5 ✅
- Observability tab → Task 6 ✅
- Testing (pure-fn, idempotency, inert-when-off, failure-path, router-shape, hook subprocess) → Tasks 1,3,4,5,7 ✅
- Graduation status / Phase-1 hook (Beta alpha/beta exposed for future Thompson) → Task 1 `arm_stats` ✅

**Placeholder scan:** none — all steps carry real code/commands.

**Type consistency:** `record_reward(domain, arm, reward, *, ref, context)`, `voice_reward/outreach_reward/dev_reward(dict)->float`, `arm_stats(domain)->{arm:{n,mean_reward,success_rate,alpha,beta}}`, `graduation_status()->{graduation_n, domains:{d:{samples,graduated,samples_until_graduation}}}` — used identically in Tasks 3, 4, 6. Hook writes raw signals (no `reward` field); `/api/rl/dev` and Task 1 `dev_reward` score on read — single source of truth, consistent.

**Decisions deferred to implementer (verify-at-execution):** exact insertion line in `app/main.py` for the router include (grep `eval_gate`); exact tab-trigger idiom in `automation.html` (follow neighbor). Both are pattern-match, not invention.
