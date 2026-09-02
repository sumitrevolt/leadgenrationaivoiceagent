"""Tests for the Control Center L1 aggregator (/api/control-center/overview).

The top-level tests/conftest.py already overrides require_admin with a mock
super-admin user, so a plain TestClient(app) is authenticated. We also set an
explicit override (test_flow_api.py style) so this file is self-contained.
"""

from fastapi.testclient import TestClient


def _client():
    from app.api import auth_deps
    from app.main import app

    app.dependency_overrides[auth_deps.require_admin] = lambda: type("U", (), {"email": "t@t"})()
    return TestClient(app)


def test_overview_returns_full_contract():
    """200 + every contract key present; cost never fabricates ₹/$ (tokens only)."""
    c = _client()
    r = c.get("/api/control-center/overview")
    assert r.status_code == 200
    body = r.json()
    for key in (
        "ok",
        "metrics",
        "staff",
        "jobs",
        "problems",
        "activation",
        "eval_gate",
        "cost",
        "nav_enabled",
    ):
        assert key in body, f"missing top-level key: {key}"
    assert body["ok"] is True
    # Without LLM_BUDGET_GUARD + tokens, available stays False — never a money figure.
    cost = body["cost"]
    assert "available" in cost and "note" in cost
    assert "instrument pending" not in str(cost.get("note") or "").lower()
    if not cost.get("budget_guard_enabled"):
        assert cost["available"] is False
    # metrics sub-shape the frontend depends on
    m = body["metrics"]
    for sub in ("staff", "jobs", "runs", "queue", "heartbeat", "llm"):
        assert sub in m, f"missing metrics.{sub}"
    assert "ok_rate" in m["llm"] and "primary" in m["llm"]
    assert isinstance(body["providers"], list) and body["providers"]


