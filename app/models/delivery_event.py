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
