"""Multi-Tenant Telegram Enterprise Bot with Isolation.

DEPRECATED / TEST-ONLY (2026-09-21, ADR-198). This module has NO production
import: the canonical Telegram control plane is ``app/platform/telegram_coordinator.py``
(dual-bot architecture, polling lease, owner gating) with
``app/integrations/telegram_bot.py`` as the command handler. Only
``tests/test_telegram.py`` still imports this file, which is why it was not
deleted — runtime removal requires proving no consumer first. Do not wire new
work here; see docs/TELEGRAM_DUAL_BOT_SETUP.md.

Enterprise-grade Telegram bot integration with:
- Multi-tenant isolation (each client gets their own bot namespace)
- Per-tenant message routing
- Tenant-aware command handling
- Async Celery task processing
- Rate limiting per tenant
- Audit logging for compliance
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


class TenantConfig(BaseModel):
    """Configuration for a tenant's Telegram bot."""

    tenant_id: str
    bot_token: str
    chat_id: str | None = None
    group_id: str | None = None
    ops_group_id: str | None = None
    is_active: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_message_at: str | None = None
    message_count: int = 0
    rate_limit_per_minute: int = 30

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "bot_token": (self.bot_token[:3] + "...") if self.bot_token else "",
            "chat_id": self.chat_id,
            "group_id": self.group_id,
            "ops_group_id": self.ops_group_id,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "last_message_at": self.last_message_at,
            "message_count": self.message_count,
            "rate_limit_per_minute": self.rate_limit_per_minute,
        }


class TelegramMessage(BaseModel):
    """Represents a Telegram message for processing."""

    message_id: int
    chat_id: int
    from_user_id: int | None = None
    text: str | None = None
    command: str | None = None
    reply_to_message_id: int | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tenant_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "chat_id": self.chat_id,
            "from_user_id": self.from_user_id,
            "text": self.text,
            "command": self.command,
            "reply_to_message_id": self.reply_to_message_id,
            "timestamp": self.timestamp,
            "tenant_id": self.tenant_id,
        }


class TenantAuditLog(BaseModel):
    """Audit log entry for tenant activity."""

    tenant_id: str
    action: str
    resource: str
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    user_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "action": self.action,
            "resource": self.resource,
            "details": self.details,
            "timestamp": self.timestamp,
            "user_id": self.user_id,
        }


class TenantRateLimiter:
    """Per-tenant rate limiter."""

    def __init__(self):
        self.limits: dict[str, list[float]] = defaultdict(list)
        self.max_per_minute: dict[str, int] = {}

    def set_limit(self, tenant_id: str, max_per_minute: int):
        """Set rate limit for a tenant."""
        self.max_per_minute[tenant_id] = max_per_minute

    def is_allowed(self, tenant_id: str) -> bool:
        """Check if tenant has remaining rate limit."""
        max_limit = self.max_per_minute.get(tenant_id, 30)
        now = datetime.now(timezone.utc)
        one_min_ago = now.timestamp() - 60

        # Clean old entries
        self.limits[tenant_id] = [t for t in self.limits[tenant_id] if t > one_min_ago]

        # Check limit
        if len(self.limits[tenant_id]) >= max_limit:
            return False

        self.limits[tenant_id].append(now.timestamp())
        return True