def test_never_raises_when_today_overview_breaks(monkeypatch):
    """If a downstream fan-in module raises, the endpoint still returns 200/ok=true
    with the contract shape intact (partial degradation, never a 500)."""
    import app.platform.today_overview as today_overview

    def _boom():
        raise RuntimeError("today_overview exploded")

    monkeypatch.setattr(today_overview, "build", _boom)

    c = _client()
    r = c.get("/api/control-center/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    # degraded-but-shaped: today_overview-sourced keys fall back to safe defaults
    assert body["headline"] == ""
    assert body["staff"] == []
    assert body["problems"] == []
    # unaffected blocks + envelope still present
    assert "metrics" in body and "cost" in body
    assert body["cost"]["available"] is False


# --------------------------------------------------------------------------- #
# New L3/L4 read-side endpoints (agents/metrics · node-stats · rca · cost-rollup)
# --------------------------------------------------------------------------- #
def test_agents_metrics_contract():
    """200 + per-agent shape the L4 Agent Explorer consumes; avg_ms always null
    (no duration column → never fabricated)."""
    c = _client()
    r = c.get("/api/control-center/agents/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "at" in body and isinstance(body["agents"], list)
    if body["agents"]:
        a = body["agents"][0]
        for key in (
            "key",
            "name",
            "emoji",
            "role",
            "product",
            "state",
            "runs_today",
            "events_total",
            "ok_rate",
            "avg_ms",
            "last_action",
            "last_event_ts",
        ):
            assert key in a, f"missing agents[].{key}"
        assert a["avg_ms"] is None  # no duration telemetry — never fabricated
        assert a["state"] in ("working", "active", "offline")


def test_node_stats_and_cost_rollup_contracts():
    """node-stats returns the slowest/critical_path/note shape; cost-rollup is
    HONEST (available=False, no money figure, calls-only by_provider)."""
    c = _client()
    r = c.get("/api/control-center/node-stats")
    assert r.status_code == 200
    ns = r.json()
    assert ns["ok"] is True
    for key in ("at", "slowest", "critical_path", "note"):
        assert key in ns
    assert isinstance(ns["slowest"], list) and isinstance(ns["critical_path"], list)

    r2 = c.get("/api/control-center/cost-rollup")
    assert r2.status_code == 200
    cr = r2.json()
    assert cr["ok"] is True
    # cost is ALWAYS unavailable — never fabricate a money figure.
    assert cr["available"] is False
    assert isinstance(cr["by_provider"], list)
    for row in cr["by_provider"]:
        assert set(row.keys()) == {"provider", "calls"}  # calls only, no money


def test_rca_contract_and_never_raises(monkeypatch):
    """rca returns findings[] (each plain-Hinglish) AND stays 200 even when a
    source (automation_health.health) raises — partial degradation, never 500."""
    c = _client()
    r = c.get("/api/control-center/rca")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and isinstance(body["findings"], list)
    for f in body["findings"]:
        for key in ("symptom", "cause", "fix", "severity"):
            assert key in f
        assert f["severity"] in ("high", "med", "low")

    # never-raise: monkeypatch a source to explode → endpoint still 200/ok.
    import app.platform.automation_health as automation_health

    def _boom():
        raise RuntimeError("automation_health exploded")

    monkeypatch.setattr(automation_health, "health", _boom)
    r2 = c.get("/api/control-center/rca")
    assert r2.status_code == 200
    assert r2.json()["ok"] is True


def test_node_stats_folds_synthetic_timings(monkeypatch):
    """Exercise the populated branch: with synthetic runs+journal, slowest must
    populate with int p50/p95, critical_path non-empty, note flipped off the
    empty default. Covers _percentile + data.ms extraction (no real runs exist)."""
    import app.agents.flow_dispatch as flow_dispatch

    monkeypatch.setattr(
        flow_dispatch, "list_runs", lambda n=50: [{"run_id": "r1"}, {"run_id": "r2"}]
    )

    def _journal(run_id, limit=100):
        # two nodes across runs; 'scrape' clearly slowest → must rank first.
        return [
            {
                "type": "node_completed",
                "data": {"node": "scrape", "ms": 1200},
                "at": "2026-06-28T10:00:00+00:00",
            },
            {
                "type": "node_completed",
                "data": {"node": "scrape", "ms": 1400},
                "at": "2026-06-28T10:00:02+00:00",
            },
            {
                "type": "node_completed",
                "data": {"node": "email", "ms": 200},
                "at": "2026-06-28T10:00:03+00:00",
            },
        ]

    monkeypatch.setattr(flow_dispatch, "journal", _journal)

    c = _client()
    r = c.get("/api/control-center/node-stats")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["slowest"], "slowest must populate from synthetic timings"
    top = body["slowest"][0]
    assert top["node"] == "scrape"  # ranked by p95 desc
    assert isinstance(top["p50_ms"], int) and isinstance(top["p95_ms"], int)
    assert top["runs"] >= 1
    assert body["critical_path"]  # non-empty
    assert body["note"] != "no run timings yet"


def test_node_stats_falls_back_to_started_completed_delta(monkeypatch):
    """When node_completed has no ms, derive it from node_started.at ↔ completed.at."""
    import app.agents.flow_dispatch as flow_dispatch

    monkeypatch.setattr(flow_dispatch, "list_runs", lambda n=50: [{"run_id": "r1"}])

    def _journal(run_id, limit=100):
        return [
            {"type": "node_started", "data": {"node": "slow"}, "at": "2026-06-28T10:00:00+00:00"},
            {"type": "node_completed", "data": {"node": "slow"}, "at": "2026-06-28T10:00:03+00:00"},
        ]

    monkeypatch.setattr(flow_dispatch, "journal", _journal)

    c = _client()
    r = c.get("/api/control-center/node-stats")
    assert r.status_code == 200
    body = r.json()
    assert body["slowest"], "delta-derived timing must populate slowest"
    # 3-second delta → ~3000ms
    assert body["slowest"][0]["p50_ms"] >= 2900


def test_agents_metrics_never_raises_when_team_status_breaks(monkeypatch):
    """If team.team_status() raises, agents/metrics still returns 200/ok with a
    safe empty agents list (the lazy module-attr call is patchable)."""
    import app.platform.team as team

    def _boom():
        raise RuntimeError("team_status exploded")

    monkeypatch.setattr(team, "team_status", _boom)

    c = _client()
    r = c.get("/api/control-center/agents/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["agents"] == []  # degraded-but-shaped


# --------------------------------------------------------------------------- #
# P4: cost-rollup surfaces REAL captured token data · route-hits read endpoint.
# --------------------------------------------------------------------------- #
def test_cost_rollup_new_contract_keys():
    """cost-rollup exposes the budget_guard-sourced keys. With LLM_BUDGET_GUARD
    off (test default) `available` stays False and tokens/calls are null — but
    the keys are always present, and by_provider rows are calls-only (no money)."""
    c = _client()
    r = c.get("/api/control-center/cost-rollup")
    assert r.status_code == 200
    cr = r.json()
    assert cr["ok"] is True
    for key in (
        "at",
        "available",
        "note",
        "tokens_today",
        "calls_today",
        "budget_guard_enabled",
        "by_provider",
    ):
        assert key in cr, f"missing cost-rollup key: {key}"
    # guard off by default → not available, honest null counters, instrument note.
    assert cr["available"] is False
    assert cr["tokens_today"] is None and cr["calls_today"] is None
    assert cr["budget_guard_enabled"] is False
    assert "LLM_BUDGET_GUARD" in cr["note"]
    assert isinstance(cr["by_provider"], list)
    for row in cr["by_provider"]:
        assert set(row.keys()) == {"provider", "calls"}  # calls only, never money


def test_cost_rollup_never_raises_when_budget_guard_breaks(monkeypatch):
    """If budget_guard.redis_stats raises, cost-rollup still returns 200/ok with
    the full key shape intact (defaults-before-try → never a 500)."""
    import app.llm.budget_guard as budget_guard

    async def _boom():
        raise RuntimeError("budget_guard exploded")

    monkeypatch.setattr(budget_guard, "redis_stats", _boom)

    c = _client()
    r = c.get("/api/control-center/cost-rollup")
    assert r.status_code == 200
    cr = r.json()
    assert cr["ok"] is True
    # degraded-but-shaped: all keys present, available falls back to False.
    for key in (
        "available",
        "tokens_today",
        "calls_today",
        "budget_guard_enabled",
        "by_provider",
    ):
        assert key in cr
    assert cr["available"] is False


def test_route_hits_contract_disabled_by_default():
    """route-hits returns 200 + contract keys; with ROUTE_HIT_COUNTER off (test
    default) it reports enabled:false + an honest enable-note + empty top/total."""
    c = _client()
    r = c.get("/api/control-center/route-hits")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    for key in ("at", "enabled", "note", "top", "total_paths"):
        assert key in body, f"missing route-hits key: {key}"
    assert body["enabled"] is False
    assert "ROUTE_HIT_COUNTER" in body["note"]
    assert body["top"] == [] and body["total_paths"] == 0


# --------------------------------------------------------------------------- #
# ADR-104 Phase F (2026-07-15): overview.metrics.queue and rca.findings used to
# drop dlq:dead (retry-exhausted) entirely -- a customer/admin could see
# "DLQ 0 · Queue clean" / no findings on THIS exact page while the Reliability
# Console (same automation_health.health() snapshot) correctly showed dead
# tasks. Both fixed to read q.get("dead") / h.get("dead_tasks_present").
# --------------------------------------------------------------------------- #
def test_overview_queue_metrics_include_dead_count(monkeypatch):
    import app.platform.automation_health as automation_health

    def _health():
        return {
            "jobs": [],
            "overdue": [],
            "never_ran": [],
            "queue": {"celery": 0, "heavy": 0, "dlq": 0, "dead": 4},
            "queue_backlogged": False,
            "dead_tasks_present": True,
            "retryable_failed_present": False,
        }

    monkeypatch.setattr(automation_health, "health", _health)
    c = _client()
    r = c.get("/api/control-center/overview")
    assert r.status_code == 200
    q = r.json()["metrics"]["queue"]
    assert "dead" in q, "metrics.queue must expose dead (retry-exhausted) count"
    assert q["dead"] == 4
    assert q["dlq"] == 0  # confirms this isn't just dlq renamed -- both present


def test_rca_findings_surface_dead_tasks_even_when_dlq_is_zero(monkeypatch):
    import app.platform.automation_health as automation_health

    def _health():
        return {
            "jobs": [],
            "overdue": [],
            "never_ran": [],
            "queue": {"celery": 0, "heavy": 0, "dlq": 0, "dead": 4},
            "queue_backlogged": False,
            "dead_tasks_present": True,
            "retryable_failed_present": False,
        }

    monkeypatch.setattr(automation_health, "health", _health)
    c = _client()
    r = c.get("/api/control-center/rca")
    assert r.status_code == 200
    findings = r.json()["findings"]
    dead_findings = [f for f in findings if "dead" in f["symptom"] or "exhausted" in f["symptom"]]
    assert dead_findings, f"expected a dead/exhausted finding, got: {findings}"
    assert dead_findings[0]["severity"] in ("high", "med")
