"""
Database Models Package
Production-ready SQLAlchemy models for the Voice Agent Platform
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
]
