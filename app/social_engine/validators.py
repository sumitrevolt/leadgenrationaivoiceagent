"""social_engine.validators — Phase 6 platform-adaptation validators.

Per-platform limits (2026-07 reference — verify at activation, since platforms
adjust). Enforces:
  - caption_length         (per-platform char cap)
  - hashtag_limit          (per-platform tag count cap)
  - unsupported_media      (media_type × platform matrix)
  - unsupported_characters (control-byte + zero-width injections)
  - duplicate_content      (same caption+platform+client within window)
  - prohibited_claims      (e.g. "guaranteed", "risk-free" — India ad code)
  - missing_disclaimer     (paid promo / affiliate CTA needs a disclosure)

`validate_post(platform, post, recent_captions=None)` returns list[dict] of
issues (severity=warn|error). `error` = drain must fail-fast; `warn` = log +
still publish (for now). Never raises. Empty list = clean.
"""

from __future__ import annotations

import re
from typing import Any

# --------------------------------------------------------------------------- #
# Platform limits (verify at activation).                                     #
# --------------------------------------------------------------------------- #
_CAPTION_LIMITS: dict[str, int] = {
    "facebook": 63206,
    "instagram": 2200,
    "gbp": 1500,
    "linkedin": 3000,
    "x": 280,
    "youtube": 5000,  # description max
    "whatsapp": 4096,  # text message max
    "postiz": 5000,  # gateway-side, longest-wins
}

# Hashtag caps (0 = platform effectively has none / uncapped).
_HASHTAG_LIMITS: dict[str, int] = {
    "facebook": 30,
    "instagram": 30,
    "gbp": 0,  # GBP posts don't officially cap tags — keep sane
    "linkedin": 30,
    "x": 0,  # X counts hashtags against 280 char limit only
    "youtube": 15,  # description-hashtag effective visible cap
    "whatsapp": 0,
    "postiz": 30,
}

# Supported media types per platform (broad — matches provider dispatch shape).
_MEDIA_SUPPORT: dict[str, set[str]] = {
    "facebook": {"text", "image", "video"},
    "instagram": {"image", "video"},  # IG post needs media
    "gbp": {"text", "image"},
    "linkedin": {"text", "image", "video"},
    "x": {"text", "image", "video"},
    "youtube": {"video"},  # channel upload = video only
    "whatsapp": {"text", "image", "video"},
    "postiz": {"text", "image", "video"},
}

# ASCI 2019+ Indian advertising code — disallowed unqualified claims for
# consumer promo posts. `warn` for now (not error) because context can qualify.
_PROHIBITED_CLAIMS = (
    r"\bguaranteed\b",
    r"\brisk[\s-]?free\b",
    r"\b100%\s+safe\b",
    r"\bcures?\s+\w+\s+disease\b",
    r"\bmiracle\s+cure\b",
    r"\bno\s+side[\s-]?effect(s)?\b",
    r"\binstant\s+weight[\s-]?loss\b",
)
_PROHIBITED_RE = re.compile("|".join(_PROHIBITED_CLAIMS), re.IGNORECASE)

# Zero-width / bidi / control chars that would silently corrupt caption or
# smuggle text past provider filters.
_INJECTION_RE = re.compile(r"[​‌‍⁠‮⁦⁧⁨⁩]")


def _issue(rule: str, severity: str, message: str, **extra: Any) -> dict[str, Any]:
    out = {"rule": rule, "severity": severity, "message": message}
    out.update(extra)
    return out


def validate_post(
    platform: str,
    post: dict[str, Any],
    recent_captions: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return list of validation issues for a post about to be published.
    Empty list = clean. Ordered highest-severity first."""
    issues: list[dict[str, Any]] = []
    try:
        p = str(platform or "").strip().lower()
        caption = str(post.get("caption") or "")
        media_type = str(post.get("media_type") or "text").lower()
        hashtags = post.get("hashtags") or []
        if isinstance(hashtags, str):
            hashtags = [h for h in hashtags.replace(",", " ").split() if h]

        # caption length
        cap_limit = _CAPTION_LIMITS.get(p, 5000)
        if len(caption) > cap_limit:
            issues.append(
                _issue(
                    "caption_length",
                    "error",
                    f"{p} caption cap {cap_limit} chars; got {len(caption)}",
                    limit=cap_limit,
                    actual=len(caption),
                )
            )

        # hashtag count
        ht_limit = _HASHTAG_LIMITS.get(p, 0)
        if ht_limit and len(hashtags) > ht_limit:
            issues.append(
                _issue(
                    "hashtag_limit",
                    "error",
                    f"{p} allows up to {ht_limit} hashtags; got {len(hashtags)}",
                    limit=ht_limit,
                    actual=len(hashtags),
                )
            )

        # media support
        supported = _MEDIA_SUPPORT.get(p, {"text", "image", "video"})
        if media_type not in supported:
            issues.append(
                _issue(
                    "unsupported_media",
                    "error",
                    f"{p} doesn't accept media_type={media_type}; allowed {sorted(supported)}",
                    media_type=media_type,
                    allowed=sorted(supported),
                )
            )
        # Instagram + YouTube must have media (text-only rejected).
        if p in ("instagram", "youtube") and media_type == "text":
            issues.append(
                _issue(
                    "missing_media",
                    "error",
                    f"{p} requires media (image or video)",
                )
            )

        # zero-width / bidi injection
        if _INJECTION_RE.search(caption):
            issues.append(
                _issue(
                    "unsupported_characters",
                    "warn",
                    "Caption contains zero-width / bidi characters — will be stripped",
                )
            )

        # prohibited claims (Indian ad-code)
        m = _PROHIBITED_RE.search(caption)
        if m:
            issues.append(
                _issue(
                    "prohibited_claims",
                    "warn",
                    f"Caption contains restricted claim '{m.group(0)}' — verify with owner",
                    match=m.group(0),
                )
            )

        # missing disclaimer for paid/affiliate posts
        cta = str(post.get("cta") or "").lower()
        content_type = str(post.get("content_type") or "").lower()
        if content_type in ("ad", "sponsored", "affiliate"):
            hay = (caption + " " + cta).lower()
            if not any(
                tok in hay
                for tok in ("#ad", "#sponsored", "sponsored", "paid partnership", "#partner")
            ):
                issues.append(
                    _issue(
                        "missing_disclaimer",
                        "error",
                        "Sponsored/affiliate content missing #ad / #sponsored disclosure",
                        content_type=content_type,
                    )
                )

        # duplicate content window (caller supplies recent_captions from
        # store.list_jobs). Case-insensitive whitespace-normalized match.
        if recent_captions:
            norm = " ".join(caption.strip().lower().split())
            recent_norm = {" ".join(c.strip().lower().split()) for c in recent_captions if c}
            if norm and norm in recent_norm:
                issues.append(
                    _issue(
                        "duplicate_content",
                        "warn",
                        "Same caption published recently on this platform — may look spammy",
                    )
                )
    except Exception as e:
        issues.append(_issue("validator_error", "warn", f"validator crashed: {e}"))

    # Errors before warns.
    issues.sort(key=lambda x: 0 if x["severity"] == "error" else 1)
    return issues


def has_blocking_error(issues: list[dict[str, Any]]) -> bool:
    return any(i.get("severity") == "error" for i in (issues or []))
