"""
Production Readiness Tests
Verify all production components are working correctly
"""
import pytest
import asyncio
from datetime import datetime


class TestConfiguration:
    """Test configuration is properly loaded"""
    
    def test_settings_load(self):
        from app.config import settings
        
        assert settings.app_name == "AI Voice Agent"
        assert settings.app_env in ["development", "staging", "production"]
        assert settings.log_level in ["DEBUG", "INFO", "WARNING", "ERROR"]
    
    def test_secret_key_configured(self):
        from app.config import settings
        
        # In production, secret key should be changed
        if settings.app_env == "production":
            assert settings.secret_key != "change-this-in-production"
            assert len(settings.secret_key) >= 32


class TestDatabaseModels:
    """Test database models are properly configured"""
    
    def test_base_model_loads(self):
        from app.models.base import Base
        assert Base is not None
    
    def test_all_models_load(self):
        from app.models import Lead, Campaign, CallLog, Client
        
        assert Lead is not None
        assert Campaign is not None
        assert CallLog is not None
        assert Client is not None
    
    def test_db_session_factory(self):
        from app.models.base import get_db
        
        # Should not raise
        gen = get_db()
        assert gen is not None


class TestMiddleware:
    """Test middleware components"""
    
    def test_middleware_imports(self):
        from app.middleware import (
            SecurityHeadersMiddleware,
            RequestTracingMiddleware,
            RateLimitMiddleware,
            setup_middleware,
        )
        
        assert SecurityHeadersMiddleware is not None
        assert RequestTracingMiddleware is not None
        assert RateLimitMiddleware is not None
        assert setup_middleware is not None
    
    def test_api_key_auth(self):
        from app.middleware import verify_api_key, require_api_key
        
        assert verify_api_key is not None
        assert require_api_key is not None


class TestExceptionHandlers:
    """Test exception handling"""
    
    def test_custom_exceptions(self):
        from app.exceptions import (
            LeadGenException,
            ValidationException,
            AuthenticationException,
            ResourceNotFoundException,
            RateLimitException,
        )
        
        # Test base exception
        exc = LeadGenException("Test error", code="TEST")
        assert exc.message == "Test error"
        assert exc.code == "TEST"
        assert exc.status_code == 500
        
        # Test validation exception
        exc = ValidationException("Invalid field", field="email")
        assert exc.status_code == 422
        assert exc.details["field"] == "email"
        
        # Test not found exception
        exc = ResourceNotFoundException("Lead", "123")
        assert exc.status_code == 404
        assert "Lead" in exc.message


class TestCache:
    """Test caching layer"""
    
    def test_cache_imports(self):
        from app.cache import (
            get_redis_client,
            Cache,
            RedisRateLimiter,
            DistributedLock,
        )
        
        assert get_redis_client is not None
        assert Cache is not None
        assert RedisRateLimiter is not None
        assert DistributedLock is not None
    
    @pytest.mark.asyncio
    async def test_inmemory_cache(self):
        from app.cache import InMemoryCache
        
        cache = InMemoryCache()
        
        # Test set and get
        await cache.set("test_key", "test_value", ex=60)
        value = await cache.get("test_key")
        assert value == "test_value"
        
        # Test delete
        await cache.delete("test_key")
        value = await cache.get("test_key")
        assert value is None
    
    @pytest.mark.asyncio
    async def test_rate_limiter(self):
        from app.cache import RedisRateLimiter
        
        limiter = RedisRateLimiter(requests_per_minute=5)
        
        # Should be allowed initially
        allowed, info = await limiter.is_allowed("test_client")
        assert allowed is True
        assert info["remaining"] >= 0


class TestLogger:
    """Test logging configuration"""
    
    def test_logger_setup(self):
        from app.utils.logger import setup_logger
        
        logger = setup_logger("test_logger")
        assert logger is not None
        assert logger.name == "test_logger"
    
    def test_json_formatter(self):
        from app.utils.logger import JSONFormatter
        import logging
        
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        
        output = formatter.format(record)
        assert "Test message" in output
        assert '"level": "INFO"' in output


