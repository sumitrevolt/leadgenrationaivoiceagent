# Lead-Gen Funnel Pipeline Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Instrument the already-scheduled `prospector.py` lead-ingestion run with first-class batch/stage/quality-issue tracking, close the confirmed data-quality gaps (scattered dedup, no quarantine, duplicated scoring thresholds, scattered outreach-eligibility gates, no pre-send provider-health check, incomplete `Interaction` wiring), and surface pipeline health in the existing admin dashboard + a simplified customer summary — without building a second parallel pipeline system.

**Architecture:** Three new SQLAlchemy models (`LeadPipelineBatch`/`LeadPipelineStageRun`/`LeadPipelineQualityIssue`) plus two new columns on the existing `Lead` model, all following the minimal `AgentEvent`-style convention already established in this codebase. A small never-raise helper module (`pipeline_batch.py`) wraps writes to these tables so `prospector.py`'s real ingestion behavior can never be broken by an observability bug. Existing per-channel gates (compliance/email/WhatsApp) are wrapped, not rewritten, behind one `is_outreach_eligible()` function.

**Tech Stack:** FastAPI, SQLAlchemy (sync sessions via `get_db_session()`), Alembic, pytest, existing Jinja-free server-rendered HTML dashboards.

## Global Constraints

- No BigQuery, Spark, Kafka, Kestra, dbt, or Terraform — free-stack/single-VPS only (user's explicit hard rule).
- Never duplicate an existing table/route — reuse `Interaction`/`interaction_log.py` for events, `dlq_retry.py` for task-level retry; this plan's new tables are additive only.
- Every new DB write in the observability layer (`pipeline_batch.py`) must be never-raise / best-effort — matches `automation_health.py`/`integration_health.py`/`_persist_prospect_to_db()`'s existing convention.
- Pre-send health checks must be **fail-open** (never block a real send/call due to a health-check glitch).
- Admin-only endpoints require `Depends(require_admin)` — matches the 2026-07-01 production-audit fix pattern.
- No new page — extend `frontend/admin_dashboard.html`'s existing nav-group/card pattern (see `memory/decisions.md` ADR-047, same session — 6-group nav, `data-view`-free plain cards).
- Verify gate for every task: `.venv\Scripts\python.exe -m pytest <task's test file> -q` green, plus a full-suite targeted sweep + `prod_check.py` + `check_secrets.py` at the end (Task 11).
- Full design context: `docs/superpowers/specs/2026-07-08-lead-gen-pipeline-automation-design.md`.

---

### Task 1: New pipeline models + migration + `Lead` column additions

**Files:**
- Create: `app/models/lead_pipeline.py`
- Modify: `app/models/__init__.py` (register new models — check current content first, follow its existing registration pattern for `CustomerDeliverable`/`Interaction`)
- Modify: `app/models/lead.py:280-284` (`update_score()` — centralize threshold + persist reason), add `score_reason`/`source_batch_id` columns near `qualification_data` (~line 128)
- Modify: `app/config.py` (add `lead_hot_threshold`/`lead_warm_threshold` near `outreach_daily_cap`, ~line 140)
- Create: `alembic/versions/012_add_lead_pipeline_tables.py`
- Test: `tests/test_lead_pipeline_models.py`

**Interfaces:**
- Produces: `LeadPipelineBatch`, `LeadPipelineStageRun`, `LeadPipelineQualityIssue` (SQLAlchemy models, importable from `app.models.lead_pipeline`); `Lead.score_reason: str|None`, `Lead.source_batch_id: str|None`; `settings.lead_hot_threshold: int` (default 70), `settings.lead_warm_threshold: int` (default 40).

- [ ] **Step 1: Write the failing model test**

```python
# tests/test_lead_pipeline_models.py
"""Model-shape tests for the lead-gen pipeline batch tracking tables
(2026-07-08 pipeline-automation vertical slice)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.lead import Lead, LeadSource, LeadStatus
from app.models.lead_pipeline import (
    LeadPipelineBatch,
    LeadPipelineQualityIssue,
    LeadPipelineStageRun,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_batch_defaults_and_roundtrip():
    db = _session()
    batch = LeadPipelineBatch(id="b1", source="prospector", niche="dentist", city="pune")
    db.add(batch)
    db.commit()
    row = db.get(LeadPipelineBatch, "b1")
    assert row.status == "pending"
    assert row.total_raw == 0
    assert row.source == "prospector"


def test_stage_run_links_to_batch():
    db = _session()
    db.add(LeadPipelineBatch(id="b2", source="prospector"))
    db.commit()
    db.add(LeadPipelineStageRun(id="s1", batch_id="b2", stage_name="ingestion", status="passed", output_count=5))
    db.commit()
    row = db.get(LeadPipelineStageRun, "s1")
    assert row.batch_id == "b2"
    assert row.output_count == 5


def test_quality_issue_defaults_unresolved():
    db = _session()
    db.add(LeadPipelineBatch(id="b3", source="prospector"))
    db.commit()
    db.add(
        LeadPipelineQualityIssue(
            id="q1", batch_id="b3", stage_name="ingestion",
            issue_type="zero_output", severity="warning", message="0 raw leads",
        )
    )
    db.commit()
    row = db.get(LeadPipelineQualityIssue, "q1")
    assert row.resolved is False
    assert row.severity == "warning"


def test_lead_has_score_reason_and_source_batch_id_columns():
    db = _session()
    lead = Lead(
        id="l1", company_name="Test Co", phone="9198765432 10".replace(" ", ""),
        status=LeadStatus.NEW, source=LeadSource.GOOGLE_MAPS,
        score_reason="niche_fit+recency", source_batch_id="b1",
    )
    db.add(lead)
    db.commit()
    row = db.get(Lead, "l1")
    assert row.score_reason == "niche_fit+recency"
    assert row.source_batch_id == "b1"


def test_update_score_uses_centralized_threshold_and_persists_reason(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "lead_hot_threshold", 65)
    lead = Lead(id="l2", company_name="X", phone="9198765432 11".replace(" ", ""),
                status=LeadStatus.NEW, source=LeadSource.MANUAL)
    lead.update_score(70, reason="high intent")
    assert lead.is_hot_lead is True
    assert lead.score_reason == "high intent"
    lead.update_score(60, reason="lower intent")
    assert lead.is_hot_lead is False
    assert lead.score_reason == "lower intent"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_lead_pipeline_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.lead_pipeline'` (and `AttributeError`/`TypeError` on `score_reason`/`source_batch_id`/`update_score(reason=...)` once that import is fixed).

- [ ] **Step 3: Create `app/models/lead_pipeline.py`**

```python
"""Lead-gen funnel pipeline batch tracking (2026-07-08).

Instruments the already-scheduled prospector.py daily run with first-class
batch/stage/quality-issue records so a broken scraper or a silent
data-quality regression is visible in the admin dashboard instead of only
surfacing weeks later as "0 replies". Deliberately NOT a new parallel
pipeline system — reuses app.models.interaction.Interaction for
per-lead/per-channel events and app.platform.dlq_retry for task-level
retry. See docs/superpowers/specs/2026-07-08-lead-gen-pipeline-automation-design.md.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text

from app.models.base import Base


class LeadPipelineBatch(Base):
    """One row per prospector.py ingestion run: what ran, how many leads
    made it through each phase, whether anything failed."""

    __tablename__ = "lead_pipeline_batches"
    __table_args__ = (
        Index("ix_pipeline_batches_source_time", "source", "created_at"),
        Index("ix_pipeline_batches_status_time", "status", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source = Column(String(30), nullable=False, default="prospector")
    niche = Column(String(50))
    city = Column(String(100))
    status = Column(String(20), nullable=False, default="pending")  # pending|running|completed|partial_failed|failed
    total_raw = Column(Integer, default=0)
    total_duplicate = Column(Integer, default=0)
    total_invalid = Column(Integer, default=0)
    total_valid = Column(Integer, default=0)
    total_scored = Column(Integer, default=0)
    total_eligible = Column(Integer, default=0)
    total_outreach_created = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class LeadPipelineStageRun(Base):
    """Per-stage counts within one batch (ingestion/dedup/validation/scoring)."""

    __tablename__ = "lead_pipeline_stage_runs"
    __table_args__ = (Index("ix_pipeline_stage_runs_batch", "batch_id", "stage_name"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    batch_id = Column(String(36), ForeignKey("lead_pipeline_batches.id"), nullable=False, index=True)
    stage_name = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending|running|passed|warning|failed
    input_count = Column(Integer, default=0)
    output_count = Column(Integer, default=0)
    rejected_count = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)


class LeadPipelineQualityIssue(Base):
    """A data-quality signal for a batch — distinct from dlq_retry.py's
    task-level failure queue. e.g. "38% duplicate rate", "scraper returned
    zero leads", "provider disabled". Drives the admin 'Today's Pipeline
    Problems' view."""

    __tablename__ = "lead_pipeline_quality_issues"
    __table_args__ = (
        Index("ix_pipeline_issues_batch", "batch_id", "created_at"),
        Index("ix_pipeline_issues_resolved", "resolved", "severity"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    batch_id = Column(String(36), ForeignKey("lead_pipeline_batches.id"), nullable=False, index=True)
    stage_name = Column(String(30), nullable=False)
    issue_type = Column(String(40), nullable=False)
    severity = Column(String(10), nullable=False, default="warning")  # info|warning|critical
    message = Column(Text)
    resolved = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
```

- [ ] **Step 4: Read `app/models/__init__.py` and register the 3 new models**

Read the file first — follow whatever pattern it already uses for `CustomerDeliverable`/`Interaction` (likely a plain import so `Base.metadata` sees them for `create_all()`/Alembic autogeneration). Add:

```python
from app.models.lead_pipeline import (  # noqa: F401
    LeadPipelineBatch,
    LeadPipelineQualityIssue,
    LeadPipelineStageRun,
)
```

- [ ] **Step 5: Add `score_reason`/`source_batch_id` columns to `app/models/lead.py`**

Read lines 120-150 first to confirm the exact surrounding code, then add (near `qualification_data`, before the `# Status tracking` block):

```python
    score_reason = Column(Text)  # WHY this score — persisted, not just computed on demand (2026-07-08)
    source_batch_id = Column(String(36), ForeignKey("lead_pipeline_batches.id"), nullable=True, index=True)
```

- [ ] **Step 6: Fix `update_score()` to use the centralized threshold and persist reason**

Replace lines 280-284:

```python
    def update_score(self, new_score: int, reason: str | None = None) -> None:
        """Update lead score and hot lead flag. `reason` (optional, e.g. from
        lead_scoring.score_components()) is persisted so admin/reporting can
        see WHY a lead is hot, not just the number. Threshold centralized in
        settings.lead_hot_threshold (2026-07-08 — previously hardcoded 70 here
        while lead_scoring.py's own env default was 60; both now read the
        same setting, see docs/superpowers/specs/2026-07-08-lead-gen-pipeline-automation-design.md)."""
        from app.config import settings

        self.lead_score = max(0, min(100, new_score))  # Clamp between 0-100
        self.is_hot_lead = self.lead_score >= settings.lead_hot_threshold
        if reason is not None:
            self.score_reason = reason[:2000]
        self.updated_at = datetime.utcnow()
```

- [ ] **Step 7: Add centralized threshold settings to `app/config.py`**

Read lines 130-147 first to confirm current content, then add after `outreach_daily_cap` (~line 140):

```python
    # Hot/warm lead-score thresholds, SINGLE source of truth (2026-07-08 pipeline-
    # automation audit found this hardcoded inconsistently: 60 in lead_scoring.py's
    # env default vs 70 in models/lead.py/call_manager.py/campaign.py. 70 chosen as
    # canonical (3 of 4 call sites + TASKS.md's own "70+" convention already used it).
    lead_hot_threshold: int = 70
    lead_warm_threshold: int = 40
```

- [ ] **Step 8: Create the migration**

```python
# alembic/versions/012_add_lead_pipeline_tables.py
"""lead_pipeline_batches / lead_pipeline_stage_runs / lead_pipeline_quality_issues
tables + leads.score_reason / leads.source_batch_id columns (2026-07-08, lead-gen
pipeline automation vertical slice — see
docs/superpowers/specs/2026-07-08-lead-gen-pipeline-automation-design.md).

Idempotent: skip if a table/column already exists — same pattern as
008_add_agents_agent_events.py / 011_add_customer_deliverable.py. Never ALTERs
an existing table's existing columns, only adds genuinely new tables/columns.

Revision ID: 012_add_lead_pipeline_tables
Revises: 011_add_customer_deliverable
"""

import sqlalchemy as sa

from alembic import op

revision = "012_add_lead_pipeline_tables"
down_revision = "011_add_customer_deliverable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if "lead_pipeline_batches" not in existing:
        op.create_table(
            "lead_pipeline_batches",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("source", sa.String(30), nullable=False, server_default="prospector"),
            sa.Column("niche", sa.String(50)),
            sa.Column("city", sa.String(100)),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("total_raw", sa.Integer(), server_default="0"),
            sa.Column("total_duplicate", sa.Integer(), server_default="0"),
            sa.Column("total_invalid", sa.Integer(), server_default="0"),
            sa.Column("total_valid", sa.Integer(), server_default="0"),
            sa.Column("total_scored", sa.Integer(), server_default="0"),
            sa.Column("total_eligible", sa.Integer(), server_default="0"),
            sa.Column("total_outreach_created", sa.Integer(), server_default="0"),
            sa.Column("error_count", sa.Integer(), server_default="0"),
            sa.Column("started_at", sa.DateTime()),
            sa.Column("completed_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_pipeline_batches_source_time", "lead_pipeline_batches", ["source", "created_at"])
        op.create_index("ix_pipeline_batches_status_time", "lead_pipeline_batches", ["status", "created_at"])

    if "lead_pipeline_stage_runs" not in existing:
        op.create_table(
            "lead_pipeline_stage_runs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("batch_id", sa.String(36), sa.ForeignKey("lead_pipeline_batches.id"), nullable=False),
            sa.Column("stage_name", sa.String(30), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("input_count", sa.Integer(), server_default="0"),
            sa.Column("output_count", sa.Integer(), server_default="0"),
            sa.Column("rejected_count", sa.Integer(), server_default="0"),
            sa.Column("error_message", sa.Text()),
            sa.Column("started_at", sa.DateTime()),
            sa.Column("completed_at", sa.DateTime()),
        )
        op.create_index("ix_pipeline_stage_runs_batch", "lead_pipeline_stage_runs", ["batch_id", "stage_name"])

    if "lead_pipeline_quality_issues" not in existing:
        op.create_table(
            "lead_pipeline_quality_issues",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("batch_id", sa.String(36), sa.ForeignKey("lead_pipeline_batches.id"), nullable=False),
            sa.Column("stage_name", sa.String(30), nullable=False),
            sa.Column("issue_type", sa.String(40), nullable=False),
            sa.Column("severity", sa.String(10), nullable=False, server_default="warning"),
            sa.Column("message", sa.Text()),
            sa.Column("resolved", sa.Boolean(), server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_pipeline_issues_batch", "lead_pipeline_quality_issues", ["batch_id", "created_at"])
        op.create_index("ix_pipeline_issues_resolved", "lead_pipeline_quality_issues", ["resolved", "severity"])

    lead_cols = {c["name"] for c in inspector.get_columns("leads")}
    if "score_reason" not in lead_cols:
        op.add_column("leads", sa.Column("score_reason", sa.Text()))
    if "source_batch_id" not in lead_cols:
        op.add_column(
            "leads",
            sa.Column("source_batch_id", sa.String(36), sa.ForeignKey("lead_pipeline_batches.id"), nullable=True),
        )


def downgrade() -> None:
    for tbl in ("lead_pipeline_quality_issues", "lead_pipeline_stage_runs", "lead_pipeline_batches"):
        try:
            op.drop_table(tbl)
        except Exception:
            pass
    try:
        op.drop_column("leads", "source_batch_id")
    except Exception:
        pass
    try:
        op.drop_column("leads", "score_reason")
    except Exception:
        pass
```

- [ ] **Step 9: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_lead_pipeline_models.py -v`
Expected: 5 passed.

- [ ] **Step 10: Run `alembic upgrade head` against a throwaway SQLite DB to verify the migration applies cleanly**

Run: `.venv\Scripts\python.exe -m alembic upgrade head` (against whatever local dev DB `alembic.ini` points at — confirm it's not a shared/prod DB first)
Expected: no errors; `012_add_lead_pipeline_tables` becomes the new head.

- [ ] **Step 11: Commit**

```bash
git add app/models/lead_pipeline.py app/models/__init__.py app/models/lead.py app/config.py alembic/versions/012_add_lead_pipeline_tables.py tests/test_lead_pipeline_models.py
git commit -m "feat(pipeline): add lead pipeline batch/stage/issue tables + centralized scoring threshold"
```

---

### Task 2: Batch/stage/issue tracking helper module

**Files:**
- Create: `app/platform/pipeline_batch.py`
- Test: `tests/test_pipeline_batch_helpers.py`

**Interfaces:**
- Consumes: `LeadPipelineBatch`/`LeadPipelineStageRun`/`LeadPipelineQualityIssue` (Task 1), `app.models.base.get_db_session`.
- Produces: `start_batch(source, niche=None, city=None) -> str|None`, `start_stage(batch_id, stage_name, input_count=0) -> str|None`, `complete_stage(stage_id, status, output_count=0, rejected_count=0, error_message=None) -> None`, `log_issue(batch_id, stage_name, issue_type, severity="warning", message="") -> None`, `complete_batch(batch_id, counters: dict, status=None) -> None`. All never-raise.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline_batch_helpers.py
"""pipeline_batch.py helpers: never-raise, correct writes (2026-07-08)."""
from __future__ import annotations

import app.platform.pipeline_batch as pb


def test_full_batch_lifecycle_writes_expected_rows():
    from app.models.base import get_db_session
    from app.models.lead_pipeline import LeadPipelineBatch, LeadPipelineQualityIssue, LeadPipelineStageRun

    batch_id = pb.start_batch("prospector", niche="dentist", city="pune")
    assert batch_id is not None

    stage_id = pb.start_stage(batch_id, "ingestion", input_count=10)
    assert stage_id is not None
    pb.complete_stage(stage_id, "passed", output_count=8, rejected_count=2)

    pb.log_issue(batch_id, "ingestion", "high_duplicate_rate", severity="warning", message="20% duplicate")

    pb.complete_batch(batch_id, {"total_raw": 10, "total_valid": 8, "total_duplicate": 2}, status="completed")

    with get_db_session() as db:
        batch = db.get(LeadPipelineBatch, batch_id)
        assert batch.status == "completed"
        assert batch.total_raw == 10
        assert batch.total_valid == 8

        stage = db.get(LeadPipelineStageRun, stage_id)
        assert stage.status == "passed"
        assert stage.output_count == 8

        issues = db.query(LeadPipelineQualityIssue).filter_by(batch_id=batch_id).all()
        assert len(issues) == 1
        assert issues[0].issue_type == "high_duplicate_rate"


def test_all_helpers_never_raise_on_db_error(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr("app.models.base.get_db_session", _boom)
    assert pb.start_batch("prospector") is None
    assert pb.start_stage("fake-batch", "ingestion") is None
    pb.complete_stage("fake-stage", "passed")  # must not raise
    pb.log_issue("fake-batch", "ingestion", "zero_output")  # must not raise
    pb.complete_batch("fake-batch", {"total_raw": 1})  # must not raise


def test_complete_stage_and_log_issue_noop_on_missing_batch_id():
    pb.complete_stage(None, "passed")  # must not raise
    pb.log_issue(None, "ingestion", "zero_output")  # must not raise
    pb.complete_batch(None, {})  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pipeline_batch_helpers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.platform.pipeline_batch'`.

- [ ] **Step 3: Create `app/platform/pipeline_batch.py`**

```python
"""Batch/stage/quality-issue tracking helpers for the lead-gen funnel
(2026-07-08). Pure instrumentation — every function is never-raise
(best-effort), matching automation_health.py/integration_health.py's
existing convention. Never blocks or changes prospector.py's real
ingestion behavior."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)


def start_batch(source: str, niche: str | None = None, city: str | None = None) -> str | None:
    """Create a new LeadPipelineBatch row, return its id. Never raises."""
    try:
        from app.models.base import get_db_session
        from app.models.lead_pipeline import LeadPipelineBatch

        batch_id = str(uuid.uuid4())
        with get_db_session() as db:
            db.add(
                LeadPipelineBatch(
                    id=batch_id, source=source, niche=niche, city=city,
                    status="running", started_at=datetime.utcnow(),
                )
            )
            db.commit()
        return batch_id
    except Exception as e:
        logger.debug(f"[pipeline_batch] start_batch skipped: {e}")
        return None


def start_stage(batch_id: str | None, stage_name: str, input_count: int = 0) -> str | None:
    """Create a LeadPipelineStageRun row for this batch. Never raises."""
    if not batch_id:
        return None
    try:
        from app.models.base import get_db_session
        from app.models.lead_pipeline import LeadPipelineStageRun

        stage_id = str(uuid.uuid4())
        with get_db_session() as db:
            db.add(
                LeadPipelineStageRun(
                    id=stage_id, batch_id=batch_id, stage_name=stage_name,
                    status="running", input_count=input_count, started_at=datetime.utcnow(),
                )
            )
            db.commit()
        return stage_id
    except Exception as e:
        logger.debug(f"[pipeline_batch] start_stage({stage_name}) skipped: {e}")
        return None


def complete_stage(
    stage_id: str | None, status: str, output_count: int = 0,
    rejected_count: int = 0, error_message: str | None = None,
) -> None:
    """Mark a stage run complete. Never raises."""
    if not stage_id:
        return
    try:
        from app.models.base import get_db_session
        from app.models.lead_pipeline import LeadPipelineStageRun

        with get_db_session() as db:
            row = db.get(LeadPipelineStageRun, stage_id)
            if row is None:
                return
            row.status = status
            row.output_count = output_count
            row.rejected_count = rejected_count
            row.error_message = error_message
            row.completed_at = datetime.utcnow()
            db.commit()
    except Exception as e:
        logger.debug(f"[pipeline_batch] complete_stage skipped: {e}")


def log_issue(
    batch_id: str | None, stage_name: str, issue_type: str,
    severity: str = "warning", message: str = "",
) -> None:
    """Record a data-quality issue. Never raises."""
    if not batch_id:
        return
    try:
        from app.models.base import get_db_session
        from app.models.lead_pipeline import LeadPipelineQualityIssue

        with get_db_session() as db:
            db.add(
                LeadPipelineQualityIssue(
                    id=str(uuid.uuid4()), batch_id=batch_id, stage_name=stage_name,
                    issue_type=issue_type, severity=severity, message=message,
                )
            )
            db.commit()
    except Exception as e:
        logger.debug(f"[pipeline_batch] log_issue skipped: {e}")


def complete_batch(batch_id: str | None, counters: dict, status: str | None = None) -> None:
    """Write final counters onto the batch row and mark it completed.
    `counters` keys should match LeadPipelineBatch's total_* columns. Never raises."""
    if not batch_id:
        return
    try:
        from app.models.base import get_db_session
        from app.models.lead_pipeline import LeadPipelineBatch

        with get_db_session() as db:
            row = db.get(LeadPipelineBatch, batch_id)
            if row is None:
                return
            for key, value in counters.items():
                if hasattr(row, key):
                    setattr(row, key, value)
            row.status = status or ("completed" if not row.error_count else "partial_failed")
            row.completed_at = datetime.utcnow()
            db.commit()
    except Exception as e:
        logger.debug(f"[pipeline_batch] complete_batch skipped: {e}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pipeline_batch_helpers.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/platform/pipeline_batch.py tests/test_pipeline_batch_helpers.py
git commit -m "feat(pipeline): add never-raise batch/stage/issue tracking helpers"
```

---

### Task 3: Wire `prospector.py` ingestion with batch tracking, email-fallback dedup, and quarantine

**Files:**
- Modify: `app/platform/prospector.py` (the ingestion loop that calls `_append()`, and `run_prospecting()`/`run_daily`'s entry point — read the file's current `run_prospecting()` and `_append()`/dedup logic in full first, this task's exact line numbers depend on it)
- Test: `tests/test_prospector_pipeline_batch_wiring.py`

**Interfaces:**
- Consumes: `pipeline_batch.start_batch/start_stage/complete_stage/log_issue/complete_batch` (Task 2), existing `phone_format_variants()`/`lead_exists_for_phone()` (`app/models/lead.py`).
- Produces: every `run_prospecting()` call now creates one `LeadPipelineBatch` row with accurate raw/duplicate/invalid/valid counts.

- [ ] **Step 1: Read `app/platform/prospector.py` in full** to find (a) `run_prospecting()`'s entry point and how it loops over niches/cities, (b) where `_append()` is called per-lead, (c) the existing `seen` set / dedup check, (d) where phone/email validation happens and what "invalid" currently means (`phone_verified` flag).

- [ ] **Step 2: Write the failing integration test**

```python
# tests/test_prospector_pipeline_batch_wiring.py
"""prospector.run_prospecting() creates a LeadPipelineBatch with accurate
counts, and duplicate/invalid leads are visible instead of silently
dropped (2026-07-08)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models.base import get_db_session
from app.models.lead_pipeline import LeadPipelineBatch, LeadPipelineQualityIssue


@pytest.mark.asyncio
async def test_run_prospecting_creates_batch_with_counts():
    from app.platform import prospector

    fake_raw = [
        {"business_name": "A Co", "phone": "9198765400 01".replace(" ", ""), "niche": "dentist", "city": "pune"},
        {"business_name": "A Co Dup", "phone": "9198765400 01".replace(" ", ""), "niche": "dentist", "city": "pune"},  # dup
        {"business_name": "B Co", "phone": "12345", "niche": "dentist", "city": "pune"},  # invalid (too short)
    ]
    with patch.object(prospector, "_scrape_targets", return_value=fake_raw):
        result = await prospector.run_prospecting(niche="dentist", city="pune")

    assert "batch_id" in result
    with get_db_session() as db:
        batch = db.get(LeadPipelineBatch, result["batch_id"])
        assert batch is not None
        assert batch.total_raw == 3
        assert batch.total_duplicate == 1
        assert batch.total_invalid == 1
        assert batch.total_valid == 1
        assert batch.status == "completed"


@pytest.mark.asyncio
async def test_zero_raw_output_logs_warning_issue():
    from app.platform import prospector

    with patch.object(prospector, "_scrape_targets", return_value=[]):
        result = await prospector.run_prospecting(niche="dentist", city="pune")

    with get_db_session() as db:
        issues = db.query(LeadPipelineQualityIssue).filter_by(batch_id=result["batch_id"]).all()
        assert any(i.issue_type == "zero_output" for i in issues)


@pytest.mark.asyncio
async def test_invalid_lead_logs_quality_issue_not_silent_drop():
    from app.platform import prospector

    fake_raw = [{"business_name": "Bad Co", "phone": "123", "niche": "dentist", "city": "pune"}]
    with patch.object(prospector, "_scrape_targets", return_value=fake_raw):
        result = await prospector.run_prospecting(niche="dentist", city="pune")

    with get_db_session() as db:
        issues = db.query(LeadPipelineQualityIssue).filter_by(
            batch_id=result["batch_id"], issue_type="invalid_lead"
        ).all()
        assert len(issues) == 1
```

**Note for implementer:** `_scrape_targets` is a placeholder name for whatever internal function `run_prospecting()` actually calls to get raw scrape results — replace with the real function name found in Step 1. If `run_prospecting()` doesn't take `niche`/`city` kwargs directly (it may loop over `_targets()` internally instead), adjust the test to patch at the correct seam — the assertions on `LeadPipelineBatch` counts are the part that must hold regardless of the exact call shape.

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_prospector_pipeline_batch_wiring.py -v`
Expected: FAIL (batch_id missing from result, or `run_prospecting` doesn't accept these kwargs yet).

- [ ] **Step 4: Wire `pipeline_batch` calls into `run_prospecting()`**

At the top of `run_prospecting()` (or wherever the per-niche/city ingestion loop begins), add:

```python
from app.platform import pipeline_batch as _pb

batch_id = _pb.start_batch("prospector", niche=niche, city=city)
stage_id = _pb.start_stage(batch_id, "ingestion")
```

Around the existing raw-scrape call, count `total_raw = len(raw_results)`; if `total_raw == 0`:

```python
_pb.log_issue(batch_id, "ingestion", "zero_output", severity="warning",
              message=f"prospector found 0 raw leads for niche={niche} city={city}")
```

Inside the existing per-lead loop, where the current dedup check (`seen` set / `lead_exists_for_phone`) already runs: on a duplicate, increment a local `total_duplicate` counter (don't change the existing skip behavior). On the existing phone/email validation step, where a lead currently gets `phone_verified=False` and is flagged-and-kept: **additionally** call

```python
_pb.log_issue(batch_id, "validation", "invalid_lead", severity="info",
              message=f"phone failed validation: {phone!r}")
```

and increment a local `total_invalid` counter — but do NOT change whether the lead is written to `prospects.jsonl`/mirrored to the DB (that stays exactly as today; this task only adds visibility, not new rejection behavior, since changing what "invalid" excludes downstream is a bigger, riskier change than this vertical slice's scope).

Add the email-fallback dedup: where the existing dedup check only tests `lead_exists_for_phone`, add — only when the raw record has no phone or an unparseable one — an email-based check:

```python
if not phone_format_variants(candidate_phone) and email:
    from app.models.lead import Lead
    with get_db_session() as db:
        if db.query(Lead.id).filter(Lead.email == email).first() is not None:
            total_duplicate += 1
            continue
```

At the end of the loop, complete the stage and batch:

```python
_pb.complete_stage(stage_id, "passed" if total_raw else "warning",
                    output_count=total_valid, rejected_count=total_duplicate + total_invalid)
_pb.complete_batch(batch_id, {
    "total_raw": total_raw, "total_duplicate": total_duplicate,
    "total_invalid": total_invalid, "total_valid": total_valid,
})
result["batch_id"] = batch_id
```

(Exact variable names/insertion points depend on Step 1's read — the counters and the never-block invariant are what must hold.)

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_prospector_pipeline_batch_wiring.py -v`
Expected: 3 passed.

- [ ] **Step 6: Run the existing prospector regression suite to confirm no behavior change**

Run: `.venv\Scripts\python.exe -m pytest tests/test_lead_scoring_dedupe.py tests/test_pipeline_automation.py -q` (and any other `test_prospect*`/`test_pipeline_ops*` files found in Step 1)
Expected: all still green — this task is additive-only.

- [ ] **Step 7: Commit**

```bash
git add app/platform/prospector.py tests/test_prospector_pipeline_batch_wiring.py
git commit -m "feat(pipeline): wire prospector.py ingestion with batch tracking + email-fallback dedup"
```

---

### Task 4: Centralize scoring in `lead_scoring.py` and remaining hardcoded thresholds

**Files:**
- Modify: `app/platform/lead_scoring.py` (read `HOT_THRESHOLD` and `rescore_db()` in full first — around lines 30, 102, 151, 217 per prior audit)
- Modify: `app/telephony/call_manager.py:796` (`get_hot_leads(min_score=70)` → read `settings.lead_hot_threshold`)
- Modify: `app/models/campaign.py:91` (`Campaign.hot_lead_threshold` column default → reference the centralized setting instead of a bare `70`)
- Test: `tests/test_centralized_scoring_threshold.py`

**Interfaces:**
- Consumes: `settings.lead_hot_threshold` (Task 1), `Lead.update_score(new_score, reason=...)` (Task 1).
- Produces: one source of truth for the hot-lead threshold; `rescore_db()` now persists a reason via `score_components()`'s existing (currently-discarded) breakdown.

- [ ] **Step 1: Read `app/platform/lead_scoring.py` in full** (confirm `HOT_THRESHOLD`'s exact definition, `score_components()`'s return shape, and `rescore_db()`'s exact write path — the earlier audit found it "writes `lead.lead_score`/`is_hot_lead` directly, bypassing `update_score()`").

- [ ] **Step 2: Write the failing test**

```python
# tests/test_centralized_scoring_threshold.py
"""All hot-lead threshold call sites read the same settings.lead_hot_threshold
(2026-07-08 — previously hardcoded inconsistently as 60 vs 70 across 4 files)."""
from __future__ import annotations


def test_lead_scoring_hot_threshold_matches_settings(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "lead_hot_threshold", 55)

    from app.platform import lead_scoring
    assert lead_scoring.HOT_THRESHOLD == settings.lead_hot_threshold


def test_rescore_db_persists_score_reason(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.config import settings
    from app.models.base import Base
    from app.models.lead import Lead, LeadSource, LeadStatus
    from app.platform import lead_scoring

    monkeypatch.setattr(settings, "lead_hot_threshold", 50)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(Lead(id="l1", company_name="X", phone="9198765400 05".replace(" ", ""),
                status=LeadStatus.NEW, source=LeadSource.MANUAL, verified=True, phone_verified=True))
    db.commit()

    lead_scoring.rescore_db(db, lead_ids=["l1"])

    row = db.get(Lead, "l1")
    assert row.score_reason is not None and len(row.score_reason) > 0


def test_call_manager_get_hot_leads_uses_settings_threshold(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "lead_hot_threshold", 55)

    import inspect

    from app.telephony import call_manager
    src = inspect.getsource(call_manager.get_hot_leads)
    assert "70" not in src, "get_hot_leads must not hardcode 70 — read settings.lead_hot_threshold"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_centralized_scoring_threshold.py -v`
Expected: FAIL — `lead_scoring.HOT_THRESHOLD` is its own env-read constant (likely 60), and `get_hot_leads` source still contains `70`.

- [ ] **Step 4: Update `lead_scoring.py`**

Replace the module-level `HOT_THRESHOLD = ...` line with:

```python
from app.config import settings

HOT_THRESHOLD = settings.lead_hot_threshold  # centralized (2026-07-08) — was its own env default (60), now matches models/lead.py
```

In `rescore_db()`, wherever it currently sets `lead.lead_score`/`lead.is_hot_lead` directly, change it to call the model's own method so the reason gets persisted and both stay in sync:

```python
components = score_components(lead)  # however this is currently invoked per-lead
reason = ", ".join(f"{k}:{v}" for k, v in components.items() if v)
lead.update_score(computed_score, reason=reason)
```

(`computed_score` = whatever the existing code already computes from `components` — do not change the scoring MATH, only route the write through `update_score()` instead of setting the two columns directly.)

- [ ] **Step 5: Update `call_manager.py::get_hot_leads()`**

Read the function first, then replace its hardcoded `min_score: int = 70` default with:

```python
def get_hot_leads(self, min_score: int | None = None) -> list[Lead]:
    from app.config import settings
    min_score = settings.lead_hot_threshold if min_score is None else min_score
    ...
```

(keep the rest of the function body unchanged — only the default-value source changes, existing explicit callers passing their own `min_score` are unaffected).

- [ ] **Step 6: Update `Campaign.hot_lead_threshold`'s column default**

Read `app/models/campaign.py` around line 91 first. A SQLAlchemy `Column(Integer, default=70)` can't reference `settings` directly at import time cleanly — instead use a callable default:

```python
def _default_hot_threshold() -> int:
    from app.config import settings
    return settings.lead_hot_threshold

hot_lead_threshold = Column(Integer, default=_default_hot_threshold)
```

- [ ] **Step 7: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_centralized_scoring_threshold.py -v`
Expected: 3 passed.

- [ ] **Step 8: Run the broader scoring/campaign regression suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_lead_scoring_dedupe.py tests/test_pipeline_automation.py -k "campaign or scor" -q`
Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add app/platform/lead_scoring.py app/telephony/call_manager.py app/models/campaign.py tests/test_centralized_scoring_threshold.py
git commit -m "fix(pipeline): centralize hot-lead threshold across 4 call sites, persist score reason"
```

---

### Task 5: Unified outreach-eligibility wrapper

**Files:**
- Create: `app/platform/outreach_eligibility.py`
- Test: `tests/test_outreach_eligibility.py`

**Interfaces:**
- Consumes: `app.telephony.compliance.ComplianceGate.check` (calls), the existing email-eligibility check inside `app/platform/auto_outreach.py` (read its exact function name — Agent 2 found it inline in `run_email_outreach()` around lines 552-648, may need extracting into its own callable first), the existing WhatsApp gate in `app/marketing/whatsapp_campaign.py` (lines 33-111), `Lead.can_be_called()` (`app/models/lead.py:399`), `Lead.phone_verified`/`email_verified`.
- Produces: `is_outreach_eligible(lead, channel: str) -> tuple[bool, str]` — `channel` is `"call"|"email"|"whatsapp"`; returns `(True, "")` or `(False, reason)`.

- [ ] **Step 1: Read the 3 existing gate implementations** — `app/telephony/compliance.py::ComplianceGate.check()`, the email eligibility logic in `app/platform/auto_outreach.py` (~lines 552-648), and `app/marketing/whatsapp_campaign.py`'s gate (~lines 33-111) — to get their exact current signatures. If the email/WhatsApp checks are inline in a larger function rather than a separately-callable one, extract the minimal condition (flag on, cap not exceeded, MX/suppression pass) into a small local helper in each file first, so `outreach_eligibility.py` has something concrete to call without duplicating their logic.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_outreach_eligibility.py
"""Unified is_outreach_eligible() wraps the 3 existing per-channel gates
without changing their individual behavior (2026-07-08)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models.lead import Lead, LeadSource, LeadStatus
from app.platform.outreach_eligibility import is_outreach_eligible


def _lead(**overrides):
    defaults = dict(
        id="l1", company_name="X", phone="9198765400 09".replace(" ", ""),
        status=LeadStatus.NEW, source=LeadSource.MANUAL,
        phone_verified=True, email_verified=True, email="x@example.com",
    )
    defaults.update(overrides)
    return Lead(**defaults)


def test_dnd_status_blocks_call_channel():
    lead = _lead(status=LeadStatus.DND)
    ok, reason = is_outreach_eligible(lead, "call")
    assert ok is False
    assert "dnd" in reason.lower() or "cannot" in reason.lower() or "not eligible" in reason.lower()


def test_unverified_phone_blocks_call_channel():
    lead = _lead(phone_verified=False)
    with patch("app.telephony.compliance.ComplianceGate.check", return_value=(True, "")):
        ok, reason = is_outreach_eligible(lead, "call")
    assert ok is False
    assert "phone" in reason.lower() or "verif" in reason.lower()


def test_unverified_email_blocks_email_channel():
    lead = _lead(email_verified=False)
    ok, reason = is_outreach_eligible(lead, "email")
    assert ok is False


def test_healthy_verified_lead_eligible_for_call_when_compliance_passes():
    lead = _lead()
    with patch("app.telephony.compliance.ComplianceGate.check", return_value=(True, "")):
        ok, reason = is_outreach_eligible(lead, "call")
    assert ok is True


def test_unknown_channel_is_rejected_not_silently_allowed():
    lead = _lead()
    ok, reason = is_outreach_eligible(lead, "carrier_pigeon")
    assert ok is False
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_outreach_eligibility.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.platform.outreach_eligibility'`.

- [ ] **Step 4: Create `app/platform/outreach_eligibility.py`**

```python
"""Unified outreach-eligibility check across all 3 channels (2026-07-08).

Wraps the 3 existing, individually-tested per-channel gates —
app.telephony.compliance.ComplianceGate (calls), the email eligibility
check in app.platform.auto_outreach, and the WhatsApp gate in
app.marketing.whatsapp_campaign — behind one function, instead of each
caller re-implementing "is this lead OK to contact right now" separately.
Deliberately does NOT rewrite any of the 3 gates; this is a consolidation
layer only (2026-07-08 pipeline-automation audit found no such unified
function existed, gaps documented in
docs/superpowers/specs/2026-07-08-lead-gen-pipeline-automation-design.md §4).
"""

from __future__ import annotations

from typing import Literal

Channel = Literal["call", "email", "whatsapp"]


def is_outreach_eligible(lead, channel: str) -> tuple[bool, str]:
    """Returns (eligible, reason). `reason` is empty when eligible=True.
    Never raises — an internal error in one channel's gate is treated as
    NOT eligible (fail-closed for outreach decisions, matching this
    project's DND-lookup-fail-closed convention), with the exception noted
    in the compliance call below."""
    if not lead.can_be_called() and channel == "call":
        return False, f"lead status {getattr(lead.status, 'value', lead.status)} cannot be called"

    if channel == "call":
        if not lead.phone_verified:
            return False, "phone not verified"
        try:
            from app.telephony.compliance import ComplianceGate

            ok, reason = ComplianceGate.check(lead)
            return bool(ok), (reason or "")
        except Exception as e:
            return False, f"compliance check error: {e}"

    if channel == "email":
        if not lead.email_verified or not lead.email:
            return False, "email not verified"
        try:
            from app.platform.auto_outreach import is_email_outreach_eligible

            ok, reason = is_email_outreach_eligible(lead)
            return bool(ok), (reason or "")
        except Exception as e:
            return False, f"email eligibility check error: {e}"

    if channel == "whatsapp":
        try:
            from app.marketing.whatsapp_campaign import is_whatsapp_outreach_eligible

            ok, reason = is_whatsapp_outreach_eligible(lead)
            return bool(ok), (reason or "")
        except Exception as e:
            return False, f"whatsapp eligibility check error: {e}"

    return False, f"unknown channel: {channel!r}"
```

**Note for implementer:** `is_email_outreach_eligible`/`is_whatsapp_outreach_eligible` are the extracted-helper names from Step 1 — if Step 1's extraction used different names, update these two imports/calls to match exactly (this is the one place in the plan where the exact name depends on a refactor you do in Step 1, not on pre-existing code).

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_outreach_eligibility.py -v`
Expected: 5 passed.

- [ ] **Step 6: Run the existing compliance/auto_outreach/whatsapp regression suites**

Run: `.venv\Scripts\python.exe -m pytest tests/test_compliance.py tests/test_auto_outreach.py tests/test_whatsapp_campaign.py -q`
Expected: all still green — Step 1's extraction must not change any existing gate's behavior, only make it separately callable.

- [ ] **Step 7: Commit**

```bash
git add app/platform/outreach_eligibility.py app/platform/auto_outreach.py app/marketing/whatsapp_campaign.py tests/test_outreach_eligibility.py
git commit -m "feat(pipeline): unified is_outreach_eligible() wrapping the 3 existing per-channel gates"
```

---

### Task 6: Pre-send provider-health gate (fail-open)

**Files:**
- Modify: `app/platform/integration_health.py` (add `is_healthy()`)
- Modify: `app/telephony/call_manager.py` (call it in `queue_call()`/`_process_call()` before dialing — read the exact function first)
- Test: `tests/test_integration_health_presend_gate.py`

**Interfaces:**
- Produces: `integration_health.is_healthy(integration: str, min_attempts: int = 3, max_fail_rate: float = 0.8) -> bool` — reads the last hour's fail/ok counts via the existing `snapshot()`; **fails open** (returns `True`) on any error, on Redis being down, or when there's too little data to judge (fewer than `min_attempts` total attempts this hour).

- [ ] **Step 1: Read `app/platform/integration_health.py`'s `snapshot()`** (lines ~97-140) to confirm its exact return shape (`{"integrations": {name: {"fail": n, "ok": n, ...}}}` per Agent 2's description — confirm exact key names before writing `is_healthy()` against it).

- [ ] **Step 2: Write the failing test**

```python
# tests/test_integration_health_presend_gate.py
"""integration_health.is_healthy() — fail-open pre-send gate (2026-07-08)."""
from __future__ import annotations

from app.platform import integration_health as ih


def test_is_healthy_true_when_no_data(monkeypatch):
    monkeypatch.setattr(ih, "snapshot", lambda hours=1: {"integrations": {}})
    assert ih.is_healthy("vobiz") is True


def test_is_healthy_false_when_high_fail_rate(monkeypatch):
    monkeypatch.setattr(ih, "snapshot", lambda hours=1: {"integrations": {"vobiz": {"fail": 9, "ok": 1}}})
    assert ih.is_healthy("vobiz") is False


def test_is_healthy_true_when_healthy(monkeypatch):
    monkeypatch.setattr(ih, "snapshot", lambda hours=1: {"integrations": {"vobiz": {"fail": 1, "ok": 9}}})
    assert ih.is_healthy("vobiz") is True


def test_is_healthy_fails_open_on_exception(monkeypatch):
    def _boom(hours=1):
        raise RuntimeError("redis down")

    monkeypatch.setattr(ih, "snapshot", _boom)
    assert ih.is_healthy("vobiz") is True  # never blocks a real call due to a health-check glitch
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_integration_health_presend_gate.py -v`
Expected: FAIL — `AttributeError: module 'app.platform.integration_health' has no attribute 'is_healthy'`.

- [ ] **Step 4: Add `is_healthy()` to `integration_health.py`**

```python
def is_healthy(integration: str, min_attempts: int = 3, max_fail_rate: float = 0.8) -> bool:
    """Pre-send gate: False only when there's clear recent evidence this
    integration is failing (>= min_attempts total this hour AND fail-rate
    above max_fail_rate). FAIL-OPEN on any error, missing data, or too few
    attempts to judge — a flaky/unavailable health-check must never block a
    real send (2026-07-08 — integration_health was previously post-hoc only,
    never consulted before a send attempt)."""
    try:
        data = snapshot(hours=1).get("integrations", {}).get(integration, {})
        fail = int(data.get("fail", 0))
        ok = int(data.get("ok", 0))
        total = fail + ok
        if total < min_attempts:
            return True
        return (fail / total) < max_fail_rate
    except Exception:
        return True
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_integration_health_presend_gate.py -v`
Expected: 4 passed.

- [ ] **Step 6: Wire into `call_manager.py`**

Read `queue_call()`/`_process_call()` first. Immediately before the existing `VobizClient.place_call()` call, add:

```python
from app.platform.integration_health import is_healthy

if not is_healthy("vobiz"):
    from app.platform import pipeline_batch as _pb
    _pb.log_issue(getattr(lead, "source_batch_id", None), "outreach_execution",
                  "provider_disabled", severity="critical",
                  message="vobiz marked unhealthy by integration_health — call skipped, will retry via DLQ")
    # existing failure-handling path (whatever _handle_call_failure or the
    # equivalent already does for a dial failure) — reuse it, don't invent
    # a new one, so this looks exactly like any other transient failure to
    # the existing retry logic.
    return await self._handle_call_failure(lead, reason="provider_unhealthy")
```

(Exact function/parameter names depend on Step 1's read of `call_manager.py` — the important invariant is: unhealthy → route through the EXISTING failure/retry path, don't add a second one.)

- [ ] **Step 7: Run the call_manager regression suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_vobiz.py tests/test_call_log_persist.py -q`
Expected: all green — confirm the new gate doesn't fire for the existing tests' mocked-healthy scenarios (since `snapshot()` with no real Redis data returns `is_healthy() == True` by the fail-open/too-little-data rule).

- [ ] **Step 8: Commit**

```bash
git add app/platform/integration_health.py app/telephony/call_manager.py tests/test_integration_health_presend_gate.py
git commit -m "feat(pipeline): fail-open pre-send provider-health gate before dialing"
```

---

### Task 7: Wire WhatsApp reply + call-completion into `interaction_log`

**Files:**
- Modify: `app/platform/reply_agent.py:815` (`whatsapp_reply()`)
- Modify: `app/telephony/call_manager.py` (`handle_call_completed()` — the earlier research found this path does NOT call `interaction_log.record()`, unlike the WS-stream path in `post_call_hooks.py:639` which does)
- Test: `tests/test_interaction_log_channel_coverage.py`

**Interfaces:**
- Consumes: `app.platform.interaction_log.record()` (existing — read its exact signature first).

- [ ] **Step 1: Read `app/platform/interaction_log.py::record()`'s exact signature**, and read `app/telephony/post_call_hooks.py:639`'s existing call to it as the reference pattern to copy for `call_manager.py`.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_interaction_log_channel_coverage.py
"""WhatsApp replies and legacy call-completion now feed interaction_log,
closing the gap where only email/voice-stream paths did (2026-07-08)."""
from __future__ import annotations

from unittest.mock import patch


def test_whatsapp_reply_calls_interaction_log():
    from app.platform import reply_agent

    with patch("app.platform.interaction_log.record") as mock_record:
        with patch.object(reply_agent, "_process_incoming_whatsapp", return_value=None):
            reply_agent.whatsapp_reply({"from": "+919876543210", "body": "interested"})
        assert mock_record.called


def test_call_completed_calls_interaction_log():
    from app.telephony import call_manager

    with patch("app.platform.interaction_log.record") as mock_record:
        call_manager.handle_call_completed({"call_id": "c1", "status": "completed", "duration": 42})
        assert mock_record.called
```

**Note for implementer:** these two tests' exact mocking seams depend on Step 1's read of the real function signatures/bodies — adjust the `patch()` targets to whatever internal helper each function actually calls, while keeping the core assertion (`interaction_log.record` gets called) intact.

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_interaction_log_channel_coverage.py -v`
Expected: FAIL on both — neither path calls `interaction_log.record()` today.

- [ ] **Step 4: Add the `interaction_log.record()` call to `whatsapp_reply()`**

Following the exact call shape already used in `reply_agent.py`'s own email path (or `post_call_hooks.py:639`'s pattern) — same `channel="whatsapp"`, `direction="in"`, populate `lead_id`/`contact_id` however the function already resolves them, `outcome` reflecting whatever the WhatsApp reply's intent classification already produces.

- [ ] **Step 5: Add the `interaction_log.record()` call to `handle_call_completed()`**

Same pattern, `channel="voice"`, `direction` based on the call's inbound/outbound flag already available in the function, `outcome` from the call's disposition/status.

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_interaction_log_channel_coverage.py -v`
Expected: 2 passed.

- [ ] **Step 7: Run the reply_agent/call_manager regression suites**

Run: `.venv\Scripts\python.exe -m pytest tests/test_vobiz.py tests/test_call_log_persist.py -k "reply or complet" -q`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add app/platform/reply_agent.py app/telephony/call_manager.py tests/test_interaction_log_channel_coverage.py
git commit -m "fix(pipeline): wire WhatsApp reply + call-completion into interaction_log (closes Stage-10 gap)"
```

---

### Task 8: Admin pipeline API

**Files:**
- Create: `app/api/admin_pipeline.py`
- Modify: `app/main.py` (mount the router — follow the exact pattern at line ~840 for `admin_dashboard_router`)
- Test: `tests/test_admin_pipeline_api.py`

**Interfaces:**
- Produces: `GET /api/admin/pipeline/batches`, `GET /api/admin/pipeline/batches/{id}`, `GET /api/admin/pipeline/health`, `GET /api/admin/pipeline/issues`, `POST /api/admin/pipeline/issues/{id}/resolve` — all `Depends(require_admin)`.

- [ ] **Step 1: Read `app/api/admin_dashboard.py`'s top ~40 lines** to copy its exact router-declaration/auth-dependency-import pattern (e.g. `from app.api.auth_deps import require_admin`).

- [ ] **Step 2: Write the failing route tests**

**Important — read `tests/conftest.py` lines 189-196 first.** The top-level suite globally overrides `app.dependency_overrides[require_admin] = get_mock_user` at import time, so every test in `tests/` (not `tests/security/`) runs AS an authenticated admin already. This file therefore tests *behavior* (assuming the mocked admin), not auth-rejection — auth-rejection coverage is added separately in Step 5a, following `tests/security/test_rbac.py`'s own established convention (which has a dedicated `tests/security/conftest.py` that strips the mock, and asserts `status_code not in _SUCCESS` rather than an exact 401/403 — do not re-invent that pattern here).

```python
# tests/test_admin_pipeline_api.py
"""Admin pipeline API — behavior/shape, under the suite's mocked-admin
session (2026-07-08). Auth-rejection coverage lives in
tests/security/test_rbac.py (Step 5a) — this file assumes admin auth
already passed, matching this repo's existing split between behavior
tests and the dedicated security-test file."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_batches_returns_empty_list_shape_with_no_data():
    r = client.get("/api/admin/pipeline/batches")
    assert r.status_code == 200
    assert r.json() == {"batches": []}


def test_health_returns_zero_counts_with_no_data():
    r = client.get("/api/admin/pipeline/health")
    assert r.status_code == 200
    body = r.json()
    assert body["open_issues"] == 0
    assert body["critical_issues"] == 0


def test_issues_returns_empty_list_shape_with_no_data():
    r = client.get("/api/admin/pipeline/issues")
    assert r.status_code == 200
    assert r.json() == {"issues": []}


def test_resolve_issue_404_when_not_found():
    r = client.post("/api/admin/pipeline/issues/fake-id/resolve")
    assert r.status_code == 404


def test_batch_detail_404_when_not_found():
    r = client.get("/api/admin/pipeline/batches/fake-id")
    assert r.status_code == 404


def test_batch_detail_returns_stages_and_issues_for_real_batch():
    from app.platform import pipeline_batch as pb

    batch_id = pb.start_batch("prospector", niche="dentist", city="pune")
    stage_id = pb.start_stage(batch_id, "ingestion", input_count=5)
    pb.complete_stage(stage_id, "passed", output_count=5)
    pb.log_issue(batch_id, "ingestion", "zero_output", severity="warning", message="test")

    r = client.get(f"/api/admin/pipeline/batches/{batch_id}")
    assert r.status_code == 200
    body = r.json()
    assert len(body["stages"]) == 1
    assert len(body["issues"]) == 1
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_admin_pipeline_api.py -v`
Expected: FAIL — `404` on every route (router doesn't exist yet).

- [ ] **Step 4: Create `app/api/admin_pipeline.py`**

```python
"""Admin-facing Lead-Gen Pipeline Health API (2026-07-08).

Read-only visibility + a resolve action over the new
LeadPipelineBatch/StageRun/QualityIssue tables. See
docs/superpowers/specs/2026-07-08-lead-gen-pipeline-automation-design.md §6.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth_deps import require_admin
from app.models.base import get_db_session
from app.models.lead_pipeline import LeadPipelineBatch, LeadPipelineQualityIssue, LeadPipelineStageRun

router = APIRouter(prefix="/api/admin/pipeline", dependencies=[Depends(require_admin)])


@router.get("/batches")
def list_batches(limit: int = 50):
    with get_db_session() as db:
        rows = (
            db.query(LeadPipelineBatch)
            .order_by(LeadPipelineBatch.created_at.desc())
            .limit(min(limit, 200))
            .all()
        )
        return {
            "batches": [
                {
                    "id": b.id, "source": b.source, "niche": b.niche, "city": b.city,
                    "status": b.status, "total_raw": b.total_raw, "total_valid": b.total_valid,
                    "total_duplicate": b.total_duplicate, "total_invalid": b.total_invalid,
                    "total_scored": b.total_scored, "total_eligible": b.total_eligible,
                    "total_outreach_created": b.total_outreach_created, "error_count": b.error_count,
                    "created_at": b.created_at.isoformat() if b.created_at else None,
                    "completed_at": b.completed_at.isoformat() if b.completed_at else None,
                }
                for b in rows
            ]
        }


@router.get("/batches/{batch_id}")
def batch_detail(batch_id: str):
    with get_db_session() as db:
        batch = db.get(LeadPipelineBatch, batch_id)
        if batch is None:
            raise HTTPException(404, "batch not found")
        stages = db.query(LeadPipelineStageRun).filter_by(batch_id=batch_id).all()
        issues = db.query(LeadPipelineQualityIssue).filter_by(batch_id=batch_id).all()
        return {
            "id": batch.id, "source": batch.source, "niche": batch.niche, "city": batch.city,
            "status": batch.status,
            "stages": [
                {"stage_name": s.stage_name, "status": s.status, "input_count": s.input_count,
                 "output_count": s.output_count, "rejected_count": s.rejected_count,
                 "error_message": s.error_message}
                for s in stages
            ],
            "issues": [
                {"id": i.id, "stage_name": i.stage_name, "issue_type": i.issue_type,
                 "severity": i.severity, "message": i.message, "resolved": i.resolved}
                for i in issues
            ],
        }


@router.get("/health")
def pipeline_health():
    with get_db_session() as db:
        today_batches = (
            db.query(LeadPipelineBatch)
            .order_by(LeadPipelineBatch.created_at.desc())
            .limit(10)
            .all()
        )
        open_issues = db.query(LeadPipelineQualityIssue).filter_by(resolved=False).count()
        critical_issues = (
            db.query(LeadPipelineQualityIssue)
            .filter_by(resolved=False, severity="critical")
            .count()
        )
        return {
            "recent_batches": len(today_batches),
            "latest_status": today_batches[0].status if today_batches else None,
            "open_issues": open_issues,
            "critical_issues": critical_issues,
        }


@router.get("/issues")
def list_issues(resolved: bool = False, limit: int = 50):
    with get_db_session() as db:
        rows = (
            db.query(LeadPipelineQualityIssue)
            .filter_by(resolved=resolved)
            .order_by(LeadPipelineQualityIssue.created_at.desc())
            .limit(min(limit, 200))
            .all()
        )
        return {
            "issues": [
                {"id": i.id, "batch_id": i.batch_id, "stage_name": i.stage_name,
                 "issue_type": i.issue_type, "severity": i.severity, "message": i.message,
                 "created_at": i.created_at.isoformat() if i.created_at else None}
                for i in rows
            ]
        }


@router.post("/issues/{issue_id}/resolve")
def resolve_issue(issue_id: str):
    with get_db_session() as db:
        row = db.get(LeadPipelineQualityIssue, issue_id)
        if row is None:
            raise HTTPException(404, "issue not found")
        row.resolved = True
        db.commit()
        return {"ok": True, "id": issue_id}
```

- [ ] **Step 5: Mount the router in `app/main.py`**

Read lines 835-845 first to confirm the exact surrounding pattern, then add near `admin_dashboard_router`:

```python
from app.api.admin_pipeline import router as admin_pipeline_router
...
app.include_router(admin_pipeline_router, tags=["Admin Pipeline"])  # /api/admin/pipeline/*
```

- [ ] **Step 5a: Extend `tests/security/test_rbac.py`'s `ADMIN_API_PATHS` list**

Read the file's `ADMIN_API_PATHS` list (line ~32) and its `_seed_fake_tenant`-style pattern for routes needing seeded state to avoid a false-pass on an incidental 404. Add the 4 GET pipeline paths to `ADMIN_API_PATHS` (the parametrized `test_admin_api_rejects_no_auth` already covers them once added — no new test function needed):

```python
ADMIN_API_PATHS = [
    "/api/admin/stats",
    "/api/admin/users",
    "/api/admin/billing",
    "/api/admin/agents",
    "/api/admin/workflows",
    "/api/platform/health",
    "/api/v1/status",
    "/api/admin/pipeline/batches",   # 2026-07-08 pipeline automation
    "/api/admin/pipeline/health",
    "/api/admin/pipeline/issues",
]
```

The `POST /issues/{id}/resolve` needs its own parametrized-POST test — follow the exact pattern of the existing `test_platform_tenant_post_rejects_no_auth`/`test_ml_training_post_rejects_no_auth` functions in the same file (read one of them first) to add an equivalent for `/api/admin/pipeline/issues/fake-id/resolve`.

- [ ] **Step 6: Run both test files to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_admin_pipeline_api.py tests/security/test_rbac.py -v`
Expected: 6 passed in the behavior file; all `test_rbac.py` tests (including the new parametrized cases) still passing.

- [ ] **Step 7: Run the duplicate-route guard**

Run: `.venv\Scripts\python.exe -c "import app.main"` then `.venv\Scripts\python.exe scripts\prod_check.py` — confirm route count increases by exactly 5 and no wiring-gap warning appears for these new routes.

- [ ] **Step 8: Commit**

```bash
git add app/api/admin_pipeline.py app/main.py tests/test_admin_pipeline_api.py
git commit -m "feat(pipeline): admin pipeline health API (batches/health/issues, admin-gated)"
```

---

### Task 9: Admin "Lead-Gen Pipeline Health" dashboard section

**Files:**
- Modify: `frontend/admin_dashboard.html` (add a new card under the "Growth & Revenue" nav group, following the exact `sec-clients`/`sec-recordings` card pattern from this same session's ADR-047 nav restore)
- Test: `tests/test_admin_pipeline_dashboard_section.py`

**Interfaces:**
- Consumes: `GET /api/admin/pipeline/health`, `GET /api/admin/pipeline/batches`, `GET /api/admin/pipeline/issues` (Task 8).

- [ ] **Step 1: Read `frontend/admin_dashboard.html`'s `sec-recordings` card** (added this session, ~line 944 before the merges) as the exact structural pattern to copy: card markup, a `load*()` JS function called from the `DOMContentLoaded` list, skeleton-loading + retry-on-error convention.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_admin_pipeline_dashboard_section.py
"""Admin dashboard has a Lead-Gen Pipeline Health card, correctly nav-linked
(2026-07-08)."""
from __future__ import annotations


def _admin_html():
    with open("frontend/admin_dashboard.html", encoding="utf-8") as f:
        return f.read()


def test_pipeline_health_card_present():
    html = _admin_html()
    assert 'id="sec-pipeline-health"' in html


def test_pipeline_health_nav_link_present_exactly_once():
    html = _admin_html()
    assert html.count('href="#sec-pipeline-health"') == 1


def test_pipeline_health_load_function_wired_on_dom_content_loaded():
    html = _admin_html()
    assert "loadPipelineHealth()" in html
    idx_fn = html.index("function loadPipelineHealth")
    idx_call = html.index("loadPipelineHealth();", html.index('addEventListener("DOMContentLoaded"'))
    assert idx_fn > 0 and idx_call > 0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_admin_pipeline_dashboard_section.py -v`
Expected: FAIL — section doesn't exist yet.

- [ ] **Step 4: Add the nav link**

In the "Growth & Revenue" nav-group (per this session's restored ADR-034 structure), after the "Niches & Pricing" link, add:

```html
<a href="#sec-pipeline-health" role="menuitem" aria-label="Lead-gen pipeline health"><span class="ic" aria-hidden="true">🔬</span> Pipeline Health</a>
```

- [ ] **Step 5: Add the card**, following the `sec-recordings` structural pattern, near the existing prospects/niches cards:

```html
<div class="card" id="sec-pipeline-health" style="scroll-margin-top:80px">
  <div class="hd">
    <h3>🔬 Lead-Gen Pipeline Health</h3>
    <span class="right" id="pipeline-health-summary" aria-live="polite">—</span>
    <button class="btn" onclick="loadPipelineHealth()" aria-label="Refresh pipeline health" style="margin-left:10px;padding:6px 12px;font-size:12px">↺ Refresh</button>
  </div>
  <div class="bd" id="pipeline-health-body">
    <div style="color:var(--muted);font-size:13px">Loading…</div>
  </div>
</div>
```

- [ ] **Step 6: Add the JS `loadPipelineHealth()` function**, near the other `load*()` functions:

```javascript
async function loadPipelineHealth(){
  const body = document.getElementById('pipeline-health-body');
  const summary = document.getElementById('pipeline-health-summary');
  try {
    const [health, batches, issues] = await Promise.all([
      fetch('/api/admin/pipeline/health').then(r => r.json()),
      fetch('/api/admin/pipeline/batches?limit=10').then(r => r.json()),
      fetch('/api/admin/pipeline/issues?resolved=false&limit=10').then(r => r.json()),
    ]);
    summary.textContent = `${health.open_issues} open issues · ${health.critical_issues} critical`;
    const batchRows = (batches.batches || []).map(b => `
      <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--line);font-size:12px">
        <span>${escH(b.niche || '-')} / ${escH(b.city || '-')} — ${escH(b.status)}</span>
        <span>${b.total_valid}/${b.total_raw} valid · ${b.total_duplicate} dup · ${b.total_invalid} invalid</span>
      </div>`).join('') || '<div style="color:var(--muted);font-size:12px">Koi batch abhi tak nahi chala.</div>';
    const issueRows = (issues.issues || []).map(i => `
      <div style="padding:6px 0;border-bottom:1px solid var(--line);font-size:12px">
        <b style="color:${i.severity === 'critical' ? '#dc2626' : '#d97706'}">${escH(i.severity)}</b>
        — ${escH(i.issue_type)}: ${escH(i.message || '')}
      </div>`).join('') || '<div style="color:var(--muted);font-size:12px">Koi open issue nahi.</div>';
    body.innerHTML = `<h4 style="font-size:13px;margin:0 0 6px">Recent batches</h4>${batchRows}<h4 style="font-size:13px;margin:12px 0 6px">Today's Pipeline Problems</h4>${issueRows}`;
  } catch (e) {
    body.innerHTML = '<div style="color:#dc2626;font-size:12px">Load failed. <a href="#" onclick="loadPipelineHealth();return false;">Retry</a></div>';
  }
}
```

- [ ] **Step 7: Wire the call into `DOMContentLoaded`**

Add `loadPipelineHealth();` alongside the other `load*()` calls in the existing `document.addEventListener("DOMContentLoaded", ...)` block.

- [ ] **Step 8: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_admin_pipeline_dashboard_section.py -v`
Expected: 3 passed.

- [ ] **Step 9: Run the full admin-nav regression suite** (this session already fixed this file's nav once — don't reintroduce a regression)

Run: `.venv\Scripts\python.exe -m pytest tests/test_admin_nav_ia_cleanup.py tests/test_admin_nav_ia_groups.py tests/test_admin_command_center.py -q`
Expected: all still green.

- [ ] **Step 10: Live-browser verify** (per this project's UI-change convention): start the preview server, navigate to `/app/admin`, click "Pipeline Health", confirm the card renders (even with empty state) and no console errors.

- [ ] **Step 11: Commit**

```bash
git add frontend/admin_dashboard.html tests/test_admin_pipeline_dashboard_section.py
git commit -m "feat(pipeline): admin Lead-Gen Pipeline Health dashboard section"
```

---

### Task 10: Customer-facing simplified summary + read-only backfill preview

**Files:**
- Modify: `app/api/customer_dashboard.py` (add a simplified summary endpoint — read the file's existing route patterns first for the exact auth-dependency convention, e.g. `Depends(get_current_customer)` or equivalent)
- Modify: `frontend/customer_dashboard.html` (add the summary section, following its existing `data-view` pattern — **do not** copy admin's anchor-scroll pattern, this file uses a different, ADR-044-blessed SPA view engine)
- Modify: `app/api/admin_pipeline.py` (add `POST /backfill/preview`, read-only)
- Test: `tests/test_customer_pipeline_summary.py`, `tests/test_pipeline_backfill_preview.py`

**Interfaces:**
- Produces: `GET /api/customer/pipeline-summary` (tenant-isolated — leads found/verified/hot/contacted/interested/appointments for the CURRENT customer only), `POST /api/admin/pipeline/backfill/preview` (returns an estimate, mutates nothing).

- [ ] **Step 1: Read `app/api/customer_dashboard.py`'s router declaration** (confirm its `prefix`, e.g. `/api/customer`, so the new route's full path matches — every existing route in this file uses `client_id: str = Depends(require_customer)` from `app.api.customer_auth`, never a client-supplied id, per this project's IDOR-safety convention) and **read `frontend/customer_dashboard.html`'s current `data-view` structure** (confirm the view name this section should live under, likely the funnel/leads-relevant tab).

- [ ] **Step 2: Write the failing customer-summary test**

```python
# tests/test_customer_pipeline_summary.py
"""Customer pipeline summary is simplified (no DLQ/worker jargon) and
tenant-isolated (2026-07-08). require_customer is NOT globally mocked in
tests/conftest.py (unlike require_admin) — unauthenticated calls genuinely
hit real auth here."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.customer_auth import require_customer
from app.main import app

client = TestClient(app)

_SUCCESS = {200, 201, 202, 203, 204, 206}


def test_pipeline_summary_rejects_unauthenticated():
    r = client.get("/api/customer/pipeline-summary")
    assert r.status_code not in _SUCCESS, f"AUTH BYPASS: -> {r.status_code} without auth"


def test_pipeline_summary_shape_has_no_internal_jargon():
    app.dependency_overrides[require_customer] = lambda: "test-client-id"
    try:
        r = client.get("/api/customer/pipeline-summary")
        assert r.status_code == 200
        body = r.json()
        expected_keys = {
            "leads_found", "leads_verified", "hot_leads",
            "contacted", "interested_replies", "appointments",
        }
        assert expected_keys.issubset(body.keys())
        body_text = str(body).lower()
        for jargon in ("dlq", "batch_id", "stage_name", "worker", "quarantine"):
            assert jargon not in body_text
    finally:
        app.dependency_overrides.pop(require_customer, None)


def test_pipeline_summary_only_counts_own_tenants_leads():
    from app.models.base import get_db_session
    from app.models.lead import Lead, LeadSource, LeadStatus

    with get_db_session() as db:
        db.add(Lead(id="mine-1", company_name="Mine", phone="9198765400 20".replace(" ", ""),
                     status=LeadStatus.NEW, source=LeadSource.MANUAL, assigned_to="test-client-id"))
        db.add(Lead(id="theirs-1", company_name="Theirs", phone="9198765400 21".replace(" ", ""),
                     status=LeadStatus.NEW, source=LeadSource.MANUAL, assigned_to="other-client-id"))
        db.commit()

    app.dependency_overrides[require_customer] = lambda: "test-client-id"
    try:
        r = client.get("/api/customer/pipeline-summary")
        assert r.json()["leads_found"] == 1
    finally:
        app.dependency_overrides.pop(require_customer, None)
```

- [ ] **Step 3: Implement the endpoint** in `app/api/customer_dashboard.py`, following the file's existing auth/tenant-scoping pattern exactly (this router's existing routes all mount under its declared prefix — confirm the endpoint's full path resolves to `/api/customer/pipeline-summary` given that prefix):

```python
@router.get("/pipeline-summary")
def pipeline_summary(client_id: str = Depends(require_customer)):
    from app.models.base import get_db_session
    from app.models.lead import Lead

    with get_db_session() as db:
        leads = db.query(Lead).filter(Lead.assigned_to == client_id).all()
        return {
            "leads_found": len(leads),
            "leads_verified": sum(1 for l in leads if l.phone_verified),
            "hot_leads": sum(1 for l in leads if l.is_hot_lead),
            "contacted": sum(1 for l in leads if l.call_attempts > 0),
            "interested_replies": sum(1 for l in leads if l.status.value == "qualified"),
            "appointments": sum(1 for l in leads if l.status.value == "appointment"),
        }
```

- [ ] **Step 4: Add the frontend summary section** to `frontend/customer_dashboard.html`, matching its existing card/tab conventions exactly as read in Step 1 (data-fetched card, no jargon in labels — "Leads mile", "Verify hue", "Hot leads", "Contact hua", "Interested replies", "Appointments").

- [ ] **Step 5: Write and pass the backfill-preview test**

```python
# tests/test_pipeline_backfill_preview.py
"""Backfill preview is read-only — never mutates leads/batches (2026-07-08).
Runs under the suite's mocked-admin session (see Task 8's note on
tests/conftest.py); add this path to tests/security/test_rbac.py's
ADMIN_API_PATHS-equivalent POST list (Task 8 Step 5a) for auth-rejection
coverage, not here."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_backfill_preview_returns_estimate_without_mutating(monkeypatch):
    from app.models.base import get_db_session
    from app.models.lead import Lead, LeadSource, LeadStatus

    with get_db_session() as db:
        db.add(Lead(id="p1", company_name="X", phone="9198765400 30".replace(" ", ""),
                     status=LeadStatus.NEW, source=LeadSource.MANUAL, niche="dentist", city="pune"))
        db.commit()
        before_count = db.query(Lead).count()

    r = client.post("/api/admin/pipeline/backfill/preview", params={"niche": "dentist", "city": "pune"})
    assert r.status_code == 200
    body = r.json()
    assert body["mutates"] is False
    assert body["estimated_existing_leads"] == 1

    with get_db_session() as db:
        assert db.query(Lead).count() == before_count  # confirm zero mutation
```

- [ ] **Step 6: Add `POST /backfill/preview` to `app/api/admin_pipeline.py`**

```python
@router.post("/backfill/preview")
def backfill_preview(niche: str, city: str):
    """Read-only estimate of how many leads a re-run for this niche/city would
    likely touch — NO mutation. Full backfill/run deferred to P1
    (docs/superpowers/specs/2026-07-08-lead-gen-pipeline-automation-design.md §7)."""
    with get_db_session() as db:
        from app.models.lead import Lead

        count = db.query(Lead).filter(Lead.niche == niche, Lead.city == city).count()
        return {"niche": niche, "city": city, "estimated_existing_leads": count, "mutates": False}
```

- [ ] **Step 7: Extend `tests/security/test_rbac.py`'s POST-paths list with `/api/admin/pipeline/backfill/preview`**

Following the same POST-parametrized pattern used in Task 8 Step 5a (which covers the 3 GET routes + the resolve POST added in Task 8) — add this POST route too, same file, same convention. This closes the loop so every new admin-gated route this plan adds has real auth-rejection coverage in the one place this repo keeps it.

- [ ] **Step 8: Run all Task 10 tests plus the extended security file**

Run: `.venv\Scripts\python.exe -m pytest tests/test_customer_pipeline_summary.py tests/test_pipeline_backfill_preview.py tests/security/test_rbac.py -v`
Expected: all passing.

- [ ] **Step 9: Commit**

```bash
git add app/api/customer_dashboard.py frontend/customer_dashboard.html app/api/admin_pipeline.py tests/test_customer_pipeline_summary.py tests/test_pipeline_backfill_preview.py
git commit -m "feat(pipeline): customer-facing simplified summary + read-only backfill preview"
```

---

### Task 11: Full regression pass, docs, and Loop Run record

**Files:**
- Modify: `progress.md` (append `## Loop Run` block per CLAUDE.md §0)
- Modify: `memory/decisions.md` (append ADR entry — check current head ADR number first, this session's ADR-047 was the admin-nav fix; use the next free number)
- Modify: `CLAUDE.md` + `AGENTS.md` Current State (byte-copy re-sync)
- Modify: `.env.example` (document `lead_hot_threshold`/`lead_warm_threshold` are settings not env-flags — no new flags actually needed per this plan's design, confirm and note if anything changed during implementation)

- [ ] **Step 1: Run the full targeted regression sweep**

Run: `.venv\Scripts\python.exe -m pytest tests/test_lead_pipeline_models.py tests/test_pipeline_batch_helpers.py tests/test_prospector_pipeline_batch_wiring.py tests/test_centralized_scoring_threshold.py tests/test_outreach_eligibility.py tests/test_integration_health_presend_gate.py tests/test_interaction_log_channel_coverage.py tests/test_admin_pipeline_api.py tests/test_admin_pipeline_dashboard_section.py tests/test_customer_pipeline_summary.py tests/test_pipeline_backfill_preview.py tests/test_lead_scoring_dedupe.py tests/test_compliance.py tests/test_auto_outreach.py tests/test_whatsapp_campaign.py tests/test_vobiz.py tests/test_admin_nav_ia_cleanup.py tests/test_admin_nav_ia_groups.py -q`
Expected: all green, 0 failed.

- [ ] **Step 2: Run `prod_check.py`**

Run: `.venv\Scripts\python.exe scripts\prod_check.py`
Expected: `[OK] ALL CHECKS PASSED`, route count increased by 6 (5 pipeline endpoints + 1 customer summary), 0 wiring gaps.

- [ ] **Step 3: Run `check_secrets.py`**

Run: `.venv\Scripts\python.exe scripts\check_secrets.py`
Expected: `[OK] no secrets detected`.

- [ ] **Step 4: Duplicate-route grep**

Run: `grep -rn "^@router\|@app\.\(get\|post\)" app/api/admin_pipeline.py` and cross-check against `app/main.py`'s full route list for any accidental collision with existing `/api/admin/*` paths.
Expected: no collisions.

- [ ] **Step 5: Append the `## Loop Run` block to `progress.md`**

Following CLAUDE.md §0's canonical format: Date / Goal / Inspected / Problems Found / Changed / Tests Run / Verification Evidence / Risks / Remaining / Next Highest Priority — summarizing Tasks 1-10.

- [ ] **Step 6: Append an ADR entry to `memory/decisions.md`** (check the current highest ADR number first — do not reuse `ADR-047`) documenting: what shipped, what was explicitly deferred to P1 (§7 of the design spec — Stage 12 CRM handoff fix, full lineage/backfill dashboard, multi-orchestrator unification), and the centralized-threshold judgment call (70 chosen over 60).

- [ ] **Step 7: Update `CLAUDE.md` Current State**, then re-sync `AGENTS.md` via `Copy-Item`/`cp`.

- [ ] **Step 8: Commit**

```bash
git add progress.md memory/decisions.md CLAUDE.md AGENTS.md
git commit -m "docs(pipeline): record lead-gen pipeline automation vertical slice + P1 follow-ups"
```

- [ ] **Step 9: Report to the user** using this project's canonical 9-field Loop Engineer format (Goal / Inspected / Problems Found / Changed / Tests Run / Verification Evidence / Risks / Remaining / Next Highest Priority), explicitly calling out: Stage 12 (lead→customer handoff) remains broken and is the single highest-value next step, not yet fixed by this plan.
