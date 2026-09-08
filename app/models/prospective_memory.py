"""ProspectiveMemory — durable "baad me yeh karna hai" row for the agent memory stack (L6).

WHY A TABLE (review P0): the first cut kept these rows in JSONL. A JSONL
read-modify-write is NOT exactly-once — two workers, an overlapping scheduler
tick, or a container restart mid-write can each dispatch the same row twice.
This table is the AUTHORITY; the same optimistic-lock pattern as `AgentTask`
(`checkout_version`) is used so a claim is a single atomic UPDATE.

State machine (see app/platform/prospective_store.py):

    pending --claim--> claimed --dispatch--> dispatched
       ^                  |                      |
       |                  +--fail--> pending (retry, attempt_count+1)
       |                  |                      |
       +--lease expiry----+          fail (attempts exhausted) --> dead

`idempotency_key` is UNIQUE: the same logical intent enqueued twice collapses to
one row, so a retrying caller cannot create duplicate future work.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String, Text

from app.models.base import Base


class ProspectiveMemory(Base):
    """One scheduled future action owned by an agent, scoped to a tenant."""

    __tablename__ = "prospective_memory"

    __table_args__ = (
        # drain hot-path: due pending rows, oldest first
        Index("ix_prospective_status_due", "status", "due_at"),
        Index("ix_prospective_tenant_agent", "tenant_id", "agent_id"),
        Index("ix_prospective_lease", "status", "lease_until"),
    )

    id = Column(String(36), primary_key=True)

    # --- isolation (P0): never nullable, never defaulted to a global tenant ---
    tenant_id = Column(String(64), nullable=False)
    agent_id = Column(String(40), nullable=False)

    # --- intent ---
    action = Column(String(500), nullable=False, default="")
    note = Column(String(400), default="")
    payload_json = Column(Text, default="{}")  # redacted before write
    source = Column(String(40), default="")  # provenance: who scheduled this

    # --- scheduling / lifecycle ---
    due_at = Column(DateTime, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    # pending -> claimed -> dispatched | dead ; cancelled is terminal-by-operator

    idempotency_key = Column(String(120), nullable=False, unique=True)
    claimed_by = Column(String(64), nullable=True)  # worker identity holding the lease
    lease_until = Column(DateTime, nullable=True)  # expiry => recoverable
    attempt_count = Column(Integer, default=0, nullable=False)
    last_error = Column(String(500), default="")
    dispatched_task_id = Column(String(36), nullable=True)  # agent_tasks.id

    # optimistic lock — atomic claim (AgentTask ka same pattern)
    checkout_version = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    closed_at = Column(DateTime, nullable=True)