class TestAPIRouters:
    """Test API routers are configured"""
    
    def test_routers_import(self):
        from app.api import leads, campaigns, analytics, webhooks
        from app.api.platform import router as platform_router
        from app.api.health import router as health_router
        
        assert leads.router is not None
        assert campaigns.router is not None
        assert analytics.router is not None
        assert webhooks.router is not None
        assert platform_router is not None
        assert health_router is not None


class TestPlatformComponents:
    """Test platform components"""
    
    def test_orchestrator_imports(self):
        from app.platform.orchestrator import PlatformOrchestrator
        
        assert PlatformOrchestrator is not None
    
    def test_tenant_manager_imports(self):
        from app.platform.tenant_manager import TenantManager
        
        assert TenantManager is not None
    
    def test_scraper_manager_imports(self):
        from app.lead_scraper.scraper_manager import LeadScraperManager
        
        assert LeadScraperManager is not None


class TestAlembicMigrations:
    """Test Alembic is configured"""
    
    def test_alembic_config_exists(self):
        import os
        assert os.path.exists("alembic.ini")
        assert os.path.exists("alembic/env.py")
        assert os.path.exists("alembic/versions/001_initial.py")


class TestDockerConfiguration:
    """Test Docker configuration"""
    
    def test_dockerfile_exists(self):
        import os
        assert os.path.exists("Dockerfile")
        assert os.path.exists("Dockerfile.production")
    
    def test_docker_compose_exists(self):
        import os
        assert os.path.exists("docker-compose.yml")
        assert os.path.exists("docker-compose.prod.yml")


class TestInfrastructure:
    """Test infrastructure configuration"""
    
    def test_terraform_exists(self):
        import os
        assert os.path.exists("infrastructure/terraform/main.tf")
    
    def test_github_actions_exists(self):
        import os
        assert os.path.exists(".github/workflows/deploy.yml")
    
    def test_nginx_config_exists(self):
        import os
        assert os.path.exists("infrastructure/nginx/nginx.conf")


class TestProductionChecklist:
    """Test production readiness checklist items"""
    
    def test_env_example_exists(self):
        import os
        assert os.path.exists(".env.example")
    
    def test_production_checklist_exists(self):
        import os
        assert os.path.exists("PRODUCTION_CHECKLIST.md")
    
    def test_pre_commit_config_exists(self):
        import os
        assert os.path.exists(".pre-commit-config.yaml")
    
    def test_secrets_baseline_exists(self):
        import os
        assert os.path.exists(".secrets.baseline")
    
    def test_pyproject_toml_exists(self):
        import os
        assert os.path.exists("pyproject.toml")
    
    def test_makefile_exists(self):
        import os
        assert os.path.exists("Makefile")
    
    def test_security_md_exists(self):
        import os
        assert os.path.exists("SECURITY.md")
    
    def test_contributing_md_exists(self):
        import os
        assert os.path.exists("CONTRIBUTING.md")
    
    def test_changelog_md_exists(self):
        import os
        assert os.path.exists("CHANGELOG.md")
    
    def test_license_exists(self):
        import os
        assert os.path.exists("LICENSE")
    
    def test_api_docs_exist(self):
        import os
        assert os.path.exists("docs/API.md")
    
    def test_github_templates_exist(self):
        import os
        assert os.path.exists(".github/PULL_REQUEST_TEMPLATE.md")
        assert os.path.exists(".github/ISSUE_TEMPLATE/bug_report.md")
        assert os.path.exists(".github/ISSUE_TEMPLATE/feature_request.md")
    
    def test_github_workflows_exist(self):
        import os
        assert os.path.exists(".github/workflows/deploy.yml")
        assert os.path.exists(".github/workflows/test.yml")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
