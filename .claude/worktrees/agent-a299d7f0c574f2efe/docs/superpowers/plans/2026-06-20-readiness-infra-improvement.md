# Readiness + Infra Improvement (Track B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the four genuine product-readiness gaps (revenue time-series, per-client activity timeline, system-health drill-down, customer inline lead-status edit) as flag-gated, additive, defensive features without touching saturated infra.

**Architecture:** Additive routes on existing FastAPI routers + small append-only JSONL stores in `data/`, surfaced as new sections inside existing HTML pages (`admin_dashboard.html`, `customer_dashboard.html`). No new page-routes, no new heavy deps. Each backend feature is flag-gated and returns a safe `{enabled: false}` shape when off. Parallel-safe: work is split into waves so no two parallel workers edit the same file.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy (existing models), Chart.js (already CDN-loaded in `admin_dashboard.html`), pytest + `fastapi.testclient.TestClient`.

## Global Constraints

- **Free stack only** — no paid/new third-party deps. Reuse existing libs (Chart.js already loaded; no psutil-new — reuse `app/api/health.py` probes).
- **Flag idiom (verbatim):** `os.getenv("FLAG_NAME", "0").strip().lower() in ("1", "true", "yes")`. No `_flag()` helper exists; inline it.
- **Flags OFF by default**, and every new flag string is registered in `app/api/growth.py` `AUTOMATION_FLAGS` (so it shows in `GET /api/growth/infra/flags`).
- **Additive only** — do not rewrite working code; match neighbouring conventions (`.card .hd .bd` CSS, `abAuthHdr()` fetch, `escH()` escaping).
- **No new `@app.get` page-routes** — all UI lands as sections inside existing pages (avoids stale-`.pyc` hard-reload).
- **New admin endpoints** must take `_user=Depends(require_admin)` (`app/api/auth_deps.py:94`).
- **Customer mutations** must be IDOR-safe via `_authed_client_id` (`app/api/billing.py:63`).
- **Hot-path endpoints** (system-health) use only O(1) reads (psutil-equivalent already in health.py, file read, `redis.llen`) — NO KB/ML/network/DB-heavy work (3 prod-downs came from heavy work on hot paths).
- **Defensive:** every handler wrapped so it never 500s — on error return a safe shape with an `error` string.
- **Source-of-truth = Windows files;** Read a file immediately before editing it (sandbox mount goes stale).
- **Secrets only in `.env`;** run `python scripts/check_secrets.py` before every commit.
- **Windows git:** `C:\PROGRA~1\Git\cmd\git.exe`. Every commit message ends with the trailer:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- **Branch:** `feature/readiness-infra-2026-06-20` (already created).
- **Parallel waves:** Wave 1 tasks (1–4) touch disjoint files → may run concurrently. Wave 2 (tasks 5–7) all edit `admin_dashboard.html` → MUST run serially, one owner. Wave 3 (task 8) edits shared config. Task 9 = verification.

---

## File Structure

| File | New/Modify | Responsibility |
|---|---|---|
| `app/platform/revenue_snapshots.py` | Create | B1: daily MRR snapshot store + read + backfill-estimate |
| `app/api/admin_dashboard.py` | Modify | B1 `/revenue-trend` + B2 `/clients/{id}/timeline` routes |
| `app/api/system_health.py` | Create | B3 `/system-health-detail` route module |
| `app/api/customer_dashboard.py` | Modify | B4 `LeadRow.id`, override read-merge, `PATCH /api/customer/leads/{id}` |
| `app/platform/lead_overrides.py` | Create | B4 override store (read/append) |
| `frontend/admin_dashboard.html` | Modify | B1 trend chart, B2 timeline drawer, B3 health gauges (Wave 2, serial) |
| `frontend/customer_dashboard.html` | Modify | B4 inline status `<select>` |
| `app/api/growth.py` | Modify | register `REVENUE_TRENDS`, `CLIENT_TIMELINE`, `SYS_HEALTH_DETAIL` |
| `app/platform/team_scheduler.py` | Modify | wire daily `revenue_snapshot` job + boot-grace |
| `app/main.py` | Modify | mount new `system_health` router |
| `tests/test_readiness_infra_b1.py` … `_b4.py` | Create | per-feature tests |

---

## Task 1: B1 — Revenue snapshot store + `/revenue-trend` endpoint

**Files:**
- Create: `app/platform/revenue_snapshots.py`
- Create: `tests/test_readiness_infra_b1.py`
- Modify: `app/api/admin_dashboard.py` (add `/revenue-trend` route near `:1049`)

