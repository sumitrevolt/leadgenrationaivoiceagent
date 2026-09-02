"""
Data Credits Model
Credit-based billing system for B2B Intelligence Platform
"""

import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base


def _enum_values(enum_cls):
    """values_callable so the DB stores .value not .name — VARCHAR-backed
    (native_enum=False), matching app/models/payment.py (production audit
    2026-07-01, F-DB4)."""
    return [member.value for member in enum_cls]


class CreditTransactionType(enum.Enum):
    """Credit transaction types"""

    PURCHASE = "purchase"
    USAGE = "usage"
    REFUND = "refund"
    BONUS = "bonus"
    SUBSCRIPTION = "subscription"
    EXPIRY = "expiry"


class APIUsageType(enum.Enum):
    """Types of API usage that consume credits"""

    COMPANY_SEARCH = "company_search"  # 1 credit per search
    COMPANY_ENRICH = "company_enrich"  # 2 credits per enrichment
    COMPANY_EXPORT = "company_export"  # 1 credit per export row
    REPORT_BASIC = "report_basic"  # 10 credits
    REPORT_DETAILED = "report_detailed"  # 50 credits
    REPORT_CUSTOM = "report_custom"  # 100 credits
    API_LOOKUP = "api_lookup"  # 1 credit per lookup


# Credit costs per operation
CREDIT_COSTS = {
    APIUsageType.COMPANY_SEARCH: 0,  # Free searches, charged on export
    APIUsageType.COMPANY_ENRICH: 2,
    APIUsageType.COMPANY_EXPORT: 1,
    APIUsageType.REPORT_BASIC: 10,
    APIUsageType.REPORT_DETAILED: 50,
    APIUsageType.REPORT_CUSTOM: 100,
    APIUsageType.API_LOOKUP: 1,
}


class DataCredits(Base):
    """Credit balance for a client"""

    __tablename__ = "data_credits"

    __table_args__ = (Index("ix_data_credits_client", "client_id"),)

    id = Column(String(36), primary_key=True)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False, unique=True)

    # Credit balances
    balance = Column(Integer, default=0)  # Current available credits
    lifetime_credits = Column(Integer, default=0)  # Total credits ever received
    used_credits = Column(Integer, default=0)  # Total credits consumed

    # Monthly limits (for subscription plans)
    monthly_limit = Column(Integer, default=0)  # 0 = no limit
    monthly_used = Column(Integer, default=0)  # Reset each billing cycle

    # Timestamps
    last_used_at = Column(DateTime)
    reset_at = Column(DateTime)  # Next monthly reset date
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    transactions = relationship("CreditTransaction", back_populates="credit_account")

    def has_credits(self, amount: int = 1) -> bool:
        """Check if client has enough credits"""
        return self.balance >= amount

    def deduct(self, amount: int) -> bool:
        """Deduct credits if available"""
        if self.has_credits(amount):
            self.balance -= amount
            self.used_credits += amount
            self.monthly_used += amount
            self.last_used_at = datetime.utcnow()
            return True
        return False

    def add(self, amount: int) -> None:
        """Add credits to balance"""
        self.balance += amount
        self.lifetime_credits += amount


class CreditTransaction(Base):
    """Transaction log for credit changes"""

    __tablename__ = "credit_transactions"

    __table_args__ = (
        Index("ix_credit_tx_client", "client_id"),
        Index("ix_credit_tx_type", "transaction_type"),
        Index("ix_credit_tx_created", "created_at"),
    )

    id = Column(String(36), primary_key=True)
    credit_account_id = Column(String(36), ForeignKey("data_credits.id"), nullable=False)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False)

    # Transaction details
    transaction_type = Column(
        Enum(CreditTransactionType, native_enum=False, values_callable=_enum_values),
        nullable=False,
    )
    amount = Column(Integer, nullable=False)  # Positive for add, negative for deduct
    balance_after = Column(Integer, nullable=False)

    # Metadata
    description = Column(String(500))
    reference_id = Column(String(100))  # Payment ID, usage ID, etc.
    usage_type = Column(
        Enum(APIUsageType, native_enum=False, values_callable=_enum_values)
    )  # For USAGE transactions

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    credit_account = relationship("DataCredits", back_populates="transactions")


class APIUsageLog(Base):
    """Log of API usage for analytics and billing"""

    __tablename__ = "api_usage_logs"

    __table_args__ = (
        Index("ix_api_usage_client", "client_id"),
        Index("ix_api_usage_type", "usage_type"),
        Index("ix_api_usage_created", "created_at"),
        Index("ix_api_usage_api_key", "api_key_id"),
    )

    id = Column(String(36), primary_key=True)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False)
    api_key_id = Column(String(36), ForeignKey("api_keys.id"))

    # Usage details
    usage_type = Column(
        Enum(APIUsageType, native_enum=False, values_callable=_enum_values), nullable=False
    )
    credits_consumed = Column(Integer, nullable=False)

    # Request details
    endpoint = Column(String(200))
    method = Column(String(10))
    query_params = Column(Text)  # JSON
    result_count = Column(Integer, default=0)

    # Performance
    response_time_ms = Column(Integer)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)


class APIKey(Base):
    """API keys for programmatic access"""

    __tablename__ = "api_keys"

    __table_args__ = (
        Index("ix_api_keys_client", "client_id"),
        Index("ix_api_keys_key_hash", "key_hash"),
    )

    id = Column(String(36), primary_key=True)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False)

    # Key details
    name = Column(String(100), nullable=False)  # e.g., "Production", "Development"
    key_prefix = Column(String(10), nullable=False)  # First 8 chars for identification
    key_hash = Column(String(64), nullable=False, unique=True)  # SHA-256 hash

    # Permissions
    scopes = Column(Text)  # JSON array: ["read", "write", "export"]

    # Limits
    rate_limit_per_minute = Column(Integer, default=60)
    rate_limit_per_day = Column(Integer, default=10000)

    # Status
    is_active = Column(Integer, default=1)  # 1 = active, 0 = revoked
    last_used_at = Column(DateTime)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)  # Optional expiry

    # Relationships
    usage_logs = relationship("APIUsageLog", backref="api_key")
