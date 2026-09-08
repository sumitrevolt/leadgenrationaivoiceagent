"""AgentGoal model — Paperclip-style goal hierarchy records.

Goals answer the "why": company goals break down into team goals, which break
down into agent-level goals. Tasks (AgentTask) carry free-text goal CONTEXT;
goals are the tracked, statused, linkable records above them. Additive table —
created by Base.metadata.create_all (DB_CREATE_ALL), no migration needed.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String, Text

from app.models.base import Base

GOAL_LEVELS = ("company", "team", "agent")
GOAL_STATUSES = ("planned", "active", "achieved", "cancelled")


class AgentGoal(Base):
    """One tracked goal in the company → team → agent hierarchy."""

    __tablename__ = "agent_goals"

    __table_args__ = (
        Index("ix_agent_goals_level_status", "level", "status"),
        Index("ix_agent_goals_parent", "parent_goal_id"),
        Index("ix_agent_goals_client", "client_id"),
        Index("ix_agent_goals_created", "created_at"),
    )

    id = Column(String(36), primary_key=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, default="")
    level = Column(String(20), nullable=False, default="team")
    status = Column(String(20), nullable=False, default="planned", index=True)
    parent_goal_id = Column(String(36), nullable=True)
    owner_agent_id = Column(String(40), nullable=True)  # STAFF key for agent-level goals
    client_id = Column(String(36), nullable=True)  # customer isolation (parity with AgentTask)
    campaign_id = Column(String(36), nullable=True)
    target_metric = Column(String(200), default="")  # e.g. "12 calls/day", "5 inquiries/week"
    progress_notes = Column(Text, default="")  # append-only log, newline separated
    linked_task_ids = Column(Text, default="[]")  # JSON array — advisory task linkage

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    achieved_at = Column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        import json

        try:
            linked = json.loads(self.linked_task_ids or "[]")
        except (ValueError, TypeError):
            linked = []
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description or "",
            "level": self.level,
            "status": self.status,
            "parent_goal_id": self.parent_goal_id,
            "owner_agent_id": self.owner_agent_id,
            "client_id": self.client_id,
            "campaign_id": self.campaign_id,
            "target_metric": self.target_metric or "",
            "progress_notes": (self.progress_notes or "").rstrip("\n"),
            "linked_task_ids": linked,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "achieved_at": self.achieved_at.isoformat() if self.achieved_at else None,
        }