**Interfaces:**
- Produces:
  - `async def snapshot_today() -> dict` — collects + appends today's row; returns the row `{date, mrr, active, churn_pct, ltv}`.
  - `def read_trend(days: int = 90, clients: list[dict] | None = None) -> list[dict]` — real snapshots (latest-per-date) merged over estimate; each point `{date, mrr, active, churn_pct, ltv, estimated: bool}`, ascending by date.
  - Route `GET /api/admin/revenue-trend?days=90` → `{enabled: bool, points: list, note: str}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_readiness_infra_b1.py
import json, os
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_snapshot_roundtrip(tmp_path, monkeypatch):
    from app.platform import revenue_snapshots as rs
    f = tmp_path / "revenue_snapshots.jsonl"
    monkeypatch.setattr(rs, "_SNAP_FILE", str(f))
    rs._append_row({"date": "2026-06-19", "mrr": 1000, "active": 2, "churn_pct": 0.0, "ltv": 6000})
    rs._append_row({"date": "2026-06-20", "mrr": 1200, "active": 3, "churn_pct": 5.0, "ltv": 4800})
    pts = rs.read_trend(days=30)
    assert [p["date"] for p in pts] == ["2026-06-19", "2026-06-20"]
    assert pts[-1]["mrr"] == 1200
    assert pts[-1]["estimated"] is False


def test_estimate_curve_from_clients(tmp_path, monkeypatch):
    from app.platform import revenue_snapshots as rs
    monkeypatch.setattr(rs, "_SNAP_FILE", str(tmp_path / "none.jsonl"))
    clients = [
        {"created_at": "2026-06-01", "plan_price_inr": 2999, "status": "active"},
        {"created_at": "2026-06-10", "plan_price_inr": 1199, "status": "active"},
    ]
    pts = rs.read_trend(days=30, clients=clients)
    assert len(pts) >= 1
    assert all(p["estimated"] for p in pts)
    assert pts[-1]["mrr"] >= 2999  # both clients counted by today


def test_revenue_trend_endpoint_flag_off(monkeypatch):
    monkeypatch.delenv("REVENUE_TRENDS", raising=False)
    r = client.get("/api/admin/revenue-trend?days=30")
    assert r.status_code == 200
    assert r.json()["enabled"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_readiness_infra_b1.py -v`
Expected: FAIL — `ModuleNotFoundError: app.platform.revenue_snapshots` / 404 on route.

- [ ] **Step 3: Create the snapshot store module**

```python
# app/platform/revenue_snapshots.py
"""B1 — daily MRR/churn/LTV snapshots (append-only) + backfill estimate.

Real history grows one row/day via the scheduled `revenue_snapshot` job.
Before the first snapshot exists we reconstruct an *approximate* curve from
client start-dates + plan price (clearly marked estimated=True).
Defensive: never raises on read.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_SNAP_FILE = os.path.join("data", "revenue_snapshots.jsonl")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _append_row(row: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(_SNAP_FILE) or ".", exist_ok=True)
        with open(_SNAP_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception as e:  # never raise
        logger.warning("revenue_snapshots append failed: %s", e)
        return False


def _read_rows() -> list[dict]:
    out: list[dict] = []
    try:
        if not os.path.isfile(_SNAP_FILE):
            return out
        with open(_SNAP_FILE, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                    if isinstance(rec, dict) and rec.get("date"):
                        out.append(rec)
                except Exception:
                    continue
    except Exception as e:
        logger.debug("revenue_snapshots read failed: %s", e)
    return out


async def snapshot_today() -> dict:
    """Collect current revenue stats and append one row for today (idempotent
    per-day on read: latest write for a date wins)."""
    row = {"date": _today(), "mrr": 0, "active": 0, "churn_pct": 0.0, "ltv": 0}
    try:
        from app.platform import client_health, revenue_digest

        stats = await revenue_digest._collect()
        subs = stats.get("subscriptions") or {}
        mrr = int(stats.get("mrr") or 0)
        active = int(subs.get("active") or 0)
        health = await client_health.health_report()
        total = len(health) or 1
        reds = sum(1 for h in health if h.get("band") == "red")
        yellows = sum(1 for h in health if h.get("band") == "yellow")
        row.update(
            mrr=mrr,
            active=active,
            churn_pct=round((reds + yellows) / total * 100, 1),
            ltv=int(mrr * 12 / max(1, active or total)),
        )
    except Exception as e:
        logger.warning("snapshot_today collect failed: %s", e)
        row["error"] = str(e)[:120]
    _append_row(row)
    return row


def _load_clients() -> list[dict]:
    try:
        from app.platform import clients_store

        return clients_store.all_clients()  # list[dict] with created_at + plan
    except Exception:
        return []


def _client_price(c: dict) -> int:
    for k in ("plan_price_inr", "price_inr", "mrr"):
        v = c.get(k)
        if v:
            try:
                return int(v)
            except Exception:
                continue
    return 0


def _estimate_curve(days: int, clients: list[dict]) -> list[dict]:
    """Approx MRR per day = sum(price for clients started on/before that day)."""
    pts: list[dict] = []
    today = datetime.now(timezone.utc).date()
    parsed = []
    for c in clients:
        ca = str(c.get("created_at") or "")[:10]
        try:
            d = datetime.strptime(ca, "%Y-%m-%d").date()
        except Exception:
            continue
        parsed.append((d, _client_price(c)))
    if not parsed:
        return pts
    for i in range(days - 1, -1, -1):
        day = today - timedelta(days=i)
        mrr = sum(p for (d, p) in parsed if d <= day)
        active = sum(1 for (d, _) in parsed if d <= day)
        if active == 0:
            continue
        pts.append({
            "date": day.strftime("%Y-%m-%d"),
            "mrr": mrr,
            "active": active,
            "churn_pct": 0.0,
            "ltv": int(mrr * 12 / max(1, active)),
            "estimated": True,
        })
    return pts


def read_trend(days: int = 90, clients: list[dict] | None = None) -> list[dict]:
    """Real snapshots (latest-per-date) override the estimate curve."""
    days = max(1, min(int(days or 90), 365))
    if clients is None:
        clients = _load_clients()
    by_date: dict[str, dict] = {}
    for p in _estimate_curve(days, clients):
        by_date[p["date"]] = p
    for r in _read_rows():  # later real rows overwrite estimate + earlier rows
        d = str(r.get("date"))[:10]
        by_date[d] = {
            "date": d,
            "mrr": int(r.get("mrr") or 0),
            "active": int(r.get("active") or 0),
            "churn_pct": float(r.get("churn_pct") or 0.0),
            "ltv": int(r.get("ltv") or 0),
            "estimated": False,
        }
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days)).strftime("%Y-%m-%d")
    return sorted((p for d, p in by_date.items() if d >= cutoff), key=lambda x: x["date"])
```

