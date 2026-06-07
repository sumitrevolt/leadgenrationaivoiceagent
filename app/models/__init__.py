"""
Database Models Package
Production-ready SQLAlchemy models for the B2B Intelligence Platform
"""
from app.models.base import (
    Base,
    get_db,
    get_async_db,
    get_db_session,
    get_async_session,
    async_session,
    init_db,
    init_async_db,
    close_async_db,
)
from app.models.lead import Lead, LeadStatus, LeadSource
from app.models.campaign import Campaign, CampaignStatus, CampaignType
from app.models.call_log import CallLog, CallOutcome, CallDirection
from app.models.client import Client, ClientStatus, SubscriptionPlan
from app.models.agent import Agent, AgentStatus
from app.models.agent_event import AgentEvent
from app.models.billing_record import (
    BillingRecord,
    BillingRecordType,
    BillingRecordStatus,
)
from app.models.user import User, UserRole, UserStatus, UserSession, AuditLog
from app.models.payment import (
    Subscription,
    Payment,
    Invoice,
    PaymentMethod,
    UsageRecord,
    PaymentGateway,
    SubscriptionStatus,
    PaymentStatus,
    InvoiceStatus,
    BillingCycle,
    PricingPlanModel,
)
from app.models.data_credits import (
    DataCredits,
    CreditTransaction,
    CreditTransactionType,
    APIUsageLog,
    APIUsageType,
    APIKey,
    CREDIT_COSTS,
)

__all__ = [
    # Base
    "Base",
    "get_db",
    "get_async_db",
    "get_db_session",
    "get_async_session",
    "async_session",
    "init_db",
    "init_async_db",
    "close_async_db",
    # Models
    "Lead",
    "LeadStatus",
    "LeadSource",
    "Campaign",
    "CampaignStatus",
    "CampaignType",
    "CallLog",
    "CallOutcome",
    "CallDirection",
    "Client",
    "ClientStatus",
    "SubscriptionPlan",
    # Agent / worker models
    "Agent",
    "AgentStatus",
    "AgentEvent",
    # Billing record models
    "BillingRecord",
    "BillingRecordType",
    "BillingRecordStatus",
    # User models
    "User",
    "UserRole",
    "UserStatus",
    "UserSession",
    "AuditLog",
    # Payment/Billing models
    "Subscription",
    "Payment",
    "Invoice",
    "PaymentMethod",
    "UsageRecord",
    "PaymentGateway",
    "SubscriptionStatus",
    "PaymentStatus",
    "InvoiceStatus",
    "BillingCycle",
    "PricingPlanModel",
    # Data Credits models (B2B Intelligence Platform)
    "DataCredits",
    "CreditTransaction",
    "CreditTransactionType",
    "APIUsageLog",
    "APIUsageType",
    "APIKey",
    "CREDIT_COSTS",
]
