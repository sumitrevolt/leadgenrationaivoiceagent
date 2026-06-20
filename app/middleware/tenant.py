"""Multi-tenant white-label middleware — resolve reseller branding from the Host header.

A reseller uses a subdomain like ``agencyname.leadsgenai.in`` (or a custom domain
mapped to the same app). We parse the host, and if the left-most label matches a
marketing client's slug, we attach that client's branding (title/logo/colors/support
email) to ``request.state.tenant`` so the customer dashboard can white-label its
response.

FAIL-OPEN by design: any parse/lookup error -> ``request.state.tenant = None`` and the
request proceeds exactly as before. Never raises, never blocks a request.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Apex hosts that are NOT reseller subdomains (their left label is "www"/"app"/etc.).
_BASE_HOSTS = {"leadsgenai.in", "www.leadsgenai.in"}
_RESERVED_SUBS = {"www", "app", "api", "admin", "mail", "smtp", "ftp", "cdn", "static", ""}


def _subdomain(host: str) -> str:
    """Left-most label of a ``*.leadsgenai.in`` host, else '' (apex / unknown)."""
    host = (host or "").split(":")[0].strip().lower().rstrip(".")
    if not host or host in _BASE_HOSTS:
        return ""
    if host.endswith(".leadsgenai.in"):
        sub = host[: -len(".leadsgenai.in")]
        # only a single-label subdomain (agencyname), not deeper nesting
        return sub if "." not in sub else sub.split(".")[0]
    return ""  # custom apex domains would be mapped via a future domain table


def resolve_branding(host: str) -> dict | None:
    """Return a reseller branding dict for this host, or None. Never raises."""
    try:
        client = None
        sub = _subdomain(host)
        if sub and sub not in _RESERVED_SUBS:
            from app.marketing.clients_store import get_by_slug

            client = get_by_slug(sub)
        if not client:
            # Custom domain per client (HighLevel-parity): client record me
            # `custom_domain` field exact-match (Caddy on-demand TLS se serve).
            h = (host or "").split(":")[0].strip().lower().rstrip(".")
            if h and h not in _BASE_HOSTS and not h.endswith(".leadsgenai.in"):
                from app.marketing.clients_store import list_clients

                client = next(
                    (
                        c
                        for c in list_clients()
                        if str(c.get("custom_domain") or "").strip().lower() == h
                    ),
                    None,
                )
        if not client:
            return None
        sub = str(client.get("slug") or sub)
        brand = client.get("brand") if isinstance(client.get("brand"), dict) else {}
        return {
            "slug": sub,
            "title": str(client.get("business_name") or sub.title()),
            "logo_text": str(
                (brand or {}).get("logo_text") or client.get("business_name") or sub.title()
            ),
            "primary_color": str((brand or {}).get("primary") or "#2563eb"),
            "accent_color": str((brand or {}).get("accent") or "#1f7a3d"),
            "tagline": str((brand or {}).get("tagline") or ""),
            "support_email": str(client.get("email") or "support@leadsgenai.in"),
        }
    except Exception as e:
        logger.debug("resolve_branding skipped for %r: %s", host, e)
        return None


class TenantBrandingMiddleware(BaseHTTPMiddleware):
    """Attach reseller branding (or None) to request.state.tenant. Fail-open."""

    async def dispatch(self, request, call_next):
        try:
            request.state.tenant = resolve_branding(request.headers.get("host", ""))
        except Exception:
            request.state.tenant = None
        return await call_next(request)


__all__ = ["TenantBrandingMiddleware", "resolve_branding"]