> If `clients_store.all_clients()` does not exist, in Step 3 replace `_load_clients` body to read `data/clients.json` directly the same parse-safe way; the estimate is best-effort and may return `[]`. Verify the real symbol with `grep -n "def all_clients\|def list_clients" app/platform/clients_store.py` before finalizing.

- [ ] **Step 4: Add the endpoint to `admin_dashboard.py`**

Insert immediately after the `get_revenue_analytics` function (after line ~1049):

```python
@router.get("/revenue-trend")
async def get_revenue_trend(days: int = 90, _user=Depends(require_admin)) -> dict:
    """B1: MRR/churn/LTV time-series for the admin revenue chart. Flag-gated."""
    if os.getenv("REVENUE_TRENDS", "0").strip().lower() not in ("1", "true", "yes"):
        return {"enabled": False, "points": [], "note": "REVENUE_TRENDS off"}
    try:
        from app.platform import revenue_snapshots

        pts = revenue_snapshots.read_trend(days=days)
        return {"enabled": True, "points": pts, "note": ""}
    except Exception as e:
        logger.warning("admin_dashboard: revenue-trend failed (%s)", e)
        return {"enabled": True, "points": [], "note": str(e)[:160]}
```

Confirm `os` and `require_admin` are already imported at the top of `admin_dashboard.py` (they are — `activity-feed` uses both). If `os` is missing, add `import os`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_readiness_infra_b1.py -v`
Expected: PASS (3 tests). If `clients_store.all_clients` differs, the estimate test may need the fallback from Step 3's note.

- [ ] **Step 6: Commit**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add app/platform/revenue_snapshots.py app/api/admin_dashboard.py tests/test_readiness_infra_b1.py
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(admin): B1 revenue time-series snapshot store + /revenue-trend (flag REVENUE_TRENDS)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: B2 — Per-client activity timeline endpoint

**Files:**
- Modify: `app/api/admin_dashboard.py` (add `/clients/{client_id}/timeline` after Task 1's route)
- Create: `tests/test_readiness_infra_b2.py`

**Interfaces:**
- Produces: `GET /api/admin/clients/{client_id}/timeline?limit=50` → `{enabled: bool, client_id: str, events: list}`. Each event `{ts: str, kind: str, source: str, summary: str}`, newest-first.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_readiness_infra_b2.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_timeline_flag_off(monkeypatch):
    monkeypatch.delenv("CLIENT_TIMELINE", raising=False)
    r = client.get("/api/admin/clients/abc/timeline")
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_timeline_aggregator_merges_and_sorts():
    from app.api.admin_dashboard import _build_client_timeline
    events = _build_client_timeline(
        client_id="c1",
        agent_events=[{"at": "2026-06-20T10:00:00", "member": "neha", "action": "rescore", "detail": "", "meta": {"client_id": "c1"}}],
        inquiries=[{"id": "i1", "client_id": "c1", "name": "Ravi", "ts": "2026-06-20T09:00:00"}],
        audit=[{"created_at": "2026-06-20T11:00:00", "action": "impersonate.start", "resource_id": "c1"}],
        limit=50,
    )
    # newest first
    assert [e["ts"][:16] for e in events] == ["2026-06-20T11:00", "2026-06-20T10:00", "2026-06-20T09:00"]
    assert {e["source"] for e in events} == {"audit", "agent", "lead"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_readiness_infra_b2.py -v`
Expected: FAIL — `ImportError: cannot import name '_build_client_timeline'` / 404.

- [ ] **Step 3: Add the pure aggregator + route to `admin_dashboard.py`**

