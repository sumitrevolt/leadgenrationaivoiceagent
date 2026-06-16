"""Security building-blocks (bot-protection, CSRF, etc.).

Currently exposes the Cloudflare Turnstile dependency. Anything added here
must follow project ethos: INERT without creds, fail-OPEN on infra error,
fail-CLOSED on missing/invalid token when armed.
"""

from app.security.turnstile import site_key, verify_turnstile

__all__ = ["verify_turnstile", "site_key"]