class MultiTenantTelegramBot:
    """Enterprise-grade multi-tenant Telegram bot."""

    def __init__(self, config_path: str = "data/telegram_tenants.json"):
        self.config_path = config_path
        self.tenants: dict[str, TenantConfig] = {}
        self.rate_limiter = TenantRateLimiter()
        self.audit_logs: list[TenantAuditLog] = []
        self._message_queue: list[TelegramMessage] = []
        self._load_config()
        self._register_default_tenants()

    def _load_config(self):
        """Load tenant configuration from disk."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path) as f:
                    data = json.load(f)
                for tenant_id, config_data in data.items():
                    try:
                        tenant = TenantConfig(**config_data)
                        self.tenants[tenant_id] = tenant
                        self.rate_limiter.set_limit(tenant_id, tenant.rate_limit_per_minute)
                    except Exception as e:
                        print(f"[telegram_bot] Failed to load tenant {tenant_id}: {e}")
            except Exception as e:
                print(f"[telegram_bot] Failed to load config: {e}")

    def _save_config(self):
        """Save tenant configuration to disk."""
        try:
            data = {tid: t.to_dict() for tid, t in self.tenants.items()}
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[telegram_bot] Failed to save config: {e}")

    def _register_default_tenants(self):
        """Register default tenants if none exist."""
        if self.tenants:
            return

        # Register leadgenai.in tenant (own brand)
        self.tenants["leadgenai"] = TenantConfig(
            tenant_id="leadgenai",
            bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
            group_id=os.environ.get("TELEGRAM_OPS_GROUP_ID", ""),
            is_active=bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        )

        self._save_config()

    def _audit(self, tenant_id: str, action: str, resource: str, details: dict = None):
        """Create audit log entry."""
        log = TenantAuditLog(
            tenant_id=tenant_id,
            action=action,
            resource=resource,
            details=details or {},
        )
        self.audit_logs.append(log)
        # Keep only last 1000 logs
        if len(self.audit_logs) > 1000:
            self.audit_logs = self.audit_logs[-1000:]

    def register_tenant(
        self,
        tenant_id: str,
        bot_token: str,
        chat_id: str | None = None,
        group_id: str | None = None,
        ops_group_id: str | None = None,
        rate_limit: int = 30,
    ) -> dict[str, Any]:
        """Register a new tenant."""
        if tenant_id in self.tenants:
            return {"success": False, "error": f"Tenant {tenant_id} already exists"}

        tenant = TenantConfig(
            tenant_id=tenant_id,
            bot_token=bot_token,
            chat_id=chat_id,
            group_id=group_id,
            ops_group_id=ops_group_id,
            rate_limit_per_minute=rate_limit,
        )
        self.tenants[tenant_id] = tenant
        self.rate_limiter.set_limit(tenant_id, rate_limit)
        self._save_config()
        self._audit(tenant_id, "register", "tenant")

        return {"success": True, "tenant": tenant.to_dict()}

    def unregister_tenant(self, tenant_id: str) -> dict[str, Any]:
        """Unregister a tenant."""
        if tenant_id not in self.tenants:
            return {"success": False, "error": f"Tenant {tenant_id} not found"}

        del self.tenants[tenant_id]
        if tenant_id in self.rate_limiter.max_per_minute:
            del self.rate_limiter.max_per_minute[tenant_id]
        self._save_config()
        self._audit(tenant_id, "unregister", "tenant")

        return {"success": True}

    def get_tenant(self, tenant_id: str) -> dict[str, Any] | None:
        """Get tenant configuration."""
        tenant = self.tenants.get(tenant_id)
        if not tenant:
            return None
        return tenant.to_dict()

    def list_tenants(self) -> list[dict[str, Any]]:
        """List all tenants."""
        return [t.to_dict() for t in self.tenants.values()]

    def activate_tenant(self, tenant_id: str) -> dict[str, Any]:
        """Activate a tenant."""
        tenant = self.tenants.get(tenant_id)
        if not tenant:
            return {"error": f"Tenant {tenant_id} not found"}

        tenant.is_active = True
        self._save_config()
        self._audit(tenant_id, "activate", "tenant")

        return {"success": True, "tenant": tenant.to_dict()}

    def deactivate_tenant(self, tenant_id: str) -> dict[str, Any]:
        """Deactivate a tenant."""
        tenant = self.tenants.get(tenant_id)
        if not tenant:
            return {"error": f"Tenant {tenant_id} not found"}

        tenant.is_active = False
        self._save_config()
        self._audit(tenant_id, "deactivate", "tenant")

        return {"success": True, "tenant": tenant.to_dict()}

    def send_message(
        self,
        tenant_id: str,
        chat_id: str,
        message: str,
        parse_mode: str | None = "HTML",
    ) -> dict[str, Any]:
        """Send message to tenant (async via Celery)."""
        tenant = self.tenants.get(tenant_id)
        if not tenant:
            return {"error": f"Tenant {tenant_id} not found"}

        if not tenant.is_active:
            return {"error": f"Tenant {tenant_id} is not active"}

        # Rate limit check
        if not self.rate_limiter.is_allowed(tenant_id):
            return {"error": f"Rate limit exceeded for tenant {tenant_id}"}

        # Add to message queue for async processing
        self._message_queue.append(
            {
                "tenant_id": tenant_id,
                "chat_id": chat_id,
                "message": message,
                "parse_mode": parse_mode,
                "queued_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        tenant.message_count += 1
        tenant.last_message_at = datetime.now(timezone.utc).isoformat()
        self._save_config()
        self._audit(tenant_id, "send_message", f"chat:{chat_id}")

        return {
            "success": True,
            "message_id": f"q-{len(self._message_queue)}",
            "queued": True,
        }

    def process_webhook(self, update: dict[str, Any]) -> dict[str, Any]:
        """Process incoming Telegram webhook update."""
        # Extract tenant_id from chat_id or from update
        message = update.get("message", {})
        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))

        # Find tenant by chat_id
        tenant_id = None
        for tid, tenant in self.tenants.items():
            if tenant.chat_id == chat_id or tenant.group_id == chat_id:
                tenant_id = tid
                break

        if not tenant_id:
            return {"status": "ignored", "reason": "unknown_tenant"}

        tenant = self.tenants[tenant_id]
        if not tenant.is_active:
            return {"status": "ignored", "reason": "tenant_inactive"}

        # Parse message
        telegram_msg = TelegramMessage(
            message_id=message.get("message_id"),
            chat_id=int(chat_id),
            from_user_id=message.get("from", {}).get("id"),
            text=message.get("text"),
            command=message.get("text", "").split()[0].replace("@", "")
            if message.get("text")
            else None,
            reply_to_message_id=message.get("reply_to_message", {}).get("message_id"),
            tenant_id=tenant_id,
        )

        # Process based on command
        result = self._handle_command(tenant_id, telegram_msg)

        # Update tenant stats
        tenant.message_count += 1
        tenant.last_message_at = datetime.now(timezone.utc).isoformat()
        self._save_config()

        return {
            "status": "processed",
            "tenant_id": tenant_id,
            "command": telegram_msg.command,
            "result": result,
        }

    def _handle_command(self, tenant_id: str, message: TelegramMessage) -> dict[str, Any]:
        """Handle Telegram command based on tenant context."""
        command = message.command or ""

        # Command routing by tenant
        if command == "/start":
            return {"response": f"Welcome to LeadGen AI Bot! Tenant: {tenant_id}"}
        elif command == "/status":
            tenant = self.tenants.get(tenant_id, {})
            return {
                "response": f"Tenant {tenant_id} is {'active' if tenant.get('is_active') else 'inactive'}",
                "message_count": tenant.get("message_count", 0),
            }
        elif command == "/help":
            return {
                "response": "/start - Welcome\n/status - Check status\n/help - This message",
            }
        else:
            return {"response": "Unknown command. Use /help for options."}

    def get_queue_status(self) -> dict[str, Any]:
        """Get message queue status."""
        return {
            "pending_messages": len(self._message_queue),
            "total_tenants": len(self.tenants),
            "active_tenants": len([t for t in self.tenants.values() if t.is_active]),
        }

    def get_audit_logs(
        self,
        tenant_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get audit logs."""
        if tenant_id:
            logs = [l for l in self.audit_logs if l.tenant_id == tenant_id]
        else:
            logs = self.audit_logs
        return [l.to_dict() for l in logs[-limit:]]


