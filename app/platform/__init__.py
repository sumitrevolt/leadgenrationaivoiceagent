"""
Multi-Tenant Platform Configuration
Automated B2B Lead Generation Platform

Business Model:
1. YOUR COMPANY (Platform Owner) - Uses this system to find B2B clients
2. YOUR CLIENTS (Tenants) - Get voice agents to generate leads for their businesses

Everything is AUTOMATED with minimal human intervention.
"""
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class TenantType(Enum):
    """Type of tenant on the platform"""
    PLATFORM_OWNER = "platform_owner"  # Your company
    CLIENT = "client"  # Businesses using your service


class SubscriptionTier(Enum):
    """Subscription tiers for clients"""
    TRIAL = "trial"  # 7-day free trial
    STARTER = "starter"  # ₹15,000/month - 500 calls
    GROWTH = "growth"  # ₹25,000/month - 2000 calls
    ENTERPRISE = "enterprise"  # ₹50,000/month - Unlimited
    CUSTOM = "custom"


class AutomationLevel(Enum):
    """Level of automation for tenant"""
    FULL_AUTO = "full_auto"  # Everything automated
    SEMI_AUTO = "semi_auto"  # Human reviews hot leads
    MANUAL = "manual"  # Human approves each step


class TenantConfig(BaseModel):
    """Configuration for each tenant (client)"""
    tenant_id: str
    company_name: str
    tenant_type: TenantType
    
    # Business Details
    industry: str
    target_audience: str  # B2B or B2C
    services: List[str]
    target_niches: List[str]
    target_cities: List[str]
    
    # Automation Settings
    automation_level: AutomationLevel = AutomationLevel.FULL_AUTO
    auto_scrape: bool = True  # Auto-scrape leads daily
    auto_call: bool = True  # Auto-call scraped leads
    auto_followup: bool = True  # Auto-followup on interested leads
    auto_appointment: bool = True  # Auto-book appointments
    auto_crm_sync: bool = True  # Auto-sync to CRM
    
    # Subscription
    subscription_tier: SubscriptionTier
    monthly_call_limit: int
    calls_used: int = 0
    
    # Notifications (minimal human touch points)
    notify_on_hot_lead: bool = True
    notify_on_appointment: bool = True
    notify_daily_report: bool = True
    notification_channels: List[str] = ["whatsapp", "email"]
    
    # API Keys (each tenant can have their own)
    custom_telephony_config: Optional[Dict] = None
    custom_crm_config: Optional[Dict] = None
    
    # Status
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.now)


# Platform Owner Configuration
PLATFORM_CONFIG = {
    "company_name": "LeadGen AI Solutions",  # Your Company Name
    "tagline": "Automated B2B Lead Generation Voice Agents",
    
    # What your company sells
    "services": [
        "AI Voice Agent for Lead Generation",
        "Automated Cold Calling System",
        "Smart Lead Qualification",
        "CRM Integration Services"
    ],
    
    # Target niches - businesses that need lead generation
    "target_niches": [
        "real_estate",
        "solar_energy",
        "digital_marketing",
        "insurance",
        "financial_services",
        "saas_companies",
        "recruitment_agencies",
        "educational_institutes"
    ],
    
    # Target cities for finding clients
    "target_cities": [
        "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai",
        "Pune", "Ahmedabad", "Kolkata", "Jaipur", "Lucknow"
    ],
    
    # Automation for YOUR company's lead gen
    "automation": {
        "daily_scrape_time": "06:00",  # Scrape new leads daily
        "daily_call_start": "09:00",  # Start calling
        "daily_call_end": "18:00",  # Stop calling
        "leads_per_day": 100,  # Scrape 100 potential clients/day
        "calls_per_day": 50,  # Call 50 potential clients/day
        "auto_onboard_trial": True  # Auto-start trial for interested leads
    }
}
