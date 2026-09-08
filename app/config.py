"""
AI Voice Agent - B2B Lead Generation Platform
Main Application Configuration
"""

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Application
    app_name: str = "AI Voice Agent"
    app_env: str = "development"
    debug: bool = True
    # Placeholder default so dev/CI boots without a .env; production is blocked
    # from running on this default by validate_production_settings() below.
    # Generate a real one: python -c "import secrets; print(secrets.token_urlsafe(64))"
    secret_key: str = "change-this-in-production-min-32-chars-xxxxx"

    # Database
    database_url: str = (
        "sqlite+aiosqlite:///./data/leadgen_dev.db"  # dev-only default; prod uses env
    )
    redis_url: str = "redis://localhost:6379/0"

    # Read-only ops API key (OPS-008). Empty = DISABLED (fail-closed): the key
    # path in require_admin_or_ops_readonly() is inert until armed. Honoured ONLY
    # for the GET endpoints listed in auth_deps.OPS_READONLY_ALLOWLIST — never for
    # a mutation, never for /api/ops/hotqueue/action.
    # Generate: python -c "import secrets; print(secrets.token_urlsafe(48))"
    ops_readonly_token: str = ""

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
    # Cerebras (free, production gpt-oss-120b) + OpenRouter free fallbacks —
    # OpenAI-compatible LLM fallbacks in the free_ai chain. Both OPTIONAL.
    cerebras_api_key: str = ""  # cloud.cerebras.ai — gpt-oss-120b
    openrouter_api_key: str = ""  # openrouter.ai key 1 — deepseek/deepseek-chat:free
    openrouter_api_key_2: str = ""  # key 2 (rotation — 4x rate-limit headroom)
    openrouter_api_key_3: str = ""  # key 3
    openrouter_api_key_4: str = ""  # key 4
    xai_api_key: str = ""  # x.ai (Grok — Groq se ALAG company; credits-based)
    sambanova_api_key: str = ""  # cloud.sambanova.ai — 100% free, no card, Llama-3.3-70B
    mistral_api_key: str = ""  # console.mistral.ai — free tier La Plateforme, mistral-small
    nvidia_api_key: str = ""  # build.nvidia.com — NVIDIA NIM (OpenAI-compatible); free tier 40 RPM + metered credits, deep-tail fallback
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
    # Premium voice = Gemini native TTS (app/voice_agent/gemini_tts.py) — reuses the
    # existing GEMINI_API_KEY (no new creds), tried FIRST when GEMINI_TTS!=0, EdgeTTS
    # fallback otherwise. Env knobs: GEMINI_TTS / GEMINI_TTS_VOICE / GEMINI_TTS_MODEL.

    # Telephony
    # Exotel removed 2026-06-18, Twilio removed 2026-07-07 — provider is now
    # Vobiz-only (see vobiz_* below).
    default_telephony: str = "vobiz"  # vobiz

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
    proxy_url: str | None = None
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
    whatsapp_app_secret: str = ""  # Meta webhook X-Hub-Signature-256 verification
    whatsapp_verify_token: str = ""  # Meta webhook GET handshake token
    # --- Self-hosted WhatsApp stack (WAHA Core) — "apna khud ka" provider ---
    # Sidesteps Meta Business *verification* entirely (the real Cloud-API blocker). Links an
    # EXISTING WhatsApp account via QR scan. Default provider stays "cloud" so setting these
    # alone changes nothing until WHATSAPP_PROVIDER=waha. A number is EITHER on Cloud API
    # OR on a Web-session stack — never both at once.
    whatsapp_provider: str = (
        "cloud"  # "cloud" (Meta Cloud API) | "waha"/"selfhost" (own WAHA stack)
    )
    whatsapp_business_number: str = ""  # linked business number, digits e.g. 918261030181
    waha_base_url: str = ""  # e.g. http://waha:3000 (in-network) — set = self-host stack reachable
    waha_api_key: str = (
        ""  # X-Api-Key for the WAHA HTTP API (matches WAHA_API_KEY on the container)
    )
    waha_session: str = "default"  # WAHA session name holding the linked number
    waha_webhook_token: str = ""  # shared secret in the WAHA->app webhook URL (path gate)

    # Email
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""
    # Owner alert inbox (env NOTIFY_EMAIL) — nayi inquiry / daily digest yahan
    # email hote hain. Empty = notifications off (SMTP creds bhi chahiye).
    notify_email: str = ""
    # Automated cold-email outreach (env AUTO_EMAIL_OUTREACH) — scraped
    # prospects ko system KHUD email karta hai (Rohan). Default OFF — SMTP
    # creds + yeh flag dono on hone par hi emails jaate hain.
    auto_email_outreach: bool = False
    # Roz max kitne prospects ko email kare (domain reputation safety).
    outreach_daily_cap: int = 50
    # From-name jo cold email me dikhta hai (footer/sender).
    outreach_from_name: str = "Sumit — LeadGen AI"
    # Email API providers (SMTP se zyada reliable; key ho to API se bhejta hai).
    # Resend: console resend.com (3000/mo free). Brevo: brevo.com (300/day free).
    resend_api_key: str = ""  # env RESEND_API_KEY
    brevo_api_key: str = ""  # env BREVO_API_KEY

    # Hot/warm lead-score thresholds, SINGLE source of truth (2026-07-08 pipeline-
    # automation audit found this hardcoded inconsistently: 60 in lead_scoring.py's
    # env default vs 70 in models/lead.py/call_manager.py/campaign.py. 70 chosen as
    # canonical (3 of 4 call sites + TASKS.md's own "70+" convention already used it).
    lead_hot_threshold: int = 70
    lead_warm_threshold: int = 40

    # Compliance
    dnd_api_url: str = ""
    dnd_api_key: str = ""
    enable_dnd_check: bool = True

    # Payment Gateways — Stripe removed 2026-07-10, Razorpay removed 2026-06-18.
    # Kept as empty defaults for backward compat (no more runtime access to these keys).
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""

    # Razorpay removed 2026-06-18 — no online gateway; payments via manual UPI.

    # Payment Settings
    default_currency: str = "INR"  # INR for India, USD for international
    auto_detect_payment_gateway: bool = True  # Auto-select based on currency/country
    # Apna UPI VPA (env UPI_VPA, e.g. 9876543210@ybl) — landing page ka
    # "Shuru karo" payment modal isi se QR banata hai. Empty = path disabled.
    upi_vpa: str = ""

    # Social auto-post — Meta Graph API (Track 3). OFF by default; creds na ho to
    # publisher mock-mode chalta hai (kuch publish nahi hota, sirf record). App-review
    # unlock ke baad flag + tokens set karo. Per-client tokens data/meta_connections.jsonl
    # me; yeh GLOBAL fallback (platform ke apne page/IG) ke liye.
    social_autopost: bool = False  # env SOCIAL_AUTOPOST — real publishing master switch
    meta_page_access_token: str = ""  # env META_PAGE_ACCESS_TOKEN (global fallback page token)
    meta_facebook_page_id: str = ""  # env META_FACEBOOK_PAGE_ID
    meta_instagram_account_id: str = ""  # env META_INSTAGRAM_ACCOUNT_ID
    meta_graph_version: str = "v21.0"  # env META_GRAPH_VERSION

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
    sentry_dsn: str | None = None
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR

    @staticmethod
    def missing_sentry_api_creds() -> list[str]:
        """Return Sentry issue-level API env vars that are unset while DSN-based
        event capture needs them for UI issue triage. Pure + testable — main.py
        logs a warning when this is non-empty."""
        import os

        _pairs = (
            ("SENTRY_AUTH_TOKEN", os.environ.get("SENTRY_AUTH_TOKEN", "").strip()),
            ("SENTRY_ORG", os.environ.get("SENTRY_ORG", "").strip()),
            ("SENTRY_PROJECT", os.environ.get("SENTRY_PROJECT", "").strip()),
        )
        return [k for k, v in _pairs if not v]

    # Platform Settings (Multi-Tier Automation)
    auto_start_platform: bool = True  # Auto-start 24/7 automation on startup
    platform_company_name: str = "LeadGen AI Solutions"
    platform_target_industries: list[str] = Field(
        default=["digital_marketing", "real_estate", "solar", "education", "insurance", "logistics"]
    )
    platform_target_cities: list[str] = Field(
        default=[
            "Mumbai",
            "Delhi",
            "Bangalore",
            "Chennai",
            "Hyderabad",
            "Pune",
            "Kolkata",
            "Ahmedabad",
        ]
    )

    # Trial/Subscription Settings
    trial_duration_days: int = 7
    trial_calls_limit: int = 100
    starter_monthly_price: int = 1999  # INR (packages.py = public truth)
    growth_monthly_price: int = 2999
    enterprise_monthly_price: int = 5999  # = Advanced tier (packages.py = public truth)

    # Google Cloud Storage (for profile pictures)
    gcs_bucket_name: str = "auraleads-storage"
    gcs_profile_pictures_bucket: str = "auraleads-profile-pictures"

    # JWT Settings
    # Placeholder default so dev/CI boots without a .env; production is blocked
    # from running on this default by validate_production_settings() below.
    # Generate a real one: python -c "import secrets; print(secrets.token_urlsafe(64))"
    jwt_secret_key: str = "change-this-jwt-secret-in-production-xxxxxxx"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7

    # Security
    cors_origins: list[str] = Field(default=["http://localhost:3000", "http://localhost:5173"])
    rate_limit_per_minute: int = 100
    max_failed_login_attempts: int = 5
    account_lockout_minutes: int = 30

    # Validators
    @field_validator("app_env")
    @classmethod
    def validate_app_env(cls, v: str) -> str:
        """Validate app environment"""
        allowed = ["development", "staging", "production", "test"]
        if v.lower() not in allowed:
            raise ValueError(f"app_env must be one of {allowed}")
        return v.lower()

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level"""
        allowed = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v.upper()

    @field_validator("max_call_duration_seconds")
    @classmethod
    def validate_call_duration(cls, v: int) -> int:
        """Validate call duration is reasonable"""
        if v < 30 or v > 3600:
            raise ValueError("max_call_duration_seconds must be between 30 and 3600")
        return v

    @field_validator("max_concurrent_calls")
    @classmethod
    def validate_concurrent_calls(cls, v: int) -> int:
        """Validate concurrent calls limit"""
        if v < 1 or v > 1000:
            raise ValueError("max_concurrent_calls must be between 1 and 1000")
        return v

    @field_validator("rate_limit_per_minute")
    @classmethod
    def validate_rate_limit(cls, v: int) -> int:
        """Validate rate limit"""
        if v < 1 or v > 10000:
            raise ValueError("rate_limit_per_minute must be between 1 and 10000")
        return v

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        """Validate critical settings in production"""
        if self.app_env == "production":
            if self.debug:
                raise ValueError("DEBUG must be False in production")

            # Sirf exact-default check kaafi NAHI tha — 2026-07-02 me prod
            # months tak `JWT_SECRET_KEY=your-jwt-secret...` placeholder pe
            # chala (guard paas ho gaya, tokens guessable-key se signed).
            # Ab koi bhi placeholder-pattern ya chhota secret = boot REFUSED.
            def _weak(val: str) -> bool:
                v = (val or "").strip().lower()
                return (
                    len(v) < 32
                    or v.startswith(("your-", "change-this", "changeme", "xxx", "placeholder"))
                    or "example" in v
                )

            if _weak(self.secret_key):
                raise ValueError(
                    "SECRET_KEY weak/placeholder in production — set a real random value "
                    "(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
                )
            if _weak(self.jwt_secret_key):
                raise ValueError(
                    "JWT_SECRET_KEY weak/placeholder in production — set a real random value "
                    "(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
                )
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


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Export settings instance
settings = get_settings()