```python
def _build_client_timeline(client_id, agent_events, inquiries, audit, limit=50):
    """Pure merge+sort of per-client events from 3 sources. Newest first."""
    items: list[dict] = []
    for ev in agent_events or []:
        meta = ev.get("meta") or {}
        if str(meta.get("client_id") or "") != str(client_id):
            continue
        items.append({
            "ts": str(ev.get("at") or ""),
            "kind": str(ev.get("action") or "event"),
            "source": "agent",
            "summary": f"{ev.get('member','')}: {(ev.get('detail') or '')[:120]}".strip(": "),
        })
    for r in inquiries or []:
        if str(r.get("client_id") or "") != str(client_id):
            continue
        items.append({
            "ts": str(r.get("ts") or r.get("created_at") or ""),
            "kind": "lead",
            "source": "lead",
            "summary": f"Enquiry from {r.get('name') or '-'}",
        })
    for a in audit or []:
        if str(a.get("resource_id") or "") != str(client_id):
            continue
        items.append({
            "ts": str(a.get("created_at") or ""),
            "kind": str(a.get("action") or "audit"),
            "source": "audit",
            "summary": str(a.get("action") or ""),
        })
    items.sort(key=lambda x: x["ts"], reverse=True)
    return items[: max(1, min(int(limit), 200))]


@router.get("/clients/{client_id}/timeline")
async def get_client_timeline(client_id: str, limit: int = 50, _user=Depends(require_admin)) -> dict:
    """B2: unified per-client event trail (agent_events + inquiries + audit)."""
    if os.getenv("CLIENT_TIMELINE", "0").strip().lower() not in ("1", "true", "yes"):
        return {"enabled": False, "client_id": client_id, "events": []}
    agent_events: list = []
    inquiries: list = []
    audit: list = []
    try:
        from app.platform.team import recent_events
        agent_events = recent_events(limit=200)
    except Exception:
        pass
    try:
        from app.api.customer_dashboard import _read_inquiries
        inquiries = _read_inquiries()
    except Exception:
        pass
    try:
        from app.api.admin import _recent_audit_logs  # if present; else skip
        audit = _recent_audit_logs(limit=200)
    except Exception:
        audit = []
    events = _build_client_timeline(client_id, agent_events, inquiries, audit, limit)
    return {"enabled": True, "client_id": client_id, "events": events}
```

> The audit import is best-effort: verify the real audit-fetch symbol with `grep -n "audit" app/api/admin.py`. If there is no reusable function, leave `audit = []` (the timeline still works from agent_events + inquiries). Do NOT add a new query — keep this endpoint cheap.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_readiness_infra_b2.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add app/api/admin_dashboard.py tests/test_readiness_infra_b2.py
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(admin): B2 per-client activity timeline endpoint (flag CLIENT_TIMELINE)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: B3 — System-health drill-down endpoint

**Files:**
- Create: `app/api/system_health.py`
- Modify: `app/main.py` (mount router)
- Create: `tests/test_readiness_infra_b3.py`

