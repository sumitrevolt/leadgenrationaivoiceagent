"""
Production Configuration
Loads secrets from Google Cloud Secret Manager in production
Falls back to environment variables for local development
"""
import os
from typing import Optional, Dict, Any
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)


class SecretManagerClient:
    """
    Google Cloud Secret Manager client
    Caches secrets for performance
    """
    
    _instance = None
    _cache: Dict[str, str] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._client = None
        self._project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
        self._initialized = True
        
        if self._project_id and self._is_gcp_environment():
            self._init_client()
    
    def _is_gcp_environment(self) -> bool:
        """Check if running in GCP"""
        return any([
            os.environ.get("K_SERVICE"),  # Cloud Run
            os.environ.get("FUNCTION_NAME"),  # Cloud Functions
            os.environ.get("GAE_APPLICATION"),  # App Engine
            os.environ.get("GOOGLE_CLOUD_PROJECT"),
        ])
    
    def _init_client(self):
        """Initialize Secret Manager client"""
        try:
            from google.cloud import secretmanager
            self._client = secretmanager.SecretManagerServiceClient()
            logger.info("✅ Secret Manager client initialized")
        except ImportError:
            logger.warning("google-cloud-secret-manager not installed, using env vars")
        except Exception as e:
            logger.warning(f"Secret Manager init failed: {e}, using env vars")
    
    def get_secret(
        self,
        secret_id: str,
        version: str = "latest",
        default: Optional[str] = None,
    ) -> Optional[str]:
        """
        Get secret from Secret Manager or environment variable
        
        Priority:
        1. Cache
        2. Environment variable
        3. Secret Manager
        4. Default value
        """
        cache_key = f"{secret_id}:{version}"
        
        # Check cache
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Check environment variable (allows override)
        env_key = secret_id.upper().replace("-", "_")
        env_value = os.environ.get(env_key)
        if env_value:
            self._cache[cache_key] = env_value
            return env_value
        
        # Try Secret Manager
        if self._client and self._project_id:
            try:
                name = f"projects/{self._project_id}/secrets/{secret_id}/versions/{version}"
                response = self._client.access_secret_version(request={"name": name})
                value = response.payload.data.decode("UTF-8")
                self._cache[cache_key] = value
                return value
            except Exception as e:
                logger.debug(f"Secret {secret_id} not found in Secret Manager: {e}")
        
        return default
    
    def clear_cache(self):
        """Clear secret cache"""
        self._cache.clear()


def get_secret(
    secret_id: str,
    default: Optional[str] = None,
) -> Optional[str]:
    """Convenience function to get secret"""
    client = SecretManagerClient()
    return client.get_secret(secret_id, default=default)


def get_secret_or_env(
    secret_id: str,
    env_var: Optional[str] = None,
    default: str = "",
) -> str:
    """
    Get secret from Secret Manager or environment variable
    For production config integration
    """
    # Try environment variable first (allows local override)
    env_key = env_var or secret_id.upper().replace("-", "_")
    env_value = os.environ.get(env_key)
    if env_value:
        return env_value
    
    # Try Secret Manager
    secret_value = get_secret(secret_id)
    if secret_value:
        return secret_value
    
    return default


class ProductionConfig:
    """
    Production configuration with Secret Manager integration
    Use this class for production deployments
    """
    
    def __init__(self):
        self._sm = SecretManagerClient()
        self._env = os.environ.get("APP_ENV", "development")
        self._prefix = f"{self._env}-" if self._env != "production" else ""
    
    @property
    def is_production(self) -> bool:
        return self._env == "production"
    
    @property
    def database_url(self) -> str:
        return get_secret_or_env(
            f"{self._prefix}database-url",
            "DATABASE_URL",
            "postgresql+asyncpg://user:password@localhost:5432/leadgen_ai"
        )
    
    @property
    def redis_url(self) -> str:
        return get_secret_or_env(
            f"{self._prefix}redis-url",
            "REDIS_URL",
            "redis://localhost:6379/0"
        )
    
    @property
    def openai_api_key(self) -> str:
        return get_secret_or_env(f"{self._prefix}openai-api-key", "OPENAI_API_KEY")
    
    @property
    def gemini_api_key(self) -> str:
        return get_secret_or_env(f"{self._prefix}gemini-api-key", "GEMINI_API_KEY")
    
    @property
    def anthropic_api_key(self) -> str:
        return get_secret_or_env(f"{self._prefix}anthropic-api-key", "ANTHROPIC_API_KEY")
    
    @property
    def elevenlabs_api_key(self) -> str:
        return get_secret_or_env(f"{self._prefix}elevenlabs-api-key", "ELEVENLABS_API_KEY")
    
    @property
    def twilio_account_sid(self) -> str:
        return get_secret_or_env(f"{self._prefix}twilio-account-sid", "TWILIO_ACCOUNT_SID")
    
    @property
    def twilio_auth_token(self) -> str:
        return get_secret_or_env(f"{self._prefix}twilio-auth-token", "TWILIO_AUTH_TOKEN")
    
    @property
    def exotel_api_key(self) -> str:
        return get_secret_or_env(f"{self._prefix}exotel-api-key", "EXOTEL_API_KEY")
    
    @property
    def exotel_api_token(self) -> str:
        return get_secret_or_env(f"{self._prefix}exotel-api-token", "EXOTEL_API_TOKEN")
    
    def get_all_config(self) -> Dict[str, Any]:
        """Get all configuration as dict"""
        return {
            "environment": self._env,
            "is_production": self.is_production,
            "database_url": "***" if self.database_url else None,
            "redis_url": "***" if self.redis_url else None,
            "openai_configured": bool(self.openai_api_key),
            "gemini_configured": bool(self.gemini_api_key),
            "twilio_configured": bool(self.twilio_account_sid),
            "exotel_configured": bool(self.exotel_api_key),
        }


@lru_cache()
def get_production_config() -> ProductionConfig:
    """Get cached production config"""
    return ProductionConfig()
