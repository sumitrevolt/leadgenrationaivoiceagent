# Customer Delivery Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single source-of-truth, append-only "delivery ledger" that records what LeadGen AI actually did for each paying customer, wire it into the 5 existing signal points that already generate/deliver value, expose it to admin (extend the existing per-client timeline + a manual "Deliver Now" button) and to the customer (a new section in the just-shipped 4-view dashboard IA) — so admin and customer both get honest, provable answers to "what happened, what's pending, what do I do next."

**Architecture:** New `DeliveryEvent` SQLAlchemy model (mirrors the existing `AgentEvent` pattern exactly, separate table — deliberately not reusing `AgentEvent` since that's staff-internal) + a new `app/platform/delivery_ledger.py` module (mirrors `app/platform/team.py`'s `log_event`/`_db()` conventions: sync, defensive, never raises). Eight of the mission's fourteen event types get wired in this sub-project at their real existing call sites; the remaining six are deferred to the sub-projects that own their views (Marketing Calendar / Leads Inbox / Reports), not guessed at here.

**Tech Stack:** FastAPI, SQLAlchemy (sync session via `app.models.base`), Alembic, pytest + `monkeypatch` (this repo's established test style — no live DB required for these tests).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-06-customer-delivery-ledger-design.md` — every task below implements a piece of that spec; do not add scope beyond it.
- **No git commit or push at the end of any task.** This repo's CLAUDE.md forbids committing without the user explicitly asking ("commit/push bina user ke kahe" — never). Every task below ends with a verification step (tests green), NOT a commit. Staging/committing happens later, only when the user explicitly asks, in one batch or however they prefer.
- **No VPS deploy** at any point in this plan.
- **No `.env` file edits.** Feature flags (`AUTO_DELIVER_VALUE`, `WHATSAPP_AUTO_SEND`) are never read, changed, or worked around — the new admin action always uses the existing `force=True` single-customer bypass, never a flag flip.
- Every new function that touches the DB or an external call must never raise to its caller (fail-open, this repo's universal convention) — match the `try/except: logger.warning(...)` style shown in `app/platform/team.py:log_event` and `app/marketing/customer_delivery.py:_record_stuck`.
- Money/plan/route logic (`app/marketing/packages.py`) is not touched anywhere in this plan.
- Follow this repo's existing per-module helper convention: small helpers like `_db()`/`_flag_on()` are duplicated locally per module (confirmed in `customer_delivery.py`, `team.py`) rather than centralized — do not "DRY" these into a shared utils module, that would be an unrequested refactor.
- Before running the migration against any real database, get a quick sanity check from the `database-architect` subagent (additive-only, new table, but still a schema change).

---

### Task 1: `DeliveryEvent` model, registration, and migration

**Files:**
- Create: `app/models/delivery_event.py`
- Modify: `app/models/__init__.py:10` (import) and `app/models/__init__.py:83-87` (`__all__`)
- Create: `alembic/versions/011_add_delivery_events.py`
- Test: `tests/test_delivery_event_model.py`

**Interfaces:**
- Produces: `app.models.delivery_event.DeliveryEvent` (columns: `id`, `client_id`, `event_type`, `detail`, `status`, `meta_json`, `created_at`), importable also from `app.models` package root. Table name `delivery_events`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_delivery_event_model.py`:

```python
"""DeliveryEvent model shape — mirrors test coverage style of AgentEvent."""


def test_delivery_event_importable_with_expected_columns():
    from app.models.delivery_event import DeliveryEvent

    assert DeliveryEvent.__tablename__ == "delivery_events"
    cols = {c.name for c in DeliveryEvent.__table__.columns}
    assert cols == {"id", "client_id", "event_type", "detail", "status", "meta_json", "created_at"}


def test_delivery_event_exported_from_models_package():
    from app.models import DeliveryEvent  # noqa: F401 — import-error is the assertion
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_delivery_event_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.delivery_event'`

- [ ] **Step 3: Create the model**

Create `app/models/delivery_event.py`:

```python
"""
DeliveryEvent Model — customer-facing delivery ledger.
Har paying customer ke liye "AI ne kya kiya" event trail; admin Customer 360
aur customer dashboard dono isi se apna-apna view banate hain
(app/platform/delivery_ledger.py). Staff-internal AgentEvent se jaan-boojh kar
ALAG table hai — do alag audiences/consumers ko couple nahi karna.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, String, Text

from app.models.base import Base


class DeliveryEvent(Base):
    """Ek customer-facing business event (plan activated, content generated, ...)."""

    __tablename__ = "delivery_events"

    __table_args__ = (
        Index("ix_delivery_events_client_time", "client_id", "created_at"),
        Index("ix_delivery_events_time", "created_at"),
    )

    id = Column(String(36), primary_key=True)
    client_id = Column(String(40), nullable=False)
    event_type = Column(String(40), nullable=False, default="event")
    detail = Column(String(500), default="")
    status = Column(String(10), default="ok")  # ok | warn | error
    meta_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
```

- [ ] **Step 4: Register in the models package**

In `app/models/__init__.py`, modify line 10 area — the import block currently reads (lines 9-11):

```python
from app.models.contact import Contact
from app.models.interaction import Interaction
```

Change to:

```python
from app.models.contact import Contact
from app.models.delivery_event import DeliveryEvent
from app.models.interaction import Interaction
```

Then in the `__all__` list, the block currently reads (lines 83-87):

```python
    "SubscriptionPlan",
    # Agent / worker models
    "Agent",
    "AgentStatus",
    "AgentEvent",
```

Change to:

```python
    "SubscriptionPlan",
    # Delivery ledger
    "DeliveryEvent",
    # Agent / worker models
    "Agent",
    "AgentStatus",
    "AgentEvent",
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_delivery_event_model.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Write the migration**

Create `alembic/versions/011_add_delivery_events.py`:

```python
"""delivery_events table (customer-facing delivery ledger, sub-project 1 of
Customer Delivery OS, 2026-07-06).

Mirrors 008_add_agents_agent_events.py's idempotent pattern: only creates the
table when genuinely absent (fresh DB / DR restore), never ALTERs an existing
table — zero column-drift risk against the live VPS.

Revision ID: 011_add_delivery_events
Revises: 010_enum_columns_to_varchar
"""

import sqlalchemy as sa

from alembic import op

revision = "011_add_delivery_events"
down_revision = "010_enum_columns_to_varchar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "delivery_events" not in existing:
        op.create_table(
            "delivery_events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("client_id", sa.String(40), nullable=False),
            sa.Column("event_type", sa.String(40), nullable=False, server_default="event"),
            sa.Column("detail", sa.String(500), server_default=""),
            sa.Column("status", sa.String(10), server_default="ok"),
            sa.Column("meta_json", sa.Text(), server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index(
            "ix_delivery_events_client_time", "delivery_events", ["client_id", "created_at"]
        )
        op.create_index("ix_delivery_events_time", "delivery_events", ["created_at"])


def downgrade() -> None:
    try:
        op.drop_table("delivery_events")
    except Exception:
        pass
```

- [ ] **Step 7: Verify the migration file is syntactically valid**

Run: `.venv\Scripts\python.exe -m py_compile alembic/versions/011_add_delivery_events.py`
Expected: no output, exit code 0. (Running it against a live DB with `alembic upgrade head` requires a reachable Postgres — do that separately wherever a dev/staging DB is available, after the `database-architect` sanity check per Global Constraints; do not skip straight to a live/VPS DB.)

- [ ] **Step 8: Final check for this task**

Run: `.venv\Scripts\python.exe -m pytest tests/test_delivery_event_model.py -v`
Expected: PASS. Do not commit (see Global Constraints).

---

### Task 2: `delivery_ledger` module — `log_event` + `get_timeline`

**Files:**
- Create: `app/platform/delivery_ledger.py`
- Test: `tests/test_delivery_ledger.py`

**Interfaces:**
- Consumes: `app.models.delivery_event.DeliveryEvent` (Task 1).
- Produces: `log_event(client_id: str, event_type: str, detail: str = "", status: str = "ok", meta: dict | None = None) -> None`; `get_timeline(client_id: str, limit: int = 50, audience: str = "customer") -> list[dict]` where each dict has `{"ts", "event_type", "label", "icon", "detail", "status"}`; `EVENT_TYPES: set[str]` (the mission's 14 canonical types).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_delivery_ledger.py`:

```python
"""app.platform.delivery_ledger — customer-facing delivery event log.
Offline (no DB required): _db() returns None when no engine is configured,
so log_event must no-op safely and get_timeline must return []."""

from app.platform import delivery_ledger as dl


def test_event_types_include_all_14_mission_types():
    expected = {
        "customer_created", "plan_activated", "onboarding_started",
        "onboarding_completed", "marketing_calendar_generated",
        "post_draft_created", "post_approved", "post_published",
        "post_failed", "lead_captured", "followup_sent",
        "weekly_report_generated", "automation_failed", "admin_manual_action",
    }
    assert expected.issubset(dl.EVENT_TYPES)


def test_log_event_never_raises_without_db(monkeypatch):
    monkeypatch.setattr(dl, "_db", lambda: None)
    # Must not raise even though there is no DB session.
    dl.log_event("client_x", "plan_activated", detail="starter plan")


def test_log_event_writes_row_via_fake_session(monkeypatch):
    added = []

    class _FakeSession:
        def add(self, row):
            added.append(row)

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(dl, "_db", lambda: _FakeSession())
    dl.log_event("client_x", "plan_activated", detail="starter plan", meta={"plan": "starter"})
    assert len(added) == 1
    row = added[0]
    assert row.client_id == "client_x"
    assert row.event_type == "plan_activated"
    assert row.detail == "starter plan"
    assert "starter" in row.meta_json


def test_log_event_unknown_type_still_logs_never_raises(monkeypatch):
    added = []

    class _FakeSession:
        def add(self, row):
            added.append(row)

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(dl, "_db", lambda: _FakeSession())
    dl.log_event("client_x", "totally_unknown_type")
    assert len(added) == 1
    assert added[0].event_type == "totally_unknown_type"


def test_get_timeline_empty_without_db(monkeypatch):
    monkeypatch.setattr(dl, "_db", lambda: None)
    assert dl.get_timeline("client_x") == []


def test_get_timeline_renders_customer_vs_admin_labels(monkeypatch):
    from datetime import datetime

    class _Row:
        def __init__(self):
            self.client_id = "client_x"
            self.event_type = "plan_activated"
            self.detail = "starter plan via upi_screenshot"
            self.status = "ok"
            self.meta_json = "{}"
            self.created_at = datetime(2026, 7, 6, 9, 0, 0)

    class _Query:
        def filter(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def all(self):
            return [_Row()]

    class _FakeSession:
        def query(self, *a, **k):
            return _Query()

        def close(self):
            pass

    monkeypatch.setattr(dl, "_db", lambda: _FakeSession())

    customer_view = dl.get_timeline("client_x", audience="customer")
    admin_view = dl.get_timeline("client_x", audience="admin")
    assert len(customer_view) == 1 and len(admin_view) == 1
    # Customer label must be the friendly Hinglish line, not the raw event_type.
    assert customer_view[0]["label"] != "plan_activated"
    assert "plan_activated" not in customer_view[0]["label"]
    # Admin label may include the technical detail.
    assert "plan_activated" in admin_view[0]["label"] or "starter plan" in admin_view[0]["label"]
    assert customer_view[0]["event_type"] == "plan_activated"


def test_get_timeline_unknown_type_has_safe_fallback_label(monkeypatch):
    from datetime import datetime

    class _Row:
        client_id = "client_x"
        event_type = "some_future_type"
        detail = "n/a"
        status = "ok"
        meta_json = "{}"
        created_at = datetime(2026, 7, 6, 9, 0, 0)

    class _Query:
        def filter(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def all(self):
            return [_Row()]

    class _FakeSession:
        def query(self, *a, **k):
            return _Query()

        def close(self):
            pass

    monkeypatch.setattr(dl, "_db", lambda: _FakeSession())
    out = dl.get_timeline("client_x")
    assert len(out) == 1
    assert out[0]["label"]  # non-empty fallback, never raises/blank
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_delivery_ledger.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.platform.delivery_ledger'`

- [ ] **Step 3: Write the module**

Create `app/platform/delivery_ledger.py`:

```python
"""
delivery_ledger.py — single source-of-truth customer-facing delivery ledger.

WHY: content generation already runs (auto_content.py) but customers had no
provable trail of what actually happened for them, and admin had no single
place to see it either. This module is that trail. Mirrors app/platform/
team.py's log_event()/_db() conventions exactly: sync, defensive, never
raises — a ledger write must never break the real work it's recording.

log_event(client_id, event_type, ...)     -> None   (never raises)
get_timeline(client_id, audience=...)     -> list[dict]  (never raises, [] on any error)

`audience` controls which label renders for a stored row — "customer" (plain
Hinglish, no internals) or "admin" (technical, includes `detail`). Same row,
two renderings — no duplicated storage.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# The mission's 14 canonical event types. Unknown types are still logged (never
# raise) but fall back to a generic label — see _label().
EVENT_TYPES: set[str] = {
    "customer_created",
    "plan_activated",
    "onboarding_started",
    "onboarding_completed",
    "marketing_calendar_generated",
    "post_draft_created",
    "post_approved",
    "post_published",
    "post_failed",
    "lead_captured",
    "followup_sent",
    "weekly_report_generated",
    "automation_failed",
    "admin_manual_action",
}

# event_type -> (customer-facing Hinglish label, icon). Admin label is built
# from the same base line + the raw technical `detail` (see _label()).
EVENT_LABELS: dict[str, tuple[str, str]] = {
    "customer_created": ("Aapka account ban gaya", "🆕"),
    "plan_activated": ("Aapka plan activate ho gaya", "✅"),
    "onboarding_started": ("Setup shuru ho gaya", "⚙️"),
    "onboarding_completed": ("Setup complete ho gaya", "🎉"),
    "marketing_calendar_generated": ("Naya content calendar taiyaar hua", "🗓️"),
    "post_draft_created": ("Naye post drafts taiyaar hue", "📝"),
    "post_approved": ("Aapne post approve kiya", "👍"),
    "post_published": ("Post publish ho gaya", "📣"),
    "post_failed": ("Post publish nahi ho paya", "⚠️"),
    "lead_captured": ("Naya lead aaya", "📥"),
    "followup_sent": ("Follow-up bheja gaya", "💬"),
    "weekly_report_generated": ("Weekly report taiyaar hua", "📊"),
    "automation_failed": ("Ek automation atak gaya", "🚨"),
    "admin_manual_action": ("Team ne manually kaam kiya", "🛠️"),
}

_FALLBACK_LABEL = ("Update hua", "•")


def _db():
    """Lazy sync Session (ya None). Mirrors app/platform/team.py:_db() exactly —
    duplicated on purpose (this repo's convention: small helpers stay local
    per module, not centralized)."""
    try:
        from app.models import base as _b

        _b._get_sync_engine()
        if _b._SessionLocal is None:
            return None
        return _b._SessionLocal()
    except Exception:
        return None


def log_event(
    client_id: str,
    event_type: str,
    detail: str = "",
    status: str = "ok",
    meta: dict[str, Any] | None = None,
) -> None:
    """Record one customer-facing delivery event. Sync, fast, never raises.

    client_id: the paying client's id (clients_store id).
    event_type: one of EVENT_TYPES (unknown values still logged, just render
      with a generic fallback label later — never raise on an unexpected type).
    detail: short technical line (admin view only).
    status: ok | warn | error.
    """
    try:
        from app.models.delivery_event import DeliveryEvent

        db = _db()
        if db is None:
            return
        try:
            row = DeliveryEvent(
                id=str(uuid.uuid4()),
                client_id=(client_id or "")[:40],
                event_type=(event_type or "event")[:40],
                detail=(detail or "")[:500],
                status=(status or "ok")[:10],
                meta_json=json.dumps(meta or {}, ensure_ascii=False, default=str)[:2000],
                created_at=datetime.utcnow(),
            )
            db.add(row)
            db.commit()
        finally:
            db.close()
    except Exception as e:  # NEVER break the caller's real work
        logger.debug("[delivery_ledger] log_event skipped: %s", e)


def _label(event_type: str, detail: str, audience: str) -> str:
    base, _icon = EVENT_LABELS.get(event_type, _FALLBACK_LABEL)
    if audience == "admin":
        return f"{base} ({event_type}: {detail})" if detail else f"{base} ({event_type})"
    return base


def get_timeline(client_id: str, limit: int = 50, audience: str = "customer") -> list[dict[str, Any]]:
    """Newest-first timeline for one client. Never raises — [] on any error.

    audience: "customer" (plain label only) or "admin" (label includes the
    technical event_type + detail — same underlying row, two renderings)."""
    out: list[dict[str, Any]] = []
    try:
        from app.models.delivery_event import DeliveryEvent

        db = _db()
        if db is None:
            return out
        try:
            rows = (
                db.query(DeliveryEvent)
                .filter(DeliveryEvent.client_id == str(client_id))
                .order_by(DeliveryEvent.created_at.desc())
                .limit(max(1, min(int(limit), 200)))
                .all()
            )
            for r in rows:
                _base, icon = EVENT_LABELS.get(r.event_type, _FALLBACK_LABEL)
                out.append(
                    {
                        "ts": r.created_at.isoformat() if r.created_at else "",
                        "event_type": r.event_type,
                        "label": _label(r.event_type, r.detail or "", audience),
                        "icon": icon,
                        "detail": r.detail if audience == "admin" else "",
                        "status": r.status or "ok",
                    }
                )
        finally:
            db.close()
    except Exception as e:
        logger.debug("[delivery_ledger] get_timeline skipped: %s", e)
        return []
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_delivery_ledger.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Final check for this task**

Run: `.venv\Scripts\python.exe -m ruff check app/platform/delivery_ledger.py`
Expected: no errors. Do not commit.

---

### Task 3: Wire `customer_created` into `clients_store.add_client()`

**Files:**
- Modify: `app/marketing/clients_store.py:276` (right after `_append(rec)`)
- Test: `tests/test_delivery_ledger_wiring.py` (new file, shared by Tasks 3–7)

**Interfaces:**
- Consumes: `app.platform.delivery_ledger.log_event` (Task 2).

- [ ] **Step 1: Write the failing test**

Create `tests/test_delivery_ledger_wiring.py`:

```python
"""Each of these tests monkeypatches app.platform.delivery_ledger.log_event at
the call site and asserts it fires with the right event_type/client_id — the
same style already used in tests/test_call_event_client_id.py for
app.platform.team.log_event."""

import pytest


def test_add_client_logs_customer_created(monkeypatch, tmp_path):
    from app.marketing import clients_store

    monkeypatch.setattr(clients_store, "_CLIENTS_FILE", str(tmp_path / "clients.jsonl"))
    events = []
    monkeypatch.setattr(
        "app.platform.delivery_ledger.log_event",
        lambda client_id, event_type, **kw: events.append((client_id, event_type)),
    )
    rec = clients_store.add_client(business_name="Test Biz", niche="solar", phone="9812345678")
    assert rec.get("id")
    assert (rec["id"], "customer_created") in events
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_delivery_ledger_wiring.py::test_add_client_logs_customer_created -v`
Expected: FAIL — `assert (rec["id"], "customer_created") in events` fails (`events == []`)

- [ ] **Step 3: Wire the call**

In `app/marketing/clients_store.py`, the block currently reads (lines 274-277):

```python
            "created_at": _now(),
        }
        _append(rec)

```

Change to:

```python
            "created_at": _now(),
        }
        _append(rec)

        try:
            from app.platform import delivery_ledger

            delivery_ledger.log_event(cid, "customer_created", detail=name)
        except Exception as e:  # pragma: no cover
            logger.debug(f"[clients_store] ledger log skip: {e}")

```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_delivery_ledger_wiring.py::test_add_client_logs_customer_created -v`
Expected: PASS

- [ ] **Step 5: Run the existing clients_store test suite to check for regressions**

Run: `.venv\Scripts\python.exe -m pytest tests/ -k clients_store -v`
Expected: all PASS (no existing test asserts on the absence of a ledger call, so this is purely additive)

---

### Task 4: Wire `plan_activated` into `usage.activate_plan()`

**Files:**
- Modify: `app/billing/usage.py:481-489`
- Test: `tests/test_delivery_ledger_wiring.py` (append)

**Interfaces:**
- Consumes: `app.platform.delivery_ledger.log_event` (Task 2).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_delivery_ledger_wiring.py`:

```python
def test_activate_plan_logs_plan_activated(monkeypatch):
    from app.billing import usage

    monkeypatch.setattr(
        "app.marketing.clients_store.get_client",
        lambda cid: {"id": cid, "business_name": "Test Biz"},
        raising=False,
    )
    monkeypatch.setattr("app.marketing.clients_store.update_client", lambda cid, **kw: None, raising=False)
    # Subscription-row side of activate_plan touches the DB — irrelevant to this
    # test, so make it a no-op rather than requiring a live DB.
    monkeypatch.setattr(usage, "_latest_subscription", lambda db, cid: None, raising=False)

    events = []
    monkeypatch.setattr(
        "app.platform.delivery_ledger.log_event",
        lambda client_id, event_type, **kw: events.append((client_id, event_type)),
    )
    usage.activate_plan("client_abc", "starter")
    assert ("client_abc", "plan_activated") in events
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_delivery_ledger_wiring.py::test_activate_plan_logs_plan_activated -v`
Expected: FAIL (`events == []`) — or an error from the Subscription-row block; if so, note the exact failing line at `app/billing/usage.py` around line 492+ so Step 3 places the ledger call BEFORE that block, not after (see Step 3).

- [ ] **Step 3: Wire the call**

In `app/billing/usage.py`, the block currently reads (lines 481-489):

```python
    applied = False
    try:
        from app.marketing.clients_store import get_client, update_client

        if get_client(cid):
            update_client(cid, plan=plan_k)
            applied = True
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("activate_plan clients_store skipped: %s", e)
```

Change to:

```python
    applied = False
    try:
        from app.marketing.clients_store import get_client, update_client

        if get_client(cid):
            update_client(cid, plan=plan_k)
            applied = True
            try:
                from app.platform import delivery_ledger

                delivery_ledger.log_event(cid, "plan_activated", detail=plan_k)
            except Exception as le:  # pragma: no cover
                logger.debug("activate_plan ledger log skip: %s", le)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("activate_plan clients_store skipped: %s", e)
```

This logs `plan_activated` immediately after the plan is actually applied to `clients_store`, before the (separate, best-effort) Subscription-row annotation block — so the ledger call never depends on DB/Subscription-row success.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_delivery_ledger_wiring.py::test_activate_plan_logs_plan_activated -v`
Expected: PASS

- [ ] **Step 5: Run the existing billing/usage test suite to check for regressions**

Run: `.venv\Scripts\python.exe -m pytest tests/ -k "usage or billing" -v`
Expected: all PASS

---

### Task 5: Wire `onboarding_started` + `onboarding_completed` into `onboarding.py`

**Files:**
- Modify: `app/marketing/onboarding.py:365-405`
- Test: `tests/test_delivery_ledger_wiring.py` (append)

**Interfaces:**
- Consumes: `app.platform.delivery_ledger.log_event` (Task 2).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_delivery_ledger_wiring.py`:

```python
@pytest.mark.asyncio
async def test_auto_onboard_logs_started_and_completed(monkeypatch):
    from app.marketing import onboarding

    client = {"id": "c1", "business_name": "Test Biz"}
    monkeypatch.setattr("app.marketing.clients_store.get_client", lambda cid: client, raising=False)
    monkeypatch.setattr("app.marketing.clients_store.update_client", lambda cid, **kw: None, raising=False)

    async def _fake_seed_kb(cid, website):
        return {"kb_chunks": 0}

    async def _fake_content_pack(client):
        return {"ok": True}

    async def _fake_welcome(client, kb_seeded):
        return {"sent": False}

    monkeypatch.setattr(onboarding, "_seed_kb_from_website", _fake_seed_kb)
    monkeypatch.setattr(onboarding, "_first_content_pack", _fake_content_pack)
    monkeypatch.setattr(onboarding, "_send_welcome_whatsapp", _fake_welcome)
    monkeypatch.setattr("app.marketing.auto_content.seed_client_content", lambda client: _async_zero(), raising=False)
    monkeypatch.setattr("app.platform.client_snapshots.apply_niche_to_client", lambda cid: {"ok": True}, raising=False)

    events = []
    monkeypatch.setattr(
        "app.platform.delivery_ledger.log_event",
        lambda client_id, event_type, **kw: events.append((client_id, event_type)),
    )

    await onboarding.auto_onboard("c1")
    kinds = [e[1] for e in events if e[0] == "c1"]
    assert "onboarding_started" in kinds
    assert "onboarding_completed" in kinds
    assert kinds.index("onboarding_started") < kinds.index("onboarding_completed")


async def _async_zero():
    return 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_delivery_ledger_wiring.py::test_auto_onboard_logs_started_and_completed -v`
Expected: FAIL (`kinds == []`, no `onboarding_started`/`onboarding_completed` logged yet)

- [ ] **Step 3: Wire the calls**

In `app/marketing/onboarding.py`, the block currently reads (lines 365-376):

```python
async def auto_onboard(cid: str) -> dict[str, Any]:
    """Run the full auto-setup for one client. Never raises."""
    report: dict[str, Any] = {"client_id": cid, "steps": {}}
    try:
        from app.marketing import clients_store

        client = clients_store.get_client(cid)
        if not client:
            return {"error": "client not found", "client_id": cid}
        biz = client.get("business_name", "")

        report["steps"]["kb_website"] = await _seed_kb_from_website(cid, _website(client))
```

Change to:

```python
async def auto_onboard(cid: str) -> dict[str, Any]:
    """Run the full auto-setup for one client. Never raises."""
    report: dict[str, Any] = {"client_id": cid, "steps": {}}
    try:
        from app.marketing import clients_store

        client = clients_store.get_client(cid)
        if not client:
            return {"error": "client not found", "client_id": cid}
        biz = client.get("business_name", "")

        try:
            from app.platform import delivery_ledger

            delivery_ledger.log_event(cid, "onboarding_started", detail=biz)
        except Exception as le:  # pragma: no cover
            logger.debug("onboard ledger log skip (started): %s", le)

        report["steps"]["kb_website"] = await _seed_kb_from_website(cid, _website(client))
```

Then the setup_done block currently reads (lines 400-405):

```python
        try:
            clients_store.update_client(
                cid, setup_done=True, setup_at=datetime.now(timezone.utc).isoformat()
            )
        except Exception:
            pass
```

Change to:

```python
        try:
            clients_store.update_client(
                cid, setup_done=True, setup_at=datetime.now(timezone.utc).isoformat()
            )
        except Exception:
            pass
        try:
            from app.platform import delivery_ledger

            delivery_ledger.log_event(cid, "onboarding_completed", detail=biz)
        except Exception as le:  # pragma: no cover
            logger.debug("onboard ledger log skip (completed): %s", le)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_delivery_ledger_wiring.py::test_auto_onboard_logs_started_and_completed -v`
Expected: PASS

- [ ] **Step 5: Run the existing onboarding test suite to check for regressions**

Run: `.venv\Scripts\python.exe -m pytest tests/ -k onboard -v`
Expected: all PASS

---

### Task 6: Wire `marketing_calendar_generated` + `post_draft_created` into `auto_content.seed_client_content()`

**Files:**
- Modify: `app/marketing/auto_content.py:523-541`
- Test: `tests/test_delivery_ledger_wiring.py` (append)

**Interfaces:**
- Consumes: `app.platform.delivery_ledger.log_event` (Task 2).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_delivery_ledger_wiring.py`:

```python
@pytest.mark.asyncio
async def test_seed_client_content_logs_calendar_and_drafts(monkeypatch):
    from app.marketing import auto_content

    async def _fake_generate(client):
        return [{"type": "post"}, {"type": "post"}]

    monkeypatch.setattr(auto_content, "generate_for_client", _fake_generate)
    monkeypatch.setattr(auto_content, "_append_items", lambda cid, items: len(items), raising=False)

    events = []
    monkeypatch.setattr(
        "app.platform.delivery_ledger.log_event",
        lambda client_id, event_type, **kw: events.append((client_id, event_type, kw.get("meta"))),
    )

    added = await auto_content.seed_client_content({"id": "c1", "business_name": "Test Biz"})
    assert added == 2
    kinds = [e[1] for e in events if e[0] == "c1"]
    assert "marketing_calendar_generated" in kinds
    assert "post_draft_created" in kinds
    draft_event = next(e for e in events if e[1] == "post_draft_created")
    assert draft_event[2].get("count") == 2


@pytest.mark.asyncio
async def test_seed_client_content_no_ledger_noise_when_zero_added(monkeypatch):
    """Zero new drafts (dedupe hit / recycle also empty) -> no misleading events."""
    from app.marketing import auto_content

    async def _fake_generate(client):
        return []

    monkeypatch.setattr(auto_content, "generate_for_client", _fake_generate)
    monkeypatch.setattr(auto_content, "_append_items", lambda cid, items: 0, raising=False)

    async def _fake_recycle(client):
        return 0

    monkeypatch.setattr(auto_content, "_recycle_fallback", _fake_recycle)

    events = []
    monkeypatch.setattr(
        "app.platform.delivery_ledger.log_event",
        lambda client_id, event_type, **kw: events.append((client_id, event_type)),
    )
    added = await auto_content.seed_client_content({"id": "c1", "business_name": "Test Biz"})
    assert added == 0
    assert events == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_delivery_ledger_wiring.py -k seed_client_content -v`
Expected: FAIL (no ledger calls wired yet)

- [ ] **Step 3: Wire the calls**

In `app/marketing/auto_content.py`, the block currently reads (lines 523-541):

```python
async def seed_client_content(client: dict[str, Any]) -> int:
    """EK client ka aaj ka content ABHI generate + queue me append (onboarding pe
    instant day-1 value — daily 07:00 sweep ka wait nahi). Same generate→append→
    recycle pattern as run_daily_content; date+type DEDUPE = daily job ke saath
    idempotent (double content nahi banega). Added-count return. KABHI raise nahi."""
    try:
        if not isinstance(client, dict):
            return 0
        cid = str(client.get("id") or "")
        if not cid:
            return 0
        items = await generate_for_client(client)
        added = _append_items(cid, items)
        if not added:
            added = await _recycle_fallback(client)
        return added
    except Exception as e:  # pragma: no cover
        logger.debug(f"[auto_content] seed_client_content skip: {e}")
        return 0
```

Change to:

```python
async def seed_client_content(client: dict[str, Any]) -> int:
    """EK client ka aaj ka content ABHI generate + queue me append (onboarding pe
    instant day-1 value — daily 07:00 sweep ka wait nahi). Same generate→append→
    recycle pattern as run_daily_content; date+type DEDUPE = daily job ke saath
    idempotent (double content nahi banega). Added-count return. KABHI raise nahi."""
    try:
        if not isinstance(client, dict):
            return 0
        cid = str(client.get("id") or "")
        if not cid:
            return 0
        items = await generate_for_client(client)
        added = _append_items(cid, items)
        if not added:
            added = await _recycle_fallback(client)
        if added:
            try:
                from app.platform import delivery_ledger

                delivery_ledger.log_event(cid, "marketing_calendar_generated")
                delivery_ledger.log_event(
                    cid, "post_draft_created", detail=f"{added} drafts", meta={"count": added}
                )
            except Exception as le:  # pragma: no cover
                logger.debug(f"[auto_content] ledger log skip: {le}")
        return added
    except Exception as e:  # pragma: no cover
        logger.debug(f"[auto_content] seed_client_content skip: {e}")
        return 0
```

Batched (one pair of events per call, count in `meta`) — not per-item — matching the spec's explicit anti-spam decision.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_delivery_ledger_wiring.py -k seed_client_content -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the existing auto_content test suite to check for regressions**

Run: `.venv\Scripts\python.exe -m pytest tests/ -k auto_content -v`
Expected: all PASS

---

### Task 7: Wire `automation_failed` into `customer_delivery._record_stuck()`

**Files:**
- Modify: `app/marketing/customer_delivery.py:149-171`
- Test: `tests/test_delivery_ledger_wiring.py` (append)

**Interfaces:**
- Consumes: `app.platform.delivery_ledger.log_event` (Task 2).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_delivery_ledger_wiring.py`:

```python
def test_record_stuck_logs_automation_failed(monkeypatch, tmp_path):
    from app.marketing import customer_delivery as cd

    monkeypatch.setattr(cd, "_STUCK_LOG", str(tmp_path / "stuck.jsonl"))
    events = []
    monkeypatch.setattr(
        "app.platform.delivery_ledger.log_event",
        lambda client_id, event_type, **kw: events.append((client_id, event_type, kw.get("status"))),
    )
    cd._record_stuck({"id": "c1", "business_name": "Test Biz", "phone": "9812345678"}, "no_phone")
    assert ("c1", "automation_failed", "warn") in events
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_delivery_ledger_wiring.py::test_record_stuck_logs_automation_failed -v`
Expected: FAIL (`events == []`)

- [ ] **Step 3: Wire the call**

In `app/marketing/customer_delivery.py`, the block currently reads (lines 149-171):

```python
def _record_stuck(client: dict[str, Any], reason: str) -> None:
    """Fail-LOUD: append a stuck-customer record (NOT a silent debug swallow) so a
    ghosted paying customer is always visible + alertable. Never raises."""
    try:
        os.makedirs("data", exist_ok=True)
        rec = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "client_id": str(client.get("id") or ""),
            "business_name": client.get("business_name"),
            "phone": client.get("phone"),
            "plan": client.get("plan"),
            "reason": reason,
        }
        with open(_STUCK_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("delivery _record_stuck err: %s", exc)
    logger.warning(
        "🚨 PAID customer undelivered: %s (%s) — %s",
        client.get("business_name"),
        client.get("id"),
        reason,
    )
```

Change to:

```python
def _record_stuck(client: dict[str, Any], reason: str) -> None:
    """Fail-LOUD: append a stuck-customer record (NOT a silent debug swallow) so a
    ghosted paying customer is always visible + alertable. Never raises."""
    try:
        os.makedirs("data", exist_ok=True)
        rec = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "client_id": str(client.get("id") or ""),
            "business_name": client.get("business_name"),
            "phone": client.get("phone"),
            "plan": client.get("plan"),
            "reason": reason,
        }
        with open(_STUCK_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("delivery _record_stuck err: %s", exc)
    logger.warning(
        "🚨 PAID customer undelivered: %s (%s) — %s",
        client.get("business_name"),
        client.get("id"),
        reason,
    )
    try:
        from app.platform import delivery_ledger

        delivery_ledger.log_event(
            str(client.get("id") or ""), "automation_failed", detail=reason, status="warn"
        )
    except Exception as le:  # pragma: no cover
        logger.debug("delivery _record_stuck ledger log skip: %s", le)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_delivery_ledger_wiring.py::test_record_stuck_logs_automation_failed -v`
Expected: PASS

- [ ] **Step 5: Run the full existing customer_delivery test suite — this file already exercises `_record_stuck` indirectly, must not regress**

Run: `.venv\Scripts\python.exe -m pytest tests/test_customer_delivery_2026_07_05.py -v`
Expected: all PASS (unchanged — the new ledger call is additive and never raises)

---

### Task 8: Admin "Deliver Now" endpoint

**Files:**
- Modify: `app/api/admin_ops.py` (add new endpoint near the existing `upi_activate`, after line 848)
- Test: `tests/test_admin_deliver_now.py`

**Interfaces:**
- Consumes: `app.marketing.customer_delivery.deliver_client_value(client, force=True)` (existing), `app.platform.delivery_ledger.log_event` (Task 2).
- Produces: `POST /api/admin/clients/{client_id}/deliver-now` → `{"ok": bool, "delivered": bool, "reason": str | None}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_admin_deliver_now.py`:

```python
"""POST /api/admin/clients/{client_id}/deliver-now — human-clicked single-customer
delivery bypass. Never flips AUTO_DELIVER_VALUE; always calls
deliver_client_value(client, force=True), the existing operator bypass."""
from fastapi.testclient import TestClient


def _override_admin(app):
    """Matches the established pattern in tests/test_upi_config.py — overriding
    require_admin replaces the whole dependency, so a plain dict is enough."""
    from app.api.auth_deps import require_admin

    app.dependency_overrides[require_admin] = lambda: {"username": "test"}


def test_deliver_now_success(monkeypatch):
    from app.main import app

    _override_admin(app)
    client = {"id": "c1", "business_name": "Test Biz", "phone": "9812345678", "slug": "s"}
    monkeypatch.setattr("app.marketing.clients_store.get_client", lambda cid: client, raising=False)

    async def _fake_deliver(client, force=False):
        assert force is True
        return {"delivered": True, "client_id": "c1"}

    monkeypatch.setattr("app.marketing.customer_delivery.deliver_client_value", _fake_deliver, raising=False)

    events = []
    monkeypatch.setattr(
        "app.platform.delivery_ledger.log_event",
        lambda client_id, event_type, **kw: events.append((client_id, event_type)),
    )

    with TestClient(app) as c:
        resp = c.post("/api/admin/clients/c1/deliver-now")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["delivered"] is True
    assert ("c1", "admin_manual_action") in events
    app.dependency_overrides.clear()


def test_deliver_now_failure_still_logs_reason(monkeypatch):
    from app.main import app

    _override_admin(app)
    client = {"id": "c2", "business_name": "No Phone Biz", "phone": "", "slug": "s2"}
    monkeypatch.setattr("app.marketing.clients_store.get_client", lambda cid: client, raising=False)

    async def _fake_deliver(client, force=False):
        return {"delivered": False, "skipped": "no_phone"}

    monkeypatch.setattr("app.marketing.customer_delivery.deliver_client_value", _fake_deliver, raising=False)

    events = []
    monkeypatch.setattr(
        "app.platform.delivery_ledger.log_event",
        lambda client_id, event_type, **kw: events.append((client_id, event_type, kw.get("detail"))),
    )

    with TestClient(app) as c:
        resp = c.post("/api/admin/clients/c2/deliver-now")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["delivered"] is False
    assert body["reason"] == "no_phone"
    assert ("c2", "admin_manual_action", "no_phone") in events
    app.dependency_overrides.clear()


def test_deliver_now_unknown_client_404(monkeypatch):
    from app.main import app

    _override_admin(app)
    monkeypatch.setattr("app.marketing.clients_store.get_client", lambda cid: None, raising=False)
    with TestClient(app) as c:
        resp = c.post("/api/admin/clients/does-not-exist/deliver-now")
    assert resp.status_code == 404
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_admin_deliver_now.py -v`
Expected: FAIL with 404 on all (route doesn't exist yet)

- [ ] **Step 3: Add the endpoint**

In `app/api/admin_ops.py`, after the existing `upi_activate` function (which ends at line 848 with the closing of the `except Exception as exc:` block), add:

```python

@router.post("/clients/{client_id}/deliver-now", summary="Human-clicked single-customer delivery unstick")
async def deliver_now(client_id: str, _user=Depends(require_admin)) -> dict:
    """Admin clicks this for one stuck paid customer — calls the existing
    deliver_client_value(force=True) bypass. Never touches AUTO_DELIVER_VALUE;
    always logs admin_manual_action either way so the reason is visible even
    on failure (no phone / send error / already delivered)."""
    from app.marketing import clients_store, customer_delivery
    from app.platform import delivery_ledger

    client = clients_store.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="client not found")

    result = await customer_delivery.deliver_client_value(client, force=True)
    reason = result.get("skipped") or result.get("error")
    try:
        delivery_ledger.log_event(
            client_id,
            "admin_manual_action",
            detail=(reason or "delivered"),
            status="ok" if result.get("delivered") else "warn",
        )
    except Exception as le:  # pragma: no cover
        logger.debug("deliver_now ledger log skip: %s", le)
    return {"ok": True, "delivered": bool(result.get("delivered")), "reason": reason}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_admin_deliver_now.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Duplicate-route check**

Run: `.venv\Scripts\python.exe -c "import ast,glob
paths=set()
for f in glob.glob('app/api/*.py'):
    tree=ast.parse(open(f, encoding='utf-8').read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, 'attr', '') in ('get','post','put','delete'):
            for kw in node.args:
                if isinstance(kw, ast.Constant) and isinstance(kw.value, str) and 'deliver-now' in kw.value:
                    print(f, kw.value)
"`
Expected: exactly one hit, in `app/api/admin_ops.py` — confirms no duplicate route (this was already checked once during planning via Grep with zero hits; this step re-confirms after the edit).

---

### Task 9: Extend admin `/clients/{id}/timeline` with ledger events

**Files:**
- Modify: `app/api/admin_dashboard.py:236-275` (`_build_client_timeline`) and `:315-340` (`get_client_timeline`)
- Test: `tests/test_admin_client_timeline_ledger.py`

**Interfaces:**
- Consumes: `app.platform.delivery_ledger.get_timeline(client_id, audience="admin")` (Task 2).

- [ ] **Step 1: Write the failing test**

Create `tests/test_admin_client_timeline_ledger.py`:

```python
"""GET /api/admin/clients/{id}/timeline must merge delivery-ledger events
alongside the existing agent_events/inquiries/audit sources."""
from fastapi.testclient import TestClient


def test_client_timeline_includes_ledger_events(monkeypatch):
    from app.main import app
    from app.api.auth_deps import require_admin

    app.dependency_overrides[require_admin] = lambda: {"username": "test"}
    monkeypatch.setenv("CLIENT_TIMELINE", "1")

    monkeypatch.setattr("app.platform.team.recent_events", lambda limit=200: [], raising=False)
    monkeypatch.setattr("app.api.admin_dashboard._read_inquiries", lambda: [], raising=False)
    monkeypatch.setattr("app.api.admin_dashboard._fetch_client_audit", lambda client_id, limit=100: [], raising=False)
    monkeypatch.setattr(
        "app.platform.delivery_ledger.get_timeline",
        lambda client_id, limit=100, audience="admin": [
            {"ts": "2026-07-06T09:00:00", "event_type": "plan_activated",
             "label": "Aapka plan activate ho gaya (plan_activated)", "icon": "✅", "detail": "starter", "status": "ok"}
        ],
        raising=False,
    )

    with TestClient(app) as c:
        resp = c.get("/api/admin/clients/c1/timeline")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    kinds = [e["kind"] for e in body["events"]]
    assert "delivery" in kinds
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_admin_client_timeline_ledger.py -v`
Expected: FAIL (`"delivery" not in kinds` — ledger source not merged yet)

- [ ] **Step 3: Merge the ledger source**

In `app/api/admin_dashboard.py`, `_build_client_timeline` currently reads (lines 236-275):

```python
def _build_client_timeline(client_id, agent_events, inquiries, audit, limit=50):
    """Pure merge+sort of per-client events from 3 sources. Newest first."""
    items: list[dict] = []
    for ev in agent_events or []:
        meta = ev.get("meta") or {}
        if str(meta.get("client_id") or "") != str(client_id):
            continue
        items.append(
            {
                "ts": str(ev.get("at") or ""),
                "kind": str(ev.get("action") or "event"),
                "source": "agent",
                "summary": f"{ev.get('member', '')}: {(ev.get('detail') or '')[:120]}".strip(": "),
            }
        )
    for r in inquiries or []:
        if str(r.get("client_id") or "") != str(client_id):
            continue
        items.append(
            {
                # inquiries.jsonl writes the timestamp under "at" (public_site.py)
                "ts": str(r.get("at") or r.get("ts") or r.get("created_at") or ""),
                "kind": "lead",
                "source": "lead",
                "summary": f"Enquiry from {r.get('name') or '-'}",
            }
        )
    for a in audit or []:
        if str(a.get("resource_id") or "") != str(client_id):
            continue
        items.append(
            {
                "ts": str(a.get("created_at") or ""),
                "kind": "audit",
                "source": "audit",
                "summary": str(a.get("action") or "audit"),
            }
        )
    items.sort(key=lambda x: x["ts"], reverse=True)
    return items[: max(1, min(int(limit), 200))]
```

Change to (new `delivery_events` parameter, new loop, updated docstring):

```python
def _build_client_timeline(client_id, agent_events, inquiries, audit, delivery_events=None, limit=50):
    """Pure merge+sort of per-client events from 4 sources. Newest first."""
    items: list[dict] = []
    for ev in agent_events or []:
        meta = ev.get("meta") or {}
        if str(meta.get("client_id") or "") != str(client_id):
            continue
        items.append(
            {
                "ts": str(ev.get("at") or ""),
                "kind": str(ev.get("action") or "event"),
                "source": "agent",
                "summary": f"{ev.get('member', '')}: {(ev.get('detail') or '')[:120]}".strip(": "),
            }
        )
    for r in inquiries or []:
        if str(r.get("client_id") or "") != str(client_id):
            continue
        items.append(
            {
                # inquiries.jsonl writes the timestamp under "at" (public_site.py)
                "ts": str(r.get("at") or r.get("ts") or r.get("created_at") or ""),
                "kind": "lead",
                "source": "lead",
                "summary": f"Enquiry from {r.get('name') or '-'}",
            }
        )
    for a in audit or []:
        if str(a.get("resource_id") or "") != str(client_id):
            continue
        items.append(
            {
                "ts": str(a.get("created_at") or ""),
                "kind": "audit",
                "source": "audit",
                "summary": str(a.get("action") or "audit"),
            }
        )
    for d in delivery_events or []:
        items.append(
            {
                "ts": str(d.get("ts") or ""),
                "kind": "delivery",
                "source": "delivery_ledger",
                "summary": f"{d.get('icon', '')} {d.get('label', '')}".strip(),
            }
        )
    items.sort(key=lambda x: x["ts"], reverse=True)
    return items[: max(1, min(int(limit), 200))]
```

Then `get_client_timeline` currently reads (lines 315-340):

```python
@router.get("/clients/{client_id}/timeline")
async def get_client_timeline(
    client_id: str, limit: int = 50, _user=Depends(require_admin)
) -> dict:
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
        inquiries = _read_inquiries()
    except Exception:
        pass
    try:
        audit = _fetch_client_audit(client_id)
    except Exception:
        audit = []
    events = _build_client_timeline(client_id, agent_events, inquiries, audit, limit)
    return {"enabled": True, "client_id": client_id, "events": events}
```

Change to:

```python
@router.get("/clients/{client_id}/timeline")
async def get_client_timeline(
    client_id: str, limit: int = 50, _user=Depends(require_admin)
) -> dict:
    """B2: unified per-client event trail (agent_events + inquiries + audit + delivery ledger)."""
    if os.getenv("CLIENT_TIMELINE", "0").strip().lower() not in ("1", "true", "yes"):
        return {"enabled": False, "client_id": client_id, "events": []}
    agent_events: list = []
    inquiries: list = []
    audit: list = []
    delivery_events: list = []
    try:
        from app.platform.team import recent_events

        agent_events = recent_events(limit=200)
    except Exception:
        pass
    try:
        inquiries = _read_inquiries()
    except Exception:
        pass
    try:
        audit = _fetch_client_audit(client_id)
    except Exception:
        audit = []
    try:
        from app.platform import delivery_ledger

        delivery_events = delivery_ledger.get_timeline(client_id, limit=100, audience="admin")
    except Exception:
        delivery_events = []
    events = _build_client_timeline(client_id, agent_events, inquiries, audit, delivery_events, limit)
    return {"enabled": True, "client_id": client_id, "events": events}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_admin_client_timeline_ledger.py -v`
Expected: PASS

- [ ] **Step 5: Full admin_dashboard regression check**

Run: `.venv\Scripts\python.exe -m pytest tests/ -k admin_dashboard -v`
Expected: all PASS (no prior test file existed for this module before Task 9's new one, so this mainly guards against import-time breakage — confirm via `prod_check.py` too, see Task 13)

---

### Task 10: Customer-facing timeline endpoint

**Files:**
- Modify: `app/api/customer_dashboard.py` (new endpoint, near `customer_pending_approvals` at line 838)
- Test: `tests/test_customer_timeline_endpoint.py`

**Interfaces:**
- Consumes: `app.platform.delivery_ledger.get_timeline(client_id, audience="customer")` (Task 2), `app.api.customer_auth.require_customer` (existing — IDOR-safe client_id resolution).
- Produces: `GET /api/customer/timeline` → `{"ok": true, "events": [...]}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_customer_timeline_endpoint.py`:

```python
"""GET /api/customer/timeline — customer-facing 'AI ne aapke liye kya kiya'.
Must be scoped to the caller's OWN client_id only (require_customer, same
IDOR-safe pattern as every other /api/customer/* route)."""
from fastapi.testclient import TestClient


def test_customer_timeline_returns_own_events_only(monkeypatch):
    from app.main import app
    from app.api.customer_auth import require_customer

    app.dependency_overrides[require_customer] = lambda: "client_A"

    def _fake_get_timeline(client_id, limit=30, audience="customer"):
        assert client_id == "client_A"  # never leaks another client's id
        assert audience == "customer"
        return [{"ts": "2026-07-06T09:00:00", "event_type": "plan_activated",
                 "label": "Aapka plan activate ho gaya", "icon": "✅", "detail": "", "status": "ok"}]

    monkeypatch.setattr("app.platform.delivery_ledger.get_timeline", _fake_get_timeline, raising=False)

    with TestClient(app) as c:
        resp = c.get("/api/customer/timeline")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert len(body["events"]) == 1
    assert body["events"][0]["label"] == "Aapka plan activate ho gaya"
    # Technical event_type/detail must not leak to the customer-facing payload's
    # raw form beyond what get_timeline(audience="customer") already redacted.
    app.dependency_overrides.clear()


def test_customer_timeline_empty_state_is_graceful(monkeypatch):
    from app.main import app
    from app.api.customer_auth import require_customer

    app.dependency_overrides[require_customer] = lambda: "client_B"
    monkeypatch.setattr("app.platform.delivery_ledger.get_timeline", lambda *a, **k: [], raising=False)

    with TestClient(app) as c:
        resp = c.get("/api/customer/timeline")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["events"] == []
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_customer_timeline_endpoint.py -v`
Expected: FAIL with 404 (route doesn't exist yet)

- [ ] **Step 3: Add the endpoint**

In `app/api/customer_dashboard.py`, right before the existing `customer_pending_approvals` (line 838), add:

```python
@router.get("/timeline")
def customer_delivery_timeline(client_id: str = Depends(require_customer), limit: int = 30) -> dict:
    """'AI ne aapke liye kya kiya' — customer's own delivery-ledger timeline.
    client_id JWT (require_customer) se aata hai => customer sirf apni hi
    timeline dekhta hai. Never raises; empty list on any error."""
    try:
        from app.platform import delivery_ledger

        events = delivery_ledger.get_timeline(client_id, limit=limit, audience="customer")
        return {"ok": True, "events": events}
    except Exception as e:
        logger.debug("customer timeline failed: %s", e)
        return {"ok": False, "events": []}


```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_customer_timeline_endpoint.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Duplicate-route + full customer_dashboard regression check**

Run: `.venv\Scripts\python.exe -m pytest tests/ -k customer_dashboard -v`
Expected: all PASS

---

### Task 11: Customer-facing UI — "AI ne aapke liye kya kiya" section (combo fork pilot)

**Files:**
- Modify: `frontend/customer_dashboard.html` (Account view section — see `docs/superpowers/specs/2026-07-05-customer-dashboard-ux-redesign-design.md` §4 for where the Account view's `data-view` section lives; billing/webhook/security cards are already there)
- Test: `tests/test_customer_dashboard_timeline_section.py`

**Interfaces:**
- Consumes: `GET /api/customer/timeline` (Task 10).

- [ ] **Step 1: Write the failing test**

Create `tests/test_customer_dashboard_timeline_section.py`:

```python
"""Cheap static-HTML guard (mirrors tests/test_office_map_frontend.py's style):
confirms the ledger timeline section exists and stays inside the Account view,
not competing with Home's one-job-above-the-fold rule."""


def test_combo_dashboard_has_timeline_section_in_account_view():
    html = open("frontend/customer_dashboard.html", encoding="utf-8").read()
    assert 'id="deliveryTimelineCard"' in html
    # Must live inside an account-view section (verified real attribute:
    # data-view="account", e.g. line 795's #billingCard), placed after
    # #billingCard (line 795) — not inside the home hero area (line 508+).
    billing_pos = html.index('id="billingCard"')
    timeline_pos = html.index('id="deliveryTimelineCard"')
    home_hero_pos = html.index('data-view="home" class="owner-hero"')
    assert timeline_pos > billing_pos
    assert not (home_hero_pos < timeline_pos < home_hero_pos + 2000), (
        "timeline card must not be crammed into the Home hero area"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_customer_dashboard_timeline_section.py -v`
Expected: FAIL (`'id="deliveryTimelineCard"' in html` is False)

- [ ] **Step 3: Add the card after `#billingCard` (line 795-845), matching its verified real markup style**

`frontend/customer_dashboard.html:795-845` shows the real card shell classes: `class="card"` on the outer div, `class="card-h"` for the header row (not `card-header`), `class="card-b"` for the body (not `card-body`). Line 1603 has a real, already-defined auth helper: `function billAuthHdr(){ const t=billToken(); return t ? {"Authorization":"Bearer "+t} : {}; }` — reuse it directly rather than inventing a new helper. Insert the new card immediately after `#billingCard`'s closing `</div>` (line 845), before the `<!-- ===== 8) Customer Webhooks -->` comment (line 847):

```html
<div data-view="account" class="card" id="deliveryTimelineCard">
  <div class="card-h">
    <h2 style="font-size:13px">🤖 AI ne aapke liye kya kiya</h2>
    <span class="grow"></span>
    <button class="btn" onclick="toggleTimelineCard()" id="timelineToggleBtn">▾</button>
  </div>
  <div id="timelineBody" class="card-b">
    <div id="timelineEmpty" class="sm" style="color:var(--muted);display:none">Abhi tak koi activity nahi — jaise hi kuch hota hai, yahan dikhega.</div>
    <ul id="timelineList" style="list-style:none;padding:0;margin:0;"></ul>
  </div>
</div>
```

Then add the fetch/render script (near the other fetch functions, e.g. right after `billAuthHdr`'s definition around line 1603):

```html
<script>
function toggleTimelineCard() {
  const body = document.getElementById('timelineBody');
  body.style.display = body.style.display === 'none' ? 'block' : 'none';
}

async function loadDeliveryTimeline() {
  try {
    const res = await fetch('/api/customer/timeline', { headers: billAuthHdr() });
    const data = await res.json();
    const list = document.getElementById('timelineList');
    const empty = document.getElementById('timelineEmpty');
    list.innerHTML = '';
    if (!data.events || data.events.length === 0) {
      empty.style.display = 'block';
      return;
    }
    empty.style.display = 'none';
    data.events.forEach(function (ev) {
      const li = document.createElement('li');
      li.style.padding = '6px 0';
      li.textContent = (ev.icon || '') + ' ' + ev.label + ' — ' + new Date(ev.ts).toLocaleDateString('en-IN');
      list.appendChild(li);
    });
  } catch (e) {
    console.debug('timeline load failed', e);
  }
}
document.addEventListener('DOMContentLoaded', loadDeliveryTimeline);
</script>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_customer_dashboard_timeline_section.py -v`
Expected: PASS

- [ ] **Step 5: Verify in the browser**

Use the `preview_start` / `preview_*` tools (per this session's standing instructions) to launch the dev server, log in as a test customer on the combo dashboard, switch to the Account view, and confirm: the card renders, shows the empty state gracefully for a client with zero events, expands/collapses, and does not appear above the fold on Home (390px viewport check). Screenshot before reporting this task done.

---

### Task 12: Port the timeline section to the other 2 customer dashboard forks

**Files:**
- Modify: `frontend/customer_marketing.html`, `frontend/customer_voice.html` (same Account-view card + script as Task 11)
- Test: extend `tests/test_customer_dashboard_timeline_section.py`

**Interfaces:**
- Consumes: same `GET /api/customer/timeline` (Task 10) — no backend changes in this task.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_customer_dashboard_timeline_section.py`:

```python
def test_marketing_fork_has_timeline_section():
    html = open("frontend/customer_marketing.html", encoding="utf-8").read()
    assert 'id="deliveryTimelineCard"' in html


def test_voice_fork_has_timeline_section():
    html = open("frontend/customer_voice.html", encoding="utf-8").read()
    assert 'id="deliveryTimelineCard"' in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_customer_dashboard_timeline_section.py -k "marketing_fork or voice_fork" -v`
Expected: FAIL (both forks missing the section)

- [ ] **Step 3: Add the same card + script to both forks**

Both forks were verified to share the exact same real markup/helper as the combo dashboard: `data-view="account" class="card" id="billingCard"` (`customer_marketing.html:917`, `customer_voice.html:746`) and `function billAuthHdr(){...}` (`customer_marketing.html:1804`, `customer_voice.html:1476`). In **both** files, insert immediately after `#billingCard`'s closing `</div>`:

```html
<div data-view="account" class="card" id="deliveryTimelineCard">
  <div class="card-h">
    <h2 style="font-size:13px">🤖 AI ne aapke liye kya kiya</h2>
    <span class="grow"></span>
    <button class="btn" onclick="toggleTimelineCard()" id="timelineToggleBtn">▾</button>
  </div>
  <div id="timelineBody" class="card-b">
    <div id="timelineEmpty" class="sm" style="color:var(--muted);display:none">Abhi tak koi activity nahi — jaise hi kuch hota hai, yahan dikhega.</div>
    <ul id="timelineList" style="list-style:none;padding:0;margin:0;"></ul>
  </div>
</div>
```

And, near each file's own `billAuthHdr` definition (`customer_marketing.html:1804`, `customer_voice.html:1476`):

```html
<script>
function toggleTimelineCard() {
  const body = document.getElementById('timelineBody');
  body.style.display = body.style.display === 'none' ? 'block' : 'none';
}

async function loadDeliveryTimeline() {
  try {
    const res = await fetch('/api/customer/timeline', { headers: billAuthHdr() });
    const data = await res.json();
    const list = document.getElementById('timelineList');
    const empty = document.getElementById('timelineEmpty');
    list.innerHTML = '';
    if (!data.events || data.events.length === 0) {
      empty.style.display = 'block';
      return;
    }
    empty.style.display = 'none';
    data.events.forEach(function (ev) {
      const li = document.createElement('li');
      li.style.padding = '6px 0';
      li.textContent = (ev.icon || '') + ' ' + ev.label + ' — ' + new Date(ev.ts).toLocaleDateString('en-IN');
      list.appendChild(li);
    });
  } catch (e) {
    console.debug('timeline load failed', e);
  }
}
document.addEventListener('DOMContentLoaded', loadDeliveryTimeline);
</script>
```

This card carries no `.marketing-only`/`.voice-only` class — it is gating-neutral and should show in both forks (per the redesign spec's fork-gating mechanism, only cards with those classes get hidden by the `prod-marketing`/`prod-voice` body-class CSS).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_customer_dashboard_timeline_section.py -v`
Expected: PASS (all 3 fork tests green)

- [ ] **Step 5: Verify both forks in the browser**

Repeat Task 11 Step 5's browser verification for `customer_marketing.html` and `customer_voice.html` (login as a marketing-plan test customer, then a voice-plan test customer). Confirm no `prod-marketing`/`prod-voice` gating leakage (the redesign's R2 risk from its own spec) — the new card must render identically in both, nothing else on the page should change.

---

### Task 13: Full sub-project verification gate

**Files:** none (verification only)

- [ ] **Step 1: Run every new/modified test file together**

Run: `.venv\Scripts\python.exe -m pytest tests/test_delivery_event_model.py tests/test_delivery_ledger.py tests/test_delivery_ledger_wiring.py tests/test_admin_deliver_now.py tests/test_admin_client_timeline_ledger.py tests/test_customer_timeline_endpoint.py tests/test_customer_dashboard_timeline_section.py -v`
Expected: all PASS

- [ ] **Step 2: Re-run the pre-existing suites this plan touched, to confirm zero regressions**

Run: `.venv\Scripts\python.exe -m pytest tests/test_customer_delivery_2026_07_05.py tests/test_billing_truth_2026.py -v`
Expected: all PASS (billing-truth must stay green — this plan never touches `packages.py`)

- [ ] **Step 3: Production gate**

Run: `.venv\Scripts\python.exe scripts\prod_check.py`
Expected: PASS

- [ ] **Step 4: Secrets scan**

Run: `.venv\Scripts\python.exe scripts\check_secrets.py`
Expected: clean diff (this plan never touches `.env` or hardcodes any key)

- [ ] **Step 5: Lint the new/modified Python files**

Run: `.venv\Scripts\python.exe -m ruff check app/models/delivery_event.py app/platform/delivery_ledger.py app/marketing/clients_store.py app/billing/usage.py app/marketing/onboarding.py app/marketing/auto_content.py app/marketing/customer_delivery.py app/api/admin_ops.py app/api/admin_dashboard.py app/api/customer_dashboard.py`
Expected: no errors

- [ ] **Step 6: Report status**

Summarize: which of the mission's Phase 6 test asks this sub-project satisfies now (paid customer sees dashboard timeline ✓, admin sees customer delivery status ✓, delivery ledger records automation events ✓) and which remain for later sub-projects (blocked-social-connection state, Marketing Calendar draft/approved/published/failed badges, Setup Wizard, nav/page hide-merge mapping). Do not commit, push, or deploy — wait for the user's explicit instruction.
