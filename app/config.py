"""
AI Voice Agent - B2B Lead Generation Platform
Main Application Configuration
"""
import os
from typing import Optional, List
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Application
    app_name: str = "AI Voice Agent"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "change-this-in-production"
    
    # Database
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/voice_agent_db"
    redis_url: str = "redis://localhost:6379/0"
    
    # AI Models
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    google_cloud_project_id: str = ""
    google_cloud_location: str = "us-central1"
    default_llm: str = "gemini-1.5-flash"  # gpt-4, gpt-4o, claude-3-opus, gemini-1.5-flash, vertex-gemini, local-llama
    local_llm_path: str = "models/llama-3-8b-instruct.Q4_K_M.gguf"
    
    # Speech-to-Text
    deepgram_api_key: str = ""
    google_speech_credentials: str = ""
    default_stt: str = "deepgram"  # deepgram, google
    
    # Text-to-Speech
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    azure_speech_key: str = ""
    azure_speech_region: str = "centralindia"
    default_tts: str = "edge"  # elevenlabs, azure, edge
    
    # Telephony
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    twilio_webhook_url: str = ""
    
    exotel_sid: str = ""
    exotel_token: str = ""
    exotel_api_key: str = ""
    exotel_api_token: str = ""
    exotel_subdomain: str = ""
    exotel_caller_id: str = ""
    default_telephony: str = "twilio"  # twilio, exotel
    
    # Lead Scraping
    google_maps_api_key: str = ""
    proxy_url: Optional[str] = None
    use_proxy: bool = False
    
    # CRM Integrations
    hubspot_api_key: str = ""
    zoho_client_id: str = ""
    zoho_client_secret: str = ""
    zoho_refresh_token: str = ""
    
    # Google Sheets
    google_sheets_credentials: str = ""
    default_spreadsheet_id: str = ""
    
    # WhatsApp
    whatsapp_business_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_business_account_id: str = ""
    
    # Email
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""
    
    # Compliance
    dnd_api_url: str = ""
    dnd_api_key: str = ""
    enable_dnd_check: bool = True
    
    # Call Settings
    max_call_duration_seconds: int = 300
    max_concurrent_calls: int = 10
    call_retry_attempts: int = 3
    call_retry_delay_minutes: int = 30
    working_hours_start: str = "09:00"
    working_hours_end: str = "18:00"
    timezone: str = "Asia/Kolkata"
    
    # Support Contact Settings
    support_phone_number: str = ""  # E.g., +919876543210
    support_whatsapp_number: str = ""  # E.g., +919876543210
    support_email: str = ""  # E.g., support@leadgenai.com
    platform_website_url: str = "https://app.leadgenai.com"
    
    # Monitoring
    sentry_dsn: Optional[str] = None
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR
    
    # Platform Settings (Multi-Tier Automation)
    auto_start_platform: bool = True  # Auto-start 24/7 automation on startup
    platform_company_name: str = "LeadGen AI Solutions"
    platform_target_industries: List[str] = Field(
        default=["digital_marketing", "real_estate", "solar", "education", "insurance", "logistics"]
    )
    platform_target_cities: List[str] = Field(
        default=["Mumbai", "Delhi", "Bangalore", "Chennai", "Hyderabad", "Pune", "Kolkata", "Ahmedabad"]
    )
    
    # Trial/Subscription Settings
    trial_duration_days: int = 7
    trial_calls_limit: int = 100
    starter_monthly_price: int = 15000  # INR
    growth_monthly_price: int = 25000
    enterprise_monthly_price: int = 50000
    
    # Google Cloud Storage (for profile pictures)
    gcs_bucket_name: str = "auraleads-storage"
    gcs_profile_pictures_bucket: str = "auraleads-profile-pictures"
    
    # JWT Settings
    jwt_secret_key: str = "change-this-jwt-secret-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7
    
    # Security
    cors_origins: List[str] = Field(default=["http://localhost:3000", "http://localhost:5173"])
    rate_limit_per_minute: int = 100
    max_failed_login_attempts: int = 5
    account_lockout_minutes: int = 30
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Export settings instance
settings = get_settings()