# Module-level singleton
_telegram_bot: MultiTenantTelegramBot | None = None


def get_telegram_bot() -> MultiTenantTelegramBot:
    """Get or create singleton MultiTenantTelegramBot."""
    global _telegram_bot
    if _telegram_bot is None:
        _telegram_bot = MultiTenantTelegramBot()
    return _telegram_bot


def register_tenant(
    tenant_id: str,
    bot_token: str,
    chat_id: str | None = None,
    group_id: str | None = None,
    ops_group_id: str | None = None,
    rate_limit: int = 30,
) -> dict[str, Any]:
    """Convenience function to register a tenant."""
    return get_telegram_bot().register_tenant(
        tenant_id, bot_token, chat_id, group_id, ops_group_id, rate_limit
    )


def send_message(
    tenant_id: str,
    chat_id: str,
    message: str,
) -> dict[str, Any]:
    """Convenience function to send a message."""
    return get_telegram_bot().send_message(tenant_id, chat_id, message)


def process_webhook(update: dict[str, Any]) -> dict[str, Any]:
    """Convenience function to process a webhook."""
    return get_telegram_bot().process_webhook(update)


def list_tenants() -> list[dict[str, Any]]:
    """Convenience function to list tenants."""
    return get_telegram_bot().list_tenants()


def get_audit_logs(
    tenant_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Convenience function to get audit logs."""
    return get_telegram_bot().get_audit_logs(tenant_id, limit)
