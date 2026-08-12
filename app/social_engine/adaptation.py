"""social_engine.adaptation — Phase 6 platform-specific content transformer.

Whereas `validators.py` REJECTS non-conforming posts, `adaptation.py` fixes
them where fixing is safe + non-lossy:
  - IG: strip URLs from caption (IG doesn't linkify; add "link in bio"),
        merge hashtags into caption tail (IG algorithmic pref)
  - X: split long caption into thread parts (1/n · 2/n ·…)
  - GBP: strip hashtags entirely (GBP posts don't render hashtags nicely)
  - LinkedIn: prefer commentary + no hashtag-tail
  - YouTube: description = caption + hashtag tail (channel-safe)
  - WhatsApp / Postiz / FB: minimal transform (pass-through)

Contract: `adapt_for_platform(post, platform) → adapted post dict`. Never
raises. Original `post` never mutated (returns a copy). Called from the drain
BEFORE `validators.validate_post` so the validator sees the actual-published
shape.
"""

from __future__ import annotations

import re
from typing import Any

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def _copy(post: dict[str, Any]) -> dict[str, Any]:
    return {k: (list(v) if isinstance(v, list) else v) for k, v in (post or {}).items()}


def _strip_urls(text: str) -> str:
    return _URL_RE.sub("", text or "").strip()


def _hashtag_tail(hashtags: list[str], limit: int = 30) -> str:
    """Space-joined `#foo #bar` from a raw list (already lowercased/deduped by
    store._norm_hashtags). Empty list = ''."""
    if not hashtags:
        return ""
    tags = ["#" + h.lstrip("#") for h in hashtags[:limit] if h]
    return " ".join(tags)


def _truncate(text: str, cap: int, suffix: str = "…") -> str:
    """Ellipsis-truncate at word boundary if possible."""
    text = text or ""
    if len(text) <= cap:
        return text
    cut = text[: cap - len(suffix)]
    sp = cut.rfind(" ")
    if sp > int(cap * 0.7):
        cut = cut[:sp]
    return cut + suffix


def _thread_split(text: str, per_part: int = 275) -> list[str]:
    """Split long text into X-thread parts. per_part 275 leaves room for
    "  (N/M)" suffix on the 280-char cap."""
    text = (text or "").strip()
    if not text:
        return [""]
    words = text.split()
    parts: list[str] = []
    cur = ""
    for w in words:
        if len(cur) + len(w) + 1 <= per_part:
            cur = (cur + " " + w).strip()
        else:
            if cur:
                parts.append(cur)
            cur = w
    if cur:
        parts.append(cur)
    if len(parts) > 1:
        parts = [f"{p}  ({i + 1}/{len(parts)})" for i, p in enumerate(parts)]
    return parts


def adapt_for_platform(post: dict[str, Any], platform: str) -> dict[str, Any]:
    """Return a NEW post dict transformed for the platform. Never mutates input.
    Never raises — on error returns a shallow copy of the original."""
    try:
        p = str(platform or "").strip().lower()
        out = _copy(post)
        caption = str(out.get("caption") or "")
        hashtags = out.get("hashtags") if isinstance(out.get("hashtags"), list) else []

        if p == "instagram":
            # IG: strip URLs (not linkified), append hashtag tail up to 30.
            no_url = _strip_urls(caption)
            if _URL_RE.search(caption):
                no_url = (no_url + "\n\n(Link in bio 🔗)").strip()
            tail = _hashtag_tail(hashtags, limit=30)
            new_cap = (no_url + (("\n\n" + tail) if tail else "")).strip()
            out["caption"] = _truncate(new_cap, 2200)
            out["_adapted"] = "instagram"

        elif p == "x":
            # X: thread split. Only the first part goes to caption; rest in extra.
            base = caption
            tail = _hashtag_tail(hashtags, limit=3)  # X counts hashtags in 280
            if tail:
                base = (base.rstrip() + " " + tail).strip()
            parts = _thread_split(base, per_part=275)
            out["caption"] = parts[0]
            if len(parts) > 1:
                extra = dict(out.get("extra") or {})
                extra["thread_parts"] = parts
                out["extra"] = extra
            out["_adapted"] = "x"

        elif p == "gbp":
            # GBP: strip hashtags entirely (poor render).
            no_url = caption  # GBP does support URLs
            out["caption"] = _truncate(no_url, 1500)
            out["hashtags"] = []
            out["_adapted"] = "gbp"

        elif p == "linkedin":
            # LI: commentary first; hashtag tail limited to 5 (algorithm pref).
            tail = _hashtag_tail(hashtags, limit=5)
            new_cap = (caption + (("\n\n" + tail) if tail else "")).strip()
            out["caption"] = _truncate(new_cap, 3000)
            out["_adapted"] = "linkedin"

        elif p == "youtube":
            # Description = caption + tag tail (channel-safe).
            tail = _hashtag_tail(hashtags, limit=15)
            desc = (caption + (("\n\n" + tail) if tail else "")).strip()
            out["caption"] = _truncate(desc, 5000)
            out["_adapted"] = "youtube"

        elif p == "facebook":
            # Minimal — FB accepts long captions + linkifies URLs.
            tail = _hashtag_tail(hashtags, limit=10)
            new_cap = (caption + (("\n\n" + tail) if tail else "")).strip()
            out["caption"] = _truncate(new_cap, 63206)
            out["_adapted"] = "facebook"

        elif p == "whatsapp":
            # Owner 1-to-1 forward: short + clean. Strip URL if none present.
            tail = _hashtag_tail(hashtags, limit=5)
            new_cap = (caption + (("\n\n" + tail) if tail else "")).strip()
            out["caption"] = _truncate(new_cap, 4096)
            out["_adapted"] = "whatsapp"

        else:
            # Postiz / unknown = pass-through with mild truncation.
            out["caption"] = _truncate(caption, 5000)
            out["_adapted"] = p or "unknown"

        return out
    except Exception:
        return _copy(post)
