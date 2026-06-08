"""
AI Voice Agent - B2B Lead Generation Platform
Main Application Configuration
"""
import os
from typing import Optional, List
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator, model_validator
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

    # Vector RAG (Qdrant) — empty = disabled; KB falls back to Chroma/keyword
    qdrant_url: str = ""
    
    # AI Models
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    # Multi-key rotation (comma/space/newline separated) — STT + LLM share a
    # Gemini free-tier quota PER KEY, so 2-3 keys here keep the phone agent alive
    # when one key exhausts. Falls back to gemini_api_key when empty.
    gemini_api_keys: str = ""
    # Groq (free, fast) — Whisper-large-v3 STT + LLM (OpenAI-compatible REST).
    # Primary STT when set; LLM fallback when Gemini quota is exhausted.
    groq_api_key: str = ""
    # Cerebras (free, fastest llama-3.3-70b) + OpenRouter (free deepseek) —
    # OpenAI-compatible LLM fallbacks in the free_ai chain. Both OPTIONAL.
    cerebras_api_key: str = ""    # cloud.cerebras.ai — llama-3.3-70b
    openrouter_api_key: str = ""  # openrouter.ai — deepseek/deepseek-chat:free
    xai_api_key: str = ""         # x.ai (Grok — Groq se ALAG company; credits-based)
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

    # Vobiz (India-native SIP trunk + voice API — primary trunk for P3)
    vobiz_auth_id: str = ""
    vobiz_auth_token: str = ""
    vobiz_trunk_id: str = ""
    vobiz_trunk_domain: str = ""
    vobiz_sip_user: str = ""
    vobiz_sip_pass: str = ""
    vobiz_sip_realm: str = ""
    vobiz_caller_id: str = ""

    # Public base URL — webhooks (e.g. Vobiz answer_url) isi pe bante hain
    public_base_url: str = "https://leadsgenai.in"

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
    # Owner alert inbox (env NOTIFY_EMAIL) — nayi inquiry / daily digest yahan
    # email hote hain. Empty = notifications off (SMTP creds bhi chahiye).
    notify_email: str = ""
    
    # Compliance
    dnd_api_url: str = ""
    dnd_api_key: str = ""
    enable_dnd_check: bool = True
    
    # Payment Gateways
    # Stripe (International)
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    
    # Razorpay (India)
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    
    # Payment Settings
    default_currency: str = "INR"  # INR for India, USD for international
    auto_detect_payment_gateway: bool = True  # Auto-select based on currency/country
    # Apna UPI VPA (env UPI_VPA, e.g. 9876543210@ybl) — landing page ka
    # "Shuru karo" payment modal isi se QR banata hai. Empty = path disabled.
    upi_vpa: str = ""
    
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
    starter_monthly_price: int = 999  # INR
    growth_monthly_price: int = 2499
    enterprise_monthly_price: int = 5999
    
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
    
    # Validators
    @field_validator('app_env')
    @classmethod
    def validate_app_env(cls, v: str) -> str:
        """Validate app environment"""
        allowed = ['development', 'staging', 'production', 'test']
        if v.lower() not in allowed:
            raise ValueError(f"app_env must be one of {allowed}")
        return v.lower()
    
    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level"""
        allowed = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v.upper()
    
    @field_validator('max_call_duration_seconds')
    @classmethod
    def validate_call_duration(cls, v: int) -> int:
        """Validate call duration is reasonable"""
        if v < 30 or v > 3600:
            raise ValueError("max_call_duration_seconds must be between 30 and 3600")
        return v
    
    @field_validator('max_concurrent_calls')
    @classmethod
    def validate_concurrent_calls(cls, v: int) -> int:
        """Validate concurrent calls limit"""
        if v < 1 or v > 1000:
            raise ValueError("max_concurrent_calls must be between 1 and 1000")
        return v
    
    @field_validator('rate_limit_per_minute')
    @classmethod
    def validate_rate_limit(cls, v: int) -> int:
        """Validate rate limit"""
        if v < 1 or v > 10000:
            raise ValueError("rate_limit_per_minute must be between 1 and 10000")
        return v
    
    @model_validator(mode='after')
    def validate_production_settings(self) -> 'Settings':
        """Validate critical settings in production"""
        if self.app_env == 'production':
            if self.secret_key == "change-this-in-production":
                raise ValueError("secret_key must be changed in production")
            if self.jwt_secret_key == "change-this-jwt-secret-in-production":
                raise ValueError("jwt_secret_key must be changed in production")
            if self.debug:
                raise ValueError("debug must be False in production")
        return self
    
    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.app_env == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development"""
        return self.app_env == "development"
    
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
