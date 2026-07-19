"""
Database Models Package
Production-ready SQLAlchemy models for the B2B Intelligence Platform
"""

from app.models.account import Account
from app.models.agent import Agent, AgentStatus
from app.models.agent_event import AgentEvent
from app.models.agent_task import AgentTask
from app.models.approval_notification import ApprovalNotification
from app.models.automation_log import AutomationLog
from app.models.base import (
    Base,
    async_session,
    close_async_db,
    get_async_db,
    get_async_session,
    get_db,
    get_db_session,
    init_async_db,
    init_db,
)
from app.models.billing_record import BillingRecord, BillingRecordStatus, BillingRecordType
from app.models.call_log import CallDirection, CallLog, CallOutcome
from app.models.campaign import Campaign, CampaignStatus, CampaignType
from app.models.campaign_variant import CampaignVariant
from app.models.client import Client, ClientStatus, SubscriptionPlan
from app.models.compliance_audit import ComplianceAuditLog, ComplianceDecision
from app.models.contact import Contact
from app.models.customer_deliverable import (
    CustomerDeliverable,
    DeliverableChannel,
    DeliverableStatus,
)
from app.models.data_credits import (
    CREDIT_COSTS,
    APIKey,
    APIUsageLog,
    APIUsageType,
    CreditTransaction,
    CreditTransactionType,
    DataCredits,
)
from app.models.dev_task import DevTask
from app.models.dev_usage import DevTaskUsage
from app.models.interaction import Interaction
from app.models.lead import Lead, LeadSource, LeadStatus
from app.models.lead_pipeline import (
    LeadPipelineBatch,
    LeadPipelineQualityIssue,
    LeadPipelineStageRun,
)
from app.models.owner_os import OwnerCommand, OwnerKillSwitch, OwnerOSAuditEvent
from app.models.payment import (
    BillingCycle,
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentGateway,
    PaymentMethod,
    PaymentStatus,
    PricingPlanModel,
    Subscription,
    SubscriptionStatus,
    UsageRecord,
)
from app.models.user import AuditLog, User, UserRole, UserSession, UserStatus

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
    "Account",
    "Contact",
    "Interaction",
    "CampaignVariant",
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
    "AgentTask",
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
    # Customer Deliverables models
    "CustomerDeliverable",
    "DeliverableStatus",
    "DeliverableChannel",
    # Automation Log model
    "AutomationLog",
    # Approval notification audit model
    "ApprovalNotification",
    "DevTask",
    "DevTaskUsage",
    # Lead-gen pipeline batch tracking models (2026-07-08)
    "LeadPipelineBatch",
    "LeadPipelineStageRun",
    "LeadPipelineQualityIssue",
    # Owner OS durable tables
    "OwnerCommand",
    "OwnerKillSwitch",
    "OwnerOSAuditEvent",
    # Compliance audit model
    "ComplianceAuditLog",
    "ComplianceDecision",
]
