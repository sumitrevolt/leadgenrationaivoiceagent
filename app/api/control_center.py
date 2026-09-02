"""Control Center — enterprise ops cockpit L1 (Executive) read-side aggregator.

ONE call powers the whole "Control Center" dashboard L1 view so the frontend
doesn't fan out to 6 separate admin endpoints (each its own round-trip + auth).

This is a THIN read-only aggregator: it fans IN over existing modules
(today_overview + automation_health + llm_metrics + activation + eval_gate +
flow_dispatch), each in its OWN try/except — partial data is fine, NEVER raises.
Every import is lazy (inside the function) so a broken downstream module can
never break app import. On total failure the top-level guard still returns a
minimal `{ok: true, ...defaults}` shell.

API: GET /api/control-center/overview (admin) → /app/control-center page.
Mounted via app.include_router(..., prefix="/api") in app/main.py.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends

from app.api.auth_deps import require_admin

router = APIRouter(tags=["Control Center"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _control_center_enabled() -> bool:
    """CONTROL_CENTER nav-surface gate (INERT default). The overview API itself
    stays admin-reachable for ops, but this flag tells the frontend whether the
    Control Center nav entry / page should be surfaced to users (default OFF)."""
    return (os.getenv("CONTROL_CENTER", "0") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _defaults() -> dict[str, Any]:
    """Safe baseline — every block degrades to this without changing the shape."""
    return {
        "ok": True,
        "at": _now_iso(),
        # nav-surface gate (CONTROL_CENTER flag) — frontend hides the page entry
        # when False. INERT default: the cockpit is opt-in until the flag is set.
        "nav_enabled": False,
        "headline": "",
        "problems": [],
        "metrics": {
            "staff": {"total": 0, "active": 0},
            "jobs": {"total": 0, "ok": 0, "issues": 0},
            "runs": {"total": 0, "running": 0},
            "queue": {"depth": 0, "dlq": 0},
            "heartbeat": {"up": 0, "total": 0},
            "llm": {"ok_rate": 0.0, "primary": "mistral"},
        },
        "staff": [],
        "jobs": [],
        "flags_off": [],
        "activation": {"ready_for_paid": False, "blockers": 0},
        "eval_gate": {"status": "neutral", "regression": False},
        # Provider chain order if cheaply available, else the live free-stack order.
        "providers": ["mistral", "groq", "cerebras", "gemini"],
        # Token/usage telemetry lives in budget_guard when LLM_BUDGET_GUARD=1.
        # Never fabricate ₹/$ — only tokens/calls. Filled in overview handler.
        "cost": {
            "available": False,
            "note": "set LLM_BUDGET_GUARD=1 to capture per-day token usage",
            "tokens_today": None,
            "calls_today": None,
            "budget_guard_enabled": False,
        },
    }


@router.get("/control-center/overview")
async def control_center_overview(_user=Depends(require_admin)) -> dict[str, Any]:
    """L1 Executive snapshot in one call. Never raises (partial data OK)."""
    out = _defaults()
    out["at"] = _now_iso()
    out["nav_enabled"] = _control_center_enabled()

    # ---- 1) today_overview: headline / problems / staff / jobs / flags_off / totals ----
    try:
        from app.platform import today_overview

        t = today_overview.build() or {}
        out["headline"] = t.get("headline") or ""
        out["problems"] = t.get("problems") or []
        staff = t.get("staff") or []
        jobs = t.get("jobs") or []
        out["staff"] = staff
        out["jobs"] = jobs
        out["flags_off"] = t.get("flags_off") or []
        totals = t.get("totals") or {}
        # staff.total from totals.staff (fallback len(staff)); active from totals.working.
        out["metrics"]["staff"]["total"] = int(totals.get("staff") or len(staff))
        out["metrics"]["staff"]["active"] = int(totals.get("working") or 0)
    except Exception:
        pass

    # ---- 2) automation_health: jobs rollup + queue + heartbeat ----
    try:
        from app.platform import automation_health

        h = automation_health.health() or {}
        hjobs = h.get("jobs") or []
        total = len(hjobs)
        ok = sum(1 for j in hjobs if j.get("status") == "ok")
        # issues = overdue + last_failed + never_ran-but-due. health() only emits
        # never_ran once a job is actually due (not-yet-due → scheduled_off), so a
        # plain status-set membership count is correct (no extra due-filter needed).
        issues = sum(1 for j in hjobs if j.get("status") in ("overdue", "last_failed", "never_ran"))
        out["metrics"]["jobs"] = {"total": total, "ok": ok, "issues": issues}

        q = h.get("queue") or {}
        queue_available = h.get("queue_available")
        if queue_available is None:
            queue_available = all(int(q.get(k, 0) or 0) >= 0 for k in ("celery", "dlq", "dead"))

        # Redis-unknown (-1) must NOT become 0 on the dashboard (ADR-114 false-green).
        def _q(key: str) -> int | None:
            v = int(q.get(key, -1) if q.get(key) is not None else -1)
            if not queue_available or v < 0:
                return None
            return v

        out["metrics"]["queue"] = {
            "depth": _q("celery"),
            "dlq": _q("dlq"),
            "dead": _q("dead"),
            "available": bool(queue_available),
        }
        # wiring gaps: flags ON but backend/creds missing — surfaced so Mission
        # Control can show "armed but unwired" instead of a false-green.
        out["wiring_gaps"] = h.get("wiring_gaps") or []
        # heartbeat: health() has no heartbeat object → derive. up = jobs that are
        # neither overdue nor never_ran (i.e. have a live recent beat).
        overdue = len(h.get("overdue") or [])
        never_ran = len(h.get("never_ran") or [])
        out["metrics"]["heartbeat"] = {
            "up": max(0, total - overdue - never_ran),
            "total": total,
        }
    except Exception:
        pass

    # ---- 3) llm_metrics: ok_rate + primary provider ----
    try:
        from app.platform import llm_metrics

        st = llm_metrics.stats(1000) or {}
        fb = float(st.get("fallback_or_fail_rate") or 0.0)
        out["metrics"]["llm"]["ok_rate"] = round(1.0 - fb, 2)
        provs = st.get("providers") or {}
        if isinstance(provs, dict) and provs:
            # most-used provider by call count
            primary = max(
                provs.items(),
                key=lambda kv: int((kv[1] or {}).get("calls", 0) or 0),
            )[0]
            out["metrics"]["llm"]["primary"] = str(primary) or "mistral"
    except Exception:
        pass

    # ---- 4) activation: ready_for_paid + blocker count (async helper, never-raises) ----
    try:
        from app.api.activation import get_activation_summary

        a = await get_activation_summary() or {}
        # ready_for_paid: prefer the paid-customer flag, fall back to launch-ready.
        ready = bool(
            a.get("ready_for_first_paid_customer")
            or a.get("production_ready")
            or a.get("ready_for_launch")
        )
        out["activation"] = {
            "ready_for_paid": ready,
            "blockers": int(a.get("blocker_count") or 0),
        }
    except Exception:
        pass

    # ---- 5) eval_gate: status + regression (derived from recent_decisions) ----
    try:
        from app.agents import eval_gate as _eval_gate

        s = _eval_gate.summary() or {}
        rec = s.get("recent_decisions") or {}
        rejects = int(rec.get("reject") or 0)
        enabled = bool(s.get("enabled"))
        regression = rejects > 0
        # green = recording on + no recent rejects; warn = recent rejects present;
        # neutral = not recording yet (observe-only / no baseline).
        if rejects:
            status = "warn"
        elif enabled:
            status = "green"
        else:
            status = "neutral"
        out["eval_gate"] = {"status": status, "regression": regression}
    except Exception:
        pass

    # ---- 6) runs: total + running (process/flow runs) ----
    try:
        from app.agents import flow_dispatch

        runs = flow_dispatch.list_runs(50) or []
        running = sum(1 for r in runs if r.get("status") == "running")
        out["metrics"]["runs"] = {"total": len(runs), "running": running}
    except Exception:
        pass

    # ---- 7) cost honesty — same source as /cost-rollup (no ₹/$ ever) ----
    try:
        from app.llm import budget_guard

        bg = await budget_guard.redis_stats() or {}
        enabled = bool(bg.get("enabled"))
        gtokens = int(bg.get("global_tokens") or 0)
        gcalls = int(bg.get("global_calls") or 0)
        out["cost"]["budget_guard_enabled"] = enabled
        if enabled:
            out["cost"]["tokens_today"] = gtokens
            out["cost"]["calls_today"] = gcalls
            if gtokens > 0:
                out["cost"]["available"] = True
                out["cost"]["note"] = ""
            else:
                out["cost"]["note"] = "LLM_BUDGET_GUARD on — aaj abhi 0 tokens captured"
        else:
            out["cost"]["note"] = "set LLM_BUDGET_GUARD=1 to capture per-day token usage"
    except Exception:
        pass

    return out


# --------------------------------------------------------------------------- #
# L4 — Agent Explorer: per-agent rollup (team_status + agent_events lifetime).
# --------------------------------------------------------------------------- #
@router.get("/control-center/agents/metrics")
async def control_center_agents_metrics(_user=Depends(require_admin)) -> dict[str, Any]:
    """Per-agent rollup for the L4 Agent Explorer. Never raises (safe empty default).

    Source: team.team_status() members (state/today_actions/last_activity) +
    a single lifetime group_by(member) count over the agent_events table for
    `events_total`. `avg_ms` is ALWAYS null — AgentEvent has no duration column,
    so we never fabricate it. `ok_rate` is lifetime non-error / total (null if
    no lifetime data). All DB work is in its own try/except; on any failure we
    fall back to whatever team_status() already exposes per member.
    """
    out: dict[str, Any] = {"ok": True, "at": _now_iso(), "agents": []}

    # 1) lifetime per-member totals + error counts (group_by; own try/except).
    lifetime_total: dict[str, int] = {}
    lifetime_errors: dict[str, int] = {}
    try:
        from sqlalchemy import func

        from app.models.agent_event import AgentEvent
        from app.platform import team as _team

        db = _team._db()
        if db is not None:
            try:
                rows = (
                    db.query(
                        AgentEvent.member,
                        func.count(AgentEvent.id),
                    )
                    .group_by(AgentEvent.member)
                    .all()
                )
                for member, cnt in rows:
                    lifetime_total[str(member or "system")] = int(cnt or 0)
                erows = (
                    db.query(
                        AgentEvent.member,
                        func.count(AgentEvent.id),
                    )
                    .filter(AgentEvent.status == "error")
                    .group_by(AgentEvent.member)
                    .all()
                )
                for member, cnt in erows:
                    lifetime_errors[str(member or "system")] = int(cnt or 0)
            finally:
                db.close()
    except Exception:
        pass

    # 2) team_status() members → per-agent shape (lazy module-attr call so tests
    #    can monkeypatch team.team_status to raise → still 200/ok).
    try:
        from app.platform import team as _team

        ts = _team.team_status() or {}
        for m in ts.get("members") or []:
            key = str(m.get("key") or "")
            le = m.get("last_activity") or {}
            today_actions = int(m.get("today_actions") or 0)
            # events_total: prefer lifetime group_by, fall back to today's count.
            ev_total = int(lifetime_total.get(key, today_actions))
            # ok_rate: prefer lifetime (non-error/total), else null (no fabrication).
            ok_rate: float | None = None
            if key in lifetime_total and lifetime_total[key] > 0:
                errs = int(lifetime_errors.get(key, 0))
                ok_rate = round(1.0 - (errs / lifetime_total[key]), 3)
            out["agents"].append(
                {
                    "key": key,
                    "name": str(m.get("name") or key.title()),
                    "emoji": str(m.get("emoji") or "🤖"),
                    # STAFF has no `role` field — its `title` IS the role.
                    "role": str(m.get("title") or ""),
                    "product": str(m.get("product") or "platform"),
                    "state": str(m.get("state") or "offline"),
                    "runs_today": today_actions,
                    "events_total": ev_total,
                    "ok_rate": ok_rate,
                    # AgentEvent has no ms/duration column → never fabricate.
                    "avg_ms": None,
                    "last_action": str((le or {}).get("action") or ""),
                    "last_event_ts": (le or {}).get("at"),
                }
            )
    except Exception:
        pass

    return out


# --------------------------------------------------------------------------- #
# L3 — Node-stats: cross-run slowest-node / timing rollup for the graph view.
# --------------------------------------------------------------------------- #
@router.get("/control-center/node-stats")
async def control_center_node_stats(_user=Depends(require_admin)) -> dict[str, Any]:
    """Fold per-node ms over the last N flow runs → slowest nodes (p50/p95).

    dag_engine records `ms` directly on each `node_completed` event, so we read
    that first; if absent we derive it from node_started.at ↔ node_completed.at
    deltas. flow_dispatch.journal() keys the per-run file by run_id only (both
    engines share the same path) so it reads dag + linear runs alike. If no run
    timings exist yet we return empty lists + an honest note. Never raises.
    """
    out: dict[str, Any] = {
        "ok": True,
        "at": _now_iso(),
        "slowest": [],
        "critical_path": [],
        "note": "no run timings yet",
    }
    try:
        from app.agents import flow_dispatch

        per_node_ms: dict[str, list[float]] = {}
        runs = flow_dispatch.list_runs(50) or []
        for r in runs:
            rid = str(r.get("run_id") or "")
            if not rid:
                continue
            try:
                evs = flow_dispatch.journal(rid, 500) or []
            except Exception:
                evs = []
            started_at: dict[str, str] = {}
            for ev in evs:
                etype = ev.get("type")
                data = ev.get("data") or {}
                node = str(data.get("node") or "")
                if not node:
                    continue
                if etype == "node_started":
                    started_at[node] = str(ev.get("at") or "")
                elif etype == "node_completed":
                    ms_val = data.get("ms")
                    ms: float | None = None
                    if ms_val is not None:
                        try:
                            ms = float(ms_val)
                        except Exception:
                            ms = None
                    # Fall back to started↔completed delta when ms absent.
                    if ms is None and started_at.get(node) and ev.get("at"):
                        ms = _iso_delta_ms(started_at[node], str(ev.get("at")))
                    if ms is not None and ms >= 0:
                        per_node_ms.setdefault(node, []).append(ms)

        slowest: list[dict[str, Any]] = []
        for node, samples in per_node_ms.items():
            if not samples:
                continue
            slowest.append(
                {
                    "node": node,
                    "p50_ms": int(_percentile(samples, 50)),
                    "p95_ms": int(_percentile(samples, 95)),
                    "runs": len(samples),
                }
            )
        slowest.sort(key=lambda d: d["p95_ms"], reverse=True)
        if slowest:
            out["slowest"] = slowest
            # critical_path = plain reading: nodes ordered by p50 desc. We can't
            # derive true DAG topology cross-run, so we say so in the note.
            out["critical_path"] = [
                d["node"] for d in sorted(slowest, key=lambda d: d["p50_ms"], reverse=True)
            ]
            out["note"] = "critical_path = nodes ranked by p50 (not DAG topology)"
    except Exception:
        pass

    return out


# --------------------------------------------------------------------------- #
# RCA — plain-Hinglish system-level root-cause findings.
# --------------------------------------------------------------------------- #
@router.get("/control-center/rca")
async def control_center_rca(_user=Depends(require_admin)) -> dict[str, Any]:
    """Join overdue jobs + LLM fallback-rate + queue/dlq depth + failed runs into
    plain-Hinglish root-cause findings. Empty findings when all healthy. Never raises."""
    out: dict[str, Any] = {"ok": True, "at": _now_iso(), "findings": []}
    findings: list[dict[str, Any]] = []

    # 1) automation_health: overdue jobs + queue/dlq backlog.
    try:
        from app.platform import automation_health

        h = automation_health.health() or {}
        overdue = h.get("overdue") or []
        if overdue:
            n = len(overdue)
            findings.append(
                {
                    "symptom": f"{n} job overdue ({', '.join(map(str, overdue[:3]))})",
                    "cause": "worker/scheduler container slow ya down",
                    "fix": "/app/ops me worker+scheduler restart karo (docker compose up -d)",
                    "severity": "high" if n >= 3 else "med",
                }
            )
        q = h.get("queue") or {}
        celery = max(0, int(q.get("celery", 0) or 0))
        dlq = max(0, int(q.get("dlq", 0) or 0))
        if celery > 500:
            findings.append(
                {
                    "symptom": f"celery queue {celery} tasks backlogged",
                    "cause": "worker keep-up nahi kar raha (concurrency kam ya stuck task)",
                    "fix": "redis-cli del celery (tasks regenerable) + worker recreate",
                    "severity": "high" if celery > 1000 else "med",
                }
            )
        if dlq > 0:
            findings.append(
                {
                    "symptom": f"{dlq} task DLQ me (dead-letter)",
                    "cause": "task repeatedly fail hua (retry exhaust)",
                    "fix": "Sat hygiene job DLQ trim karta; ya manually dlq:failed_tasks inspect karo",
                    "severity": "med" if dlq < 20 else "high",
                }
            )
        # ADR-104 Phase F (2026-07-15): dlq:dead (retry-exhausted, dlq_retry.py)
        # was never checked here, so "Koi problem nahi — sab theek" could show
        # on this exact page while dead tasks sat unaddressed. Reuse the
        # Phase B authoritative dead_tasks_present flag rather than
        # re-deriving another ad hoc dead>0 check.
        if h.get("dead_tasks_present"):
            dead = max(0, int(q.get("dead", 0) or 0))
            findings.append(
                {
                    "symptom": f"{dead} task(s) dead/exhausted (dlq:dead)",
                    "cause": "retry budget exhausted (dlq_retry.py auto-retry sweep gave up)",
                    "fix": "Reliability Console (/app/office#reliability) me inspect karo — manual retry ya root-cause fix chahiye",
                    "severity": "high" if dead >= 5 else "med",
                }
            )
    except Exception:
        pass

    # 2) llm_metrics: high fallback/fail rate.
    try:
        from app.platform import llm_metrics

        st = llm_metrics.stats(1000) or {}
        rate = float(st.get("fallback_or_fail_rate") or 0.0)
        total = int(st.get("total_calls") or 0)
        if total >= 30 and rate >= 0.4:
            findings.append(
                {
                    "symptom": f"LLM fallback/fail-rate {int(rate * 100)}% (last {total} calls)",
                    "cause": "free providers quota/TPD khatam (Groq/Gemini) — chain deep tak gir raha",
                    "fix": "1 headroom LLM key add karo (Groq Dev tier) ya provider keys rotate",
                    "severity": "high" if rate >= 0.6 else "med",
                }
            )
    except Exception:
        pass

    # 3) flow_dispatch: recent failed runs.
    try:
        from app.agents import flow_dispatch

        runs = flow_dispatch.list_runs(50) or []
        failed = [r for r in runs if r.get("status") == "failed"]
        if failed:
            n = len(failed)
            findings.append(
                {
                    "symptom": f"{n} flow-run failed (recent {len(runs)})",
                    "cause": "node gate-fail ya step exception (KB/LLM/integration down)",
                    "fix": "/app/automation me run journal dekho + failing node replay karo",
                    "severity": "med" if n < 5 else "high",
                }
            )
    except Exception:
        pass

    out["findings"] = findings
    return out


# --------------------------------------------------------------------------- #
# Cost-rollup — surfaces ALREADY-captured token/usage data (never fabricates).
# --------------------------------------------------------------------------- #
@router.get("/control-center/cost-rollup")
async def control_center_cost_rollup(_user=Depends(require_admin)) -> dict[str, Any]:
    """Honest token/usage view from EXISTING capture (no instrumentation added).

    Token data is captured by budget_guard.record() in free_ai — but ONLY when
    `LLM_BUDGET_GUARD=1` (off default → no counters). We READ those daily GLOBAL
    counters via budget_guard.redis_stats(); `available` is True only when the
    guard is enabled AND today's token total > 0. Per-provider CALL counts come
    from llm_metrics (calls ONLY — these are free providers, NEVER a $/₹ figure).
    All keys are initialised before the try blocks so a downstream raise still
    returns the full shape (never-raise). require_admin-gated."""
    out: dict[str, Any] = {
        "ok": True,
        "at": _now_iso(),
        "available": False,
        "note": ("instrument pending — set LLM_BUDGET_GUARD=1 to capture per-day token usage"),
        "tokens_today": None,
        "calls_today": None,
        "budget_guard_enabled": False,
        # Per-provider CALL counts only — free providers, NEVER a money figure.
        "by_provider": [],
    }

    # 1) budget_guard daily GLOBAL token/call counters (already captured when the
    #    guard flag is on). Module-attr call so tests can monkeypatch it to raise.
    try:
        from app.llm import budget_guard

        bg = await budget_guard.redis_stats() or {}
        enabled = bool(bg.get("enabled"))
        gtokens = int(bg.get("global_tokens") or 0)
        gcalls = int(bg.get("global_calls") or 0)
        out["budget_guard_enabled"] = enabled
        if enabled:
            out["tokens_today"] = gtokens
            out["calls_today"] = gcalls
            if gtokens > 0:
                out["available"] = True
                out["note"] = ""
    except Exception:
        pass

    # 2) llm_metrics per-provider call counts (calls ONLY — no money figure).
    try:
        from app.platform import llm_metrics

        st = llm_metrics.stats(1000) or {}
        provs = st.get("providers") or {}
        if isinstance(provs, dict):
            by_provider = [
                {"provider": str(p), "calls": int((v or {}).get("calls", 0) or 0)}
                for p, v in provs.items()
            ]
            by_provider.sort(key=lambda d: d["calls"], reverse=True)
            out["by_provider"] = by_provider
    except Exception:
        pass

    return out


# --------------------------------------------------------------------------- #
# Route-hits — "unused API / dead route" view (reads RouteHitMiddleware data).
# --------------------------------------------------------------------------- #
@router.get("/control-center/route-hits")
async def control_center_route_hits(_user=Depends(require_admin)) -> dict[str, Any]:
    """Top hit routes today, from the Redis hash `route_hits:{YYYYMMDD}` that
    RouteHitMiddleware populates (GATED `ROUTE_HIT_COUNTER=1`). Honest empty
    state when the flag is off or no data captured yet. Never raises;
    require_admin-gated."""
    enabled = os.getenv("ROUTE_HIT_COUNTER", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    out: dict[str, Any] = {
        "ok": True,
        "at": _now_iso(),
        "enabled": enabled,
        "note": "" if enabled else "enable ROUTE_HIT_COUNTER=1 to track",
        "top": [],
        "total_paths": 0,
    }
    if not enabled:
        return out
    try:
        from app.cache import get_redis_client

        r = await get_redis_client()
        # UTC day key — MUST match RouteHitMiddleware._record (time.gmtime()).
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        raw = await r.hgetall(f"route_hits:{day}") or {}
        rows = []
        for path, hits in (raw or {}).items():
            try:
                rows.append({"path": str(path), "hits": int(hits or 0)})
            except Exception:
                pass
        rows.sort(key=lambda d: d["hits"], reverse=True)
        out["top"] = rows[:20]
        out["total_paths"] = len(rows)
    except Exception:
        pass

    return out


def _iso_delta_ms(a: str, b: str) -> float | None:
    """Milliseconds between two ISO timestamps (b - a), or None if unparseable."""
    try:
        da = datetime.fromisoformat(str(a).replace("Z", "+00:00"))
        db = datetime.fromisoformat(str(b).replace("Z", "+00:00"))
        return max(0.0, (db - da).total_seconds() * 1000.0)
    except Exception:
        return None


def _percentile(samples: list[float], pct: float) -> float:
    """Nearest-rank percentile of a non-empty list. Safe on tiny samples."""
    if not samples:
        return 0.0
    s = sorted(samples)
    if len(s) == 1:
        return s[0]
    k = (pct / 100.0) * (len(s) - 1)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] + (s[hi] - s[lo]) * frac


__all__ = ["router"]