**Interfaces:**
- Produces: `GET /api/admin/system-health-detail` → `{enabled, cpu_pct, mem_pct, disk_pct, redis_ping_ms, celery_queue_depth, worker_alive, health_ready}`. Never 500; missing data → safe sentinels (`-1` / `"unknown"`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_readiness_infra_b3.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_detail_flag_off(monkeypatch):
    monkeypatch.delenv("SYS_HEALTH_DETAIL", raising=False)
    r = client.get("/api/admin/system-health-detail")
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_health_detail_shape(monkeypatch):
    monkeypatch.setenv("SYS_HEALTH_DETAIL", "1")
    r = client.get("/api/admin/system-health-detail")
    assert r.status_code == 200
    d = r.json()
    for k in ("cpu_pct", "mem_pct", "disk_pct", "redis_ping_ms",
              "celery_queue_depth", "worker_alive", "health_ready"):
        assert k in d
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_readiness_infra_b3.py -v`
Expected: FAIL — 404 (route not mounted).

- [ ] **Step 3: Create the router module**

```python
# app/api/system_health.py
"""B3 — system-health drill-down for the admin dashboard. Flag-gated.

HOT-PATH RULE: O(1) reads only (resource probes already used by /health,
one redis llen, one heartbeat-file read). No KB/ML/network/DB-heavy work.
Never raises.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends

from app.api.auth_deps import require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["Infrastructure"])


def _resources() -> dict:
    """Reuse psutil the same way /health does; degrade to -1 on any failure."""
    out = {"cpu_pct": -1.0, "mem_pct": -1.0, "disk_pct": -1.0}
    try:
        import psutil  # already a dep (health.py uses it)
        out["cpu_pct"] = round(psutil.cpu_percent(interval=0.0), 1)
        out["mem_pct"] = round(psutil.virtual_memory().percent, 1)
        out["disk_pct"] = round(psutil.disk_usage("/").percent, 1)
    except Exception as e:
        logger.debug("system_health resources failed: %s", e)
    return out


def _redis_and_queue() -> dict:
    out = {"redis_ping_ms": -1, "celery_queue_depth": -1}
    try:
        import time
        import redis as _redis
        url = os.getenv("REDIS_URL") or "redis://localhost:6379/0"
        r = _redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
        t0 = time.monotonic()
        r.ping()
        out["redis_ping_ms"] = int((time.monotonic() - t0) * 1000)
        try:
            out["celery_queue_depth"] = int(r.llen("celery"))
        except Exception:
            out["celery_queue_depth"] = -1
    except Exception as e:
        logger.debug("system_health redis failed: %s", e)
    return out


def _worker_alive() -> str:
    try:
        from app.platform import automation_health
        h = automation_health.health()
        statuses = [v.get("status") for v in (h.get("jobs") or {}).values()] if isinstance(h, dict) else []
        if not statuses:
            return "unknown"
        return "ok" if any(s == "ok" for s in statuses) else "stale"
    except Exception:
        return "unknown"


@router.get("/system-health-detail")
async def system_health_detail(_user=Depends(require_admin)) -> dict:
    if os.getenv("SYS_HEALTH_DETAIL", "0").strip().lower() not in ("1", "true", "yes"):
        return {"enabled": False}
    out = {"enabled": True, "worker_alive": _worker_alive(), "health_ready": "unknown"}
    out.update(_resources())
    out.update(_redis_and_queue())
    try:
        from app.api.health import readiness_check  # reuse existing readiness
        rr = await readiness_check() if callable(readiness_check) else None
        if isinstance(rr, dict):
            out["health_ready"] = rr.get("status", "unknown")
    except Exception:
        pass
    return out
```

> Verify symbols before finalizing: `grep -n "psutil\|def readiness" app/api/health.py` and `grep -n "def health" app/platform/automation_health.py`. If `readiness_check` has a different name, wire the actual one or drop `health_ready` to `"unknown"` (do not add new heavy work). Confirm `redis` import style matches the rest of the app (`grep -rn "from_url" app | head`).

- [ ] **Step 4: Mount the router in `app/main.py`**

Find where other admin routers are included (`grep -n "system_health\|admin_dashboard" app/main.py`) and add alongside them:

```python
from app.api import system_health as _system_health
app.include_router(_system_health.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_readiness_infra_b3.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add app/api/system_health.py app/main.py tests/test_readiness_infra_b3.py
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(admin): B3 system-health drill-down endpoint (flag SYS_HEALTH_DETAIL)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: B4 — Customer inline lead-status edit (backend + override store + UI)

**Files:**
- Create: `app/platform/lead_overrides.py`
- Modify: `app/api/customer_dashboard.py` (add `id` to `LeadRow`, merge overrides, add `PATCH /api/customer/leads/{lead_id}`)
- Modify: `frontend/customer_dashboard.html` (inline `<select>` in leads table — this file is NOT touched by any other task, safe here)
- Create: `tests/test_readiness_infra_b4.py`

**Interfaces:**
- Produces:
  - `lead_overrides.read_overrides() -> dict[str, dict]` (lead_id → latest record), `lead_overrides.set_status(lead_id, client_id, status) -> bool`.
  - `PATCH /api/customer/leads/{lead_id}` body `{"status": "..."}`, dep `_authed_client_id` → `{ok: bool, lead_id, status}`. Cross-client → 403.
  - `LeadRow.id: str` (the inquiry UUID).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_readiness_infra_b4.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
ALLOWED = {"Hot", "Warm", "Cold", "Won", "Lost", "Follow-up"}


def test_override_roundtrip(tmp_path, monkeypatch):
    from app.platform import lead_overrides as lo
    monkeypatch.setattr(lo, "_OVR_FILE", str(tmp_path / "ovr.jsonl"))
    assert lo.set_status("lead1", "c1", "Won") is True
    lo.set_status("lead1", "c1", "Lost")  # latest wins
    ovr = lo.read_overrides()
    assert ovr["lead1"]["status"] == "Lost"
    assert ovr["lead1"]["client_id"] == "c1"


def test_patch_rejects_bad_status():
    # no auth header → 401/403 before status check; assert it is NOT 200
    r = client.patch("/api/customer/leads/x", json={"status": "Nonsense"})
    assert r.status_code in (401, 403, 422)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_readiness_infra_b4.py -v`
Expected: FAIL — `ModuleNotFoundError: app.platform.lead_overrides`.

- [ ] **Step 3: Create the override store**

```python
# app/platform/lead_overrides.py
"""B4 — customer-set lead status overrides (append-only; latest wins).
Source inquiries stay immutable; this is a thin overlay keyed by lead id."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_OVR_FILE = os.path.join("data", "lead_status_overrides.jsonl")
ALLOWED_STATUSES = {"Hot", "Warm", "Cold", "Won", "Lost", "Follow-up"}


def read_overrides() -> dict[str, dict]:
    out: dict[str, dict] = {}
    try:
        if not os.path.isfile(_OVR_FILE):
            return out
        with open(_OVR_FILE, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                    if isinstance(rec, dict) and rec.get("lead_id"):
                        out[str(rec["lead_id"])] = rec  # latest wins
                except Exception:
                    continue
    except Exception as e:
        logger.debug("lead_overrides read failed: %s", e)
    return out


def set_status(lead_id: str, client_id: str, status: str) -> bool:
    if status not in ALLOWED_STATUSES:
        return False
    rec = {
        "lead_id": str(lead_id),
        "client_id": str(client_id),
        "status": status,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        os.makedirs(os.path.dirname(_OVR_FILE) or ".", exist_ok=True)
        with open(_OVR_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        logger.warning("lead_overrides write failed: %s", e)
        return False
```

- [ ] **Step 4: Add `id` to `LeadRow` and merge overrides in `customer_dashboard.py`**

In the `LeadRow` model (around `:66`), add the id field:

```python
class LeadRow(BaseModel):
    id: str = ""           # NEW: stable inquiry UUID, used by inline status edit
    business: str
    # ... existing fields unchanged ...
```

In the lead-building loop (around `:365-393`), set `id=str(r.get("id") or "")` in the `LeadRow(...)` call. Then, immediately before the leads list is sliced/returned (around `:429`), apply overrides:

```python
        # B4: apply customer-set status overrides (latest wins)
        try:
            from app.platform.lead_overrides import read_overrides
            _ovr = read_overrides()
            for _ld in leads:
                _o = _ovr.get(_ld.id)
                if _o and _o.get("status"):
                    _ld.score = _o["status"]
        except Exception:
            pass
```

- [ ] **Step 5: Add the PATCH route in `customer_dashboard.py`**

Add near the top imports: `from fastapi import Body`. Then add the route (reusing billing's IDOR-safe dep):

```python
from app.api.billing import _authed_client_id  # IDOR-safe client resolution


@router.patch("/leads/{lead_id}")
async def patch_lead_status(
    lead_id: str,
    status: str = Body(..., embed=True),
    client_id: str = Depends(_authed_client_id),
) -> dict:
    """B4: customer updates a lead's status inline. Authorized to own client_id."""
    from app.platform.lead_overrides import ALLOWED_STATUSES, set_status

    if status not in ALLOWED_STATUSES:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(ALLOWED_STATUSES)}")
    ok = set_status(lead_id, client_id, status)
    return {"ok": ok, "lead_id": lead_id, "status": status}
```

> Verify the customer router prefix with `grep -n "APIRouter(" app/api/customer_dashboard.py` — the leads path must resolve to `/api/customer/leads/{lead_id}`. If the prefix is `/api/customer`, the decorator `@router.patch("/leads/{lead_id}")` is correct.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_readiness_infra_b4.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Add the inline `<select>` to `frontend/customer_dashboard.html`**

Read the leads-table render JS first (`grep -n "leads" frontend/customer_dashboard.html`). In the row template that renders each lead's score column, replace the static score cell with a select bound to `lead.id`:

```html
<select class="lead-status" data-id="${escH(l.id)}" onchange="updateLeadStatus(this)">
  ${["Hot","Warm","Cold","Won","Lost","Follow-up"].map(s=>
    `<option value="${s}" ${l.score===s?"selected":""}>${s}</option>`).join("")}
</select>
```

Add the handler near the other dashboard JS functions:

```javascript
async function updateLeadStatus(sel){
  const id=sel.getAttribute("data-id"), status=sel.value;
  if(!id) return;
  try{
    const r=await fetch("/api/customer/leads/"+encodeURIComponent(id),{
      method:"PATCH",
      headers:Object.assign({"Content-Type":"application/json"}, custAuthHdr()),
      body:JSON.stringify({status})
    });
    if(!r.ok) throw new Error("status "+r.status);
    sel.style.outline="2px solid #16a34a";
    setTimeout(()=>sel.style.outline="",800);
  }catch(e){ sel.style.outline="2px solid #dc2626"; }
}
```

> Match the existing auth-header helper name — `grep -n "AuthHdr\|Authorization" frontend/customer_dashboard.html` (it may be `custAuthHdr` / `authHdr` / inline). Use whatever the file already uses for authed customer fetches.

- [ ] **Step 8: Commit**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add app/platform/lead_overrides.py app/api/customer_dashboard.py frontend/customer_dashboard.html tests/test_readiness_infra_b4.py
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(customer): B4 inline lead-status edit (override store + IDOR-safe PATCH)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: B1 UI — Revenue trend chart in `admin_dashboard.html` (Wave 2, serial)

**Files:**
- Modify: `frontend/admin_dashboard.html` (revenue section only)

> Wave 2 START. Tasks 5, 6, 7 all edit this file — do them strictly one after another, re-Reading the file before each.

**Interfaces:**
- Consumes: `GET /api/admin/revenue-trend?days=90` → `{enabled, points:[{date,mrr,churn_pct,estimated}]}`.

- [ ] **Step 1: Add a canvas + loader in the revenue section**

Read the revenue card first (`grep -n "loadRevenueAnalytics\|revKpis" frontend/admin_dashboard.html`). Inside the revenue card `.bd`, add a chart canvas:

```html
<div class="chart-wrap" style="height:220px"><canvas id="chRevTrend"></canvas></div>
```

Add a loader that follows the existing Chart.js pattern:

```javascript
let _revTrendChart=null;
async function loadRevenueTrend(){
  try{
    const r=await fetch("/api/admin/revenue-trend?days=90",{headers:abAuthHdr(),cache:"no-store"});
    const d=await r.json();
    if(!d.enabled||!(d.points||[]).length) return;
    const labels=d.points.map(p=>p.date.slice(5));
    if(_revTrendChart) _revTrendChart.destroy();
    _revTrendChart=new Chart(document.getElementById("chRevTrend"),{
      type:"line",
      data:{labels,datasets:[
        {label:"MRR (₹)",data:d.points.map(p=>p.mrr),borderColor:"#4f46e5",tension:.3},
        {label:"Churn %",data:d.points.map(p=>p.churn_pct),borderColor:"#f59e0b",yAxisID:"y1",tension:.3}
      ]},
      options:{responsive:true,maintainAspectRatio:false,
        plugins:{legend:{position:"bottom",labels:{boxWidth:12,usePointStyle:true}}},
        scales:{y:{beginAtZero:true},y1:{position:"right",beginAtZero:true,grid:{display:false}}}}
    });
  }catch(e){/* silent: chart optional */}
}
```

- [ ] **Step 2: Call the loader where the revenue section initializes**

Find where `loadRevenueAnalytics()` is called and add `loadRevenueTrend();` right after it.

- [ ] **Step 3: Verify**

Run the app locally or curl the endpoint with `REVENUE_TRENDS=1`: `curl -s "http://127.0.0.1:8000/api/admin/revenue-trend?days=90" -H "Authorization: Bearer <admin-token>"` returns `enabled:true`. Load `/app/admin` revenue tab → line chart renders (or no-ops cleanly when flag off). No console errors.

- [ ] **Step 4: Commit**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add frontend/admin_dashboard.html
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(admin-ui): B1 revenue trend line chart

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: B2 UI — Per-client timeline drawer in `admin_dashboard.html` (Wave 2, serial)

**Files:**
- Modify: `frontend/admin_dashboard.html` (clients section only)

**Interfaces:**
- Consumes: `GET /api/admin/clients/{id}/timeline?limit=50` → `{enabled, events:[{ts,kind,source,summary}]}`.

- [ ] **Step 1: Re-Read the file, then add a "Timeline" action + drawer**

In the client row actions (find with `grep -n "bulkImpersonate\|client-row\|actions" frontend/admin_dashboard.html`), add a per-row button:

```html
<button class="btn-mini" onclick="openClientTimeline('${escH(c.client_id)}')">Timeline</button>
```

Add a drawer container near the end of the clients card and the loader (reuse the `.tl-row`/`.tl-dot` classes from `loadActivityFeed`):

```html
<div id="clientTlDrawer" style="display:none" class="card"><div class="hd"><h3>Client Timeline</h3>
  <button class="btn-mini" onclick="document.getElementById('clientTlDrawer').style.display='none'">×</button></div>
  <div class="bd"><div id="clientTlBody"></div></div></div>
```

```javascript
async function openClientTimeline(cid){
  const drawer=document.getElementById("clientTlDrawer"), body=document.getElementById("clientTlBody");
  drawer.style.display="block"; body.innerHTML="Loading…";
  try{
    const r=await fetch("/api/admin/clients/"+encodeURIComponent(cid)+"/timeline?limit=50",{headers:abAuthHdr()});
    const d=await r.json();
    if(!d.enabled){ body.innerHTML="<i>CLIENT_TIMELINE flag off</i>"; return; }
    const evs=d.events||[];
    body.innerHTML = evs.length ? evs.map(ev=>`<div class="tl-row">
      <div class="tl-dot ${ev.source==='audit'?'warn':''}"></div>
      <div><div><b>${escH(ev.kind)}</b> · <span style="color:#64748b">${escH(ev.source)}</span></div>
      <div class="tl-meta">${escH((ev.summary||'').slice(0,140))} · ${String(ev.ts||'').slice(0,19)}</div></div>
    </div>`).join("") : "<i>No events yet</i>";
  }catch(e){ body.innerHTML="<i>Failed to load</i>"; }
}
```

- [ ] **Step 2: Verify**

With `CLIENT_TIMELINE=1`, click a client's Timeline button → drawer shows merged events newest-first; with flag off shows the flag-off note. No console errors.

- [ ] **Step 3: Commit**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add frontend/admin_dashboard.html
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(admin-ui): B2 per-client timeline drawer

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: B3 UI — System-health gauges in `admin_dashboard.html` (Wave 2, serial)

**Files:**
- Modify: `frontend/admin_dashboard.html` (System Health section only)

**Interfaces:**
- Consumes: `GET /api/admin/system-health-detail` → `{enabled,cpu_pct,mem_pct,disk_pct,redis_ping_ms,celery_queue_depth,worker_alive,health_ready}`.

- [ ] **Step 1: Re-Read the file, then add a detail grid + loader**

Find the System Health card (`grep -n "loadHealthDetail\|System Health" frontend/admin_dashboard.html`). Add a detail container in its `.bd`:

```html
<div id="sysHealthDetail" class="rev-kpi-grid"></div>
```

```javascript
async function loadSysHealthDetail(){
  const el=document.getElementById("sysHealthDetail"); if(!el) return;
  try{
    const r=await fetch("/api/admin/system-health-detail",{headers:abAuthHdr(),cache:"no-store"});
    const d=await r.json();
    if(!d.enabled){ el.innerHTML="<i>SYS_HEALTH_DETAIL flag off</i>"; return; }
    const rows=[
      {l:"CPU",v:(d.cpu_pct<0?"—":d.cpu_pct+"%")},
      {l:"Memory",v:(d.mem_pct<0?"—":d.mem_pct+"%")},
      {l:"Disk",v:(d.disk_pct<0?"—":d.disk_pct+"%")},
      {l:"Redis ping",v:(d.redis_ping_ms<0?"—":d.redis_ping_ms+"ms")},
      {l:"Celery queue",v:(d.celery_queue_depth<0?"—":d.celery_queue_depth)},
      {l:"Worker",v:escH(d.worker_alive||"?")}
    ];
    el.innerHTML=rows.map(x=>`<div class="rev-kpi"><div class="rk-lbl">${x.l}</div><div class="rk-val">${x.v}</div></div>`).join("");
  }catch(e){ el.innerHTML="<i>Failed to load</i>"; }
}
```

- [ ] **Step 2: Call the loader where the health section initializes**

Find where `loadHealthDetail()` is called and add `loadSysHealthDetail();` after it.

- [ ] **Step 3: Verify**

With `SYS_HEALTH_DETAIL=1`, the admin health card shows CPU/mem/disk/redis/queue/worker; queue depth ≥ 0; flag-off shows the note. No console errors.

- [ ] **Step 4: Commit**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add frontend/admin_dashboard.html
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(admin-ui): B3 system-health drill-down gauges

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Register flags + wire the daily snapshot job (Wave 3, serial)

**Files:**
- Modify: `app/api/growth.py` (`AUTOMATION_FLAGS`)
- Modify: `app/platform/team_scheduler.py` (daily `revenue_snapshot` job + boot-grace)

- [ ] **Step 1: Register the three flags**

In `app/api/growth.py` `AUTOMATION_FLAGS` (around `:1151`), add three strings:

```python
    "REVENUE_TRENDS",   # B1 admin revenue time-series
    "CLIENT_TIMELINE",  # B2 per-client activity timeline
    "SYS_HEALTH_DETAIL",  # B3 system-health drill-down
```

- [ ] **Step 2: Add `revenue_snapshot` to the scheduler**

In `app/platform/team_scheduler.py`:

(a) In `_last_ran` dict (around `:95`): add `"revenue_snapshot": None,`.

(b) In `_run_job_inner` (the `elif job == ...` chain): add a branch:

```python
    elif job == "revenue_snapshot":
        if os.environ.get("REVENUE_TRENDS", "0").strip().lower() in ("1", "true", "yes"):
            from app.platform import revenue_snapshots
            await revenue_snapshots.snapshot_today()
```

(c) In the boot-grace `_heavy` dict (around `:641`): add `"revenue_snapshot": ((0, 5), (0, 35)),` (00:05–00:35 IST window).

(d) In `scheduler_loop` (around `:686`): add a check matching the window:

```python
    if (0, 5) <= hm < (0, 35) and _last_ran["revenue_snapshot"] != day_key:
        _last_ran["revenue_snapshot"] = day_key
        await _run_job("revenue_snapshot")
```

> Confirm `hm` is the `(hour, minute)` IST tuple used by the surrounding checks and that `os` is imported (it is). Match the exact comparison style of the neighbouring `if (8, 30) <= hm < ...` lines.

- [ ] **Step 3: Verify flags appear**

Run: `pytest tests/test_readiness_infra_b1.py tests/test_readiness_infra_b2.py tests/test_readiness_infra_b3.py tests/test_readiness_infra_b4.py -v`
Then confirm flags register: `python -c "from app.api.growth import AUTOMATION_FLAGS; print([f for f in AUTOMATION_FLAGS if f in ('REVENUE_TRENDS','CLIENT_TIMELINE','SYS_HEALTH_DETAIL')])"`
Expected: all four test files PASS; the print shows all three flags.

- [ ] **Step 4: Commit**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add app/api/growth.py app/platform/team_scheduler.py
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat: register B1-B3 flags + daily revenue-snapshot scheduler job (boot-grace)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Verification gate (Track C)

**Files:** none (verification only)

- [ ] **Step 1: Production import + readiness check**

Run: `python scripts/prod_check.py`
Expected: green (no import errors, routes load). Fix any import issue surfaced (e.g. wrong symbol in Task 1/2/3 "verify" notes).

- [ ] **Step 2: Run the targeted test suite**

Run: `scripts\run_tests.bat`
Then **Read `pytest_run.log`** (do not trust console alone). Expected: existing suite still green + the four new test files pass. Avoid the full-suite team_pulse hang — if it hangs, run the four new files + `tests/test_activation_readiness.py` + `tests/test_billing_truth_2026.py` individually.

- [ ] **Step 3: Secret scan**

Run: `python scripts/check_secrets.py`
Expected: clean. (The `.env` fragments surfaced during the audit must NOT appear in any committed file.)

- [ ] **Step 4: Confirm live readiness is unaffected (pre-deploy sanity)**

Run: `curl -s https://leadsgenai.in/api/activation/summary`
Expected: still `blocker_count: 0` (this branch is not deployed yet; this confirms the baseline before the ops deploy step).

- [ ] **Step 5: Hand off to deploy**

Deploy is the standard ops loop (`leadgen-ops` / `hostinger-deploy` skill), run AFTER this plan and AFTER merging `feature/readiness-infra-2026-06-20` → `main`. Flags stay OFF in prod `.env` until you choose to enable them (`REVENUE_TRENDS`, `CLIENT_TIMELINE`, `SYS_HEALTH_DETAIL`). B4 (no flag) is live-on-deploy but inert until a customer edits a status.

---

## Self-Review (completed during authoring)

- **Spec coverage:** B1 → Tasks 1, 5, 8(job). B2 → Tasks 2, 6. B3 → Tasks 3, 7. B4 → Task 4. Flags → Task 8. Track C verification → Task 9. Track A (activation) is user-action documentation only (no task; in spec §3). Parallel-safe file-ownership matrix → reflected in wave structure + Global Constraints. All spec sections mapped.
- **Placeholder scan:** No TBD/TODO. The `>` verify-notes are explicit grep commands to confirm real symbols (`clients_store.all_clients`, audit fetch, `readiness_check`, customer router prefix, customer auth-header helper) — these are real verification steps, not deferred work; each has a concrete fallback.
- **Type consistency:** `read_trend(days, clients)`, `snapshot_today()`, `_build_client_timeline(...)`, `read_overrides()`/`set_status()`, `LeadRow.id`, and the endpoint shapes (`{enabled, points|events|...}`) are used identically in tests, backend, and the consuming frontend loaders.
