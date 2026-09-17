"""Tests for Multi-Tenant Telegram Bot."""

import pytest
from app.telegram.multi_tenant import (
    MultiTenantTelegramBot,
    TenantConfig,
    TenantAuditLog,
)


class TestMultiTenantTelegramBot:
    """Test multi-tenant Telegram bot."""
    
    def test_initialization(self):
        """Test bot initialization."""
        bot = MultiTenantTelegramBot()
        assert len(bot.tenants) >= 1  # At least leadgenai
    
    def test_register_tenant(self):
        """Test tenant registration."""
        bot = MultiTenantTelegramBot()
        result = bot.register_tenant(
            tenant_id="test_tenant",
            bot_token="123456:ABC-DEF",
            chat_id="123456",
            rate_limit=10,
        )
        assert result["success"] is True
        assert bot.get_tenant("test_tenant") is not None
    
    def test_unregister_tenant(self):
        """Test tenant unregistration."""
        bot = MultiTenantTelegramBot()
        bot.register_tenant(
            tenant_id="temp_tenant",
            bot_token="test_token",
        )
        result = bot.unregister_tenant("temp_tenant")
        assert result["success"] is True
        assert bot.get_tenant("temp_tenant") is None
    
    def test_list_tenants(self):
        """Test listing tenants."""
        bot = MultiTenantTelegramBot()
        tenants = bot.list_tenants()
        assert len(tenants) >= 1
    
    def test_activate_deactivate_tenant(self):
        """Test tenant activation/deactivation."""
        bot = MultiTenantTelegramBot()
        bot.register_tenant(
            tenant_id="inactive_tenant",
            bot_token="test_token",
        )
        
        # Deactivate
        result = bot.deactivate_tenant("inactive_tenant")
        assert result["success"] is True
        
        tenant = bot.get_tenant("inactive_tenant")
        assert tenant["is_active"] is False
        
        # Activate
        result = bot.activate_tenant("inactive_tenant")
        assert result["success"] is True
        
        tenant = bot.get_tenant("inactive_tenant")
        assert tenant["is_active"] is True
    
    def test_send_message(self):
        """Test sending message."""
        bot = MultiTenantTelegramBot()
        bot.register_tenant(
            tenant_id="msg_tenant",
            bot_token="test_token",
        )
        
        result = bot.send_message(
            tenant_id="msg_tenant",
            chat_id="123456",
            message="Hello world",
        )
        assert result["success"] is True
        assert result["queued"] is True
    
    def test_rate_limiting(self):
        """Test rate limiting."""
        bot = MultiTenantTelegramBot()
        bot.register_tenant(
            tenant_id="rate_tenant",
            bot_token="test_token",
            rate_limit=2,
        )
        
        # Send 2 messages (should succeed)
        bot.send_message("rate_tenant", "123", "msg1")
        bot.send_message("rate_tenant", "123", "msg2")
        
        # Third should be rate limited
        result = bot.send_message("rate_tenant", "123", "msg3")
        assert "error" in result
        assert "Rate limit" in result["error"]
    
    def test_webhook_processing(self):
        """Test webhook processing."""
        bot = MultiTenantTelegramBot()
        bot.register_tenant(
            tenant_id="web_tenant",
            bot_token="test_token",
            chat_id="123",
        )
        
        update = {
            "message": {
                "message_id": 1,
                "chat": {"id": 123, "type": "private"},
                "text": "/start",
                "from": {"id": 456},
            }
        }
        
        result = bot.process_webhook(update)
        assert result["status"] == "processed"
        assert result["tenant_id"] == "web_tenant"
    
    def test_audit_logging(self):
        """Test audit logging."""
        bot = MultiTenantTelegramBot()
        bot.register_tenant(
            tenant_id="audit_tenant",
            bot_token="test_token",
        )
        
        # Perform some actions
        bot.send_message("audit_tenant", "123", "test")
        
        # Check audit logs
        logs = bot.get_audit_logs(tenant_id="audit_tenant")
        assert len(logs) > 0
        assert logs[0]["action"] == "send_message"


class TestTenantConfig:
    """Test TenantConfig model."""
    
    def test_tenant_config_creation(self):
        """Test creating tenant config."""
        config = TenantConfig(
            tenant_id="test",
            bot_token="123:ABC",
            chat_id="123456",
        )
        assert config.tenant_id == "test"
        assert config.is_active is True
    
    def test_tenant_config_to_dict(self):
        """Test converting to dict."""
        config = TenantConfig(
            tenant_id="test",
            bot_token="123:ABC",
        )
        data = config.to_dict()
        assert data["tenant_id"] == "test"
        assert "..." in data["bot_token"]  # Masked


class TestTenantRateLimiter:
    """Test tenant rate limiter."""
    
    def test_rate_limiter(self):
        """Test rate limiting logic."""
        from app.telegram.multi_tenant import TenantRateLimiter
        
        limiter = TenantRateLimiter()
        limiter.set_limit("tenant1", 2)
        
        assert limiter.is_allowed("tenant1") is True
        assert limiter.is_allowed("tenant1") is True
        assert limiter.is_allowed("tenant1") is False  # Rate limited
