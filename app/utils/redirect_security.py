"""
Security utilities for redirect URL validation.
P0-2 Fix: Prevent open redirect vulnerabilities by validating against allowlist.
"""

from urllib.parse import urlparse

from fastapi import HTTPException

# Allowed redirect origins — must be explicitly configured
# These are the only hosts we allow redirects to
ALLOWED_REDIRECT_ORIGINS = {
    "https://leadsgenai.in",
    "https://app.leadsgenai.in",
    "https://admin.leadsgenai.in",
}

# Development-only: allow localhost
ALLOWED_REDIRECT_ORIGINS_DEV = ALLOWED_REDIRECT_ORIGINS | {
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
}


def validate_redirect_url(url: str | None, is_dev: bool = False) -> str:
    """
    Validate a redirect URL against the allowlist.

    Args:
        url: The redirect URL to validate (can be None or empty)
        is_dev: Whether running in development mode

    Returns:
        Safe redirect URL (guaranteed to be in allowlist)

    Raises:
        HTTPException: 400 if URL is not in allowlist
    """
    if not url or not url.strip():
        # Empty/None redirect → default to homepage
        return "https://leadsgenai.in"

    url = url.strip()

    # Don't allow relative URLs to be redirected externally
    # (relative URLs are safe, but we want to be explicit)
    if url.startswith("/"):
        # Relative URL is safe — return as-is
        return url

    # For absolute URLs, validate against allowlist
    try:
        parsed = urlparse(url)
    except Exception:
        # Malformed URL — reject
        raise HTTPException(status_code=400, detail="Invalid redirect URL")

    # Reconstruct origin from parsed URL
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or parsed.hostname or ""
    origin = f"{scheme}://{netloc}" if netloc else ""

    # Determine which allowlist to use
    allowed_origins = ALLOWED_REDIRECT_ORIGINS_DEV if is_dev else ALLOWED_REDIRECT_ORIGINS

    # Check if origin is in allowlist
    if origin not in allowed_origins:
        raise HTTPException(
            status_code=400,
            detail=f"Redirect to '{origin}' not allowed. Allowed origins: {', '.join(allowed_origins)}",
        )

    return url
