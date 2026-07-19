"""
AgentTask Model — Paperclip-inspired per-agent work queue.
Har agent ka pending/active/done task yahan track hota hai.
Atomic checkout ensures no double-work. Goal chain provides context.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Index, Integer, String, Text

from app.models.base import Base


class AgentTask(Base):
    """One unit of work assigned to (or claimed by) a staff agent."""

    __tablename__ = "agent_tasks"

    __table_args__ = (
        Index("ix_agent_tasks_agent_status", "agent_id", "status"),
        Index("ix_agent_tasks_status", "status"),
        Index("ix_agent_tasks_client", "client_id"),
        Index("ix_agent_tasks_created", "created_at"),
    )

    id = Column(String(36), primary_key=True)
    agent_id = Column(String(40), nullable=False)  # STAFF key
    status = Column(String(20), nullable=False, default="pending")
    # pending -> claimed -> running -> done | failed | cancelled
    goal = Column(String(500), nullable=False, default="")  # what to do (Hinglish ok)
    result_summary = Column(Text, default="")  # what happened

    # Goal hierarchy — Paperclip-style context chain
    client_id = Column(String(36), nullable=True)  # which client (isolation)
    campaign_id = Column(String(36), nullable=True)  # which campaign
    goal_text = Column(String(500), default="")  # WHY — business goal
    parent_task_id = Column(String(36), nullable=True)  # delegation chain

    # Delegation
    delegated_by = Column(String(40), nullable=True)  # STAFF key of assigner
    delegated_to = Column(String(40), nullable=True)  # STAFF key (if re-delegated)

    # Cost tracking
    cost_tokens_in = Column(Integer, default=0)
    cost_tokens_out = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    provider = Column(String(40), default="")  # groq/mistral/gemini/...

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    claimed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Org chart — how deep in delegation hierarchy (0=Boss, 1=lead, 2+=IC)
    request_depth = Column(Integer, default=0)

    # Checkout lock — atomic claim (version field for optimistic locking)
    checkout_version = Column(Integer, default=0)
