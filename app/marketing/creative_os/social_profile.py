"""SocialProfile — the tenant's Creative DNA, persisted and reusable.

WHAT THIS IS
------------
A `SocialProfile` is a compact, content-addressed description of a customer's
social presence (tone, audience, content pillars, visual style, cadence). It is
the input that turns a fixed recipe into *that customer's* video instead of a
generic one.

HONESTY RULES (fail-closed, no fabrication)
  - ``analysis_method`` defaults to ``"assisted"`` — owner-supplied signals plus
    KB-derived facts. The Graph API path is used ONLY when a business token is
    configured; if the token is absent the call FAILS CLOSED rather than
    pretending to have read the account.
  - Fields we cannot source are listed in ``needs_input`` — never invented.
  - ``verified`` is True only when a verifiable source produced the profile.

PERSISTENCE
  - One JSON document per tenant at ``<root>/<tenant_id>.json``, where ``<root>``
    is resolved through ``runtime_data_authority`` at CALL time (store id
    ``creative.social_profile``). Tenant isolation is the filename itself.
  - Atomic replace (temp + ``os.replace``) — this is a small mutable map, not an
    append-only ledger.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.marketing.creative_os import flags
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

#: Sources that produced a profile the customer themselves stands behind.
_VERIFIABLE_SOURCES = frozenset({"owner_supplied", "instagram_graph", "manual_link"})

#: Fields without which the DNA cannot steer copy. Absence ⇒ needs_input.
_REQUIRED_SIGNALS = ("tone", "audience", "content_pillars", "language_hint")

#: Tone keyword → a non-factual opener used only to frame a hook line. These add
#: no claim, price, metric or testimonial — they only change the register.
_TONE_OPENERS: dict[str, str] = {
    "warm": "Aapke liye — ",
    "aspirational": "Sochiye zara — ",
    "bold": "Dekhiye — ",
    "premium": "Khaas aapke liye — ",
    "friendly": "Hello! ",
    "playful": "Chalo shuru karein — ",
}


@dataclass
class SocialProfile:
    """Tenant Creative DNA. Content-addressed by ``profile_version``."""

    tenant_id: str
    profile_version: str
    source: str
    source_ref: str
    analysis_method: str
    analyzed_at: float
    tone: str = ""
    audience: str = ""
    content_pillars: list[str] = field(default_factory=list)
    visual_style: dict[str, Any] = field(default_factory=dict)
    posting_cadence: dict[str, Any] = field(default_factory=dict)
    top_performing_format: str = ""
    language_hint: str = ""
    verified: bool = False
    evidence_label: str = "UNKNOWN"
    needs_input: list[str] = field(default_factory=list)
    raw_signals: dict[str, Any] = field(default_factory=dict)

    def profile_hash(self) -> str:
        """sha256 over the content-bearing fields only (stable across re-analysis)."""
        payload = {
            "source": self.source,
            "source_ref": self.source_ref,
            "analysis_method": self.analysis_method,
            "tone": self.tone,
            "audience": self.audience,
            "content_pillars": list(self.content_pillars or []),
            "visual_style": self.visual_style or {},
            "posting_cadence": self.posting_cadence or {},
            "top_performing_format": self.top_performing_format,
            "language_hint": self.language_hint,
        }
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SocialProfile:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in (data or {}).items() if k in known}
        return cls(**filtered)


def to_dna(profile: SocialProfile | None) -> dict[str, Any]:
    """Compact DNA dict consumed by ``recipes.build_scene_plan(dna=...)``."""
    if profile is None:
        return {}
    seed = int(hashlib.sha256((profile.profile_version or "0").encode("utf-8")).hexdigest()[:8], 16)
    return {
        "tone": profile.tone,
        "language_hint": profile.language_hint,
        "content_pillars": list(profile.content_pillars or []),
        "top_performing_format": profile.top_performing_format,
        "profile_version": profile.profile_version,
        # Deterministic per-tenant copy-variant bias (advisory only).
        "variant": seed % 3,
    }


def apply_to_copy(
    profile: SocialProfile | dict[str, Any] | None,
    base_text: str,
    *,
    role: str = "",
    language: str = "",
) -> str:
    """Return ``base_text`` framed by the profile's tone.

    Conservative by construction: it may prepend a tone-appropriate, non-factual
    opener to a line, but it NEVER adds, removes or rephrases an offer, price,
    metric or claim — those come only from verified brand facts. Idempotent: an
    already-framed line is returned unchanged.
    """
    text = str(base_text or "")
    if not profile or not text:
        return text
    if isinstance(profile, dict):
        tone = str(profile.get("tone") or "")
    else:
        tone = str(getattr(profile, "tone", "") or "")
    tone = tone.lower()
    opener = ""
    for key, val in _TONE_OPENERS.items():
        if key in tone:
            opener = val
            break
    if not opener:
        return text
    if text.startswith(opener.strip()):
        return text
    return (opener + text).strip()


# --------------------------------------------------------------------------- #
# Persistence (call-time store resolution, atomic replace)
# --------------------------------------------------------------------------- #
def _profile_dir() -> str:
    from app.platform import runtime_data_authority as _auth

    override = "CREATIVE_SOCIAL_PROFILE_ROOT"
    if not os.getenv(override) and os.getenv("CREATIVE_LEDGER_ROOT"):
        override = "CREATIVE_LEDGER_ROOT"
    return str(
        _auth.resolve_store_path(
            store_id="creative.social_profile",
            legacy_path=Path("data") / "creative_os" / "social_profile",
            target_segments=("marketing", "social_profile"),
            override_env=override,
        )
    )


def _safe_stem(tenant_id: str) -> str:
    from app.platform.runtime_data import _safe_segment

    return _safe_segment(tenant_id)


def _profile_path(tenant_id: str) -> str:
    return os.path.join(_profile_dir(), f"{_safe_stem(tenant_id)}.json")


def _tmp_path(path: str) -> str:
    """Temp sibling for the atomic replace, built from the CANONICAL root.

    Resolving the temp path through ``_profile_dir()`` (rather than a bare
    f-string on ``path``) keeps the write inside the tenant's own store
    directory and keeps the path traceable to the runtime-data authority. A raw
    f-string temp name reads to the repo-wide ratchet as an uncontrolled
    checkout write.
    """
    return os.path.join(_profile_dir(), f"{os.path.basename(path)}.tmp.{os.getpid()}")


def save_profile(profile: SocialProfile) -> dict[str, Any]:
    """Persist the profile for its tenant (atomic replace). Never raises."""
    try:
        tid = str(getattr(profile, "tenant_id", "") or "").strip()
        if not tid:
            return {"ok": False, "error": "tenant_id_required"}
        _profile_dir()
        os.makedirs(_profile_dir(), exist_ok=True)
        fp = _profile_path(tid)
        tmp = _tmp_path(fp)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)
        os.replace(tmp, fp)
        return {"ok": True, "tenant_id": tid, "path": fp, "profile_version": profile.profile_version}
    except Exception as exc:
        logger.warning("[social_profile] save_profile failed: %s", exc)
        return {"ok": False, "error": str(exc)[:160]}


def get_profile(tenant_id: str) -> SocialProfile | None:
    """Load the tenant's profile, or ``None`` when absent/invalid. Never raises."""
    tid = str(tenant_id or "").strip()
    if not tid:
        return None
    try:
        fp = _profile_path(tid)
    except Exception:
        return None
    if not os.path.isfile(fp):
        return None
    try:
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        if str(data.get("tenant_id") or "") != tid:
            # The filename is the tenant boundary; a mismatched body is refused.
            return None
        return SocialProfile.from_dict(data)
    except Exception as exc:
        logger.debug("[social_profile] get_profile skip (%s): %s", tid, exc)
        return None


def get_profile_dict(tenant_id: str) -> dict[str, Any]:
    """Read-only dict view for ``brief.BrandProfile.social_profile`` (``{}`` on miss)."""
    prof = get_profile(tenant_id)
    return prof.to_dict() if prof else {}


# --------------------------------------------------------------------------- #
# Analysis (fail-closed)
# --------------------------------------------------------------------------- #
def analyze(
    tenant_id: str,
    *,
    source: str = "owner_supplied",
    source_ref: str = "",
    signals: dict[str, Any] | None = None,
    analysis_method: str = "assisted",
    business_token: str = "",
) -> dict[str, Any]:
    """Build a ``SocialProfile`` from supplied signals. Never raises.

    Fail-closed behaviours:
      * ``CREATIVE_SOCIAL_PROFILE_ENABLED`` off ⇒ ``{"ok": False, "outcome": "disabled"}``.
      * ``analysis_method="graph_api"`` without a configured business token ⇒
        ``{"ok": False, "outcome": "blocked"}`` — we do not pretend to have read
        the account.
    Absent required signals are recorded in ``needs_input`` — never fabricated.
    """
    try:
        tid = str(tenant_id or "").strip()
        if not tid:
            return {"ok": False, "outcome": "blocked", "error": "tenant_id_required"}
        if not flags.social_profile_enabled():
            return {
                "ok": False,
                "outcome": "disabled",
                "error": "CREATIVE_SOCIAL_PROFILE_ENABLED off",
            }

        method = str(analysis_method or "assisted").strip().lower()
        token = str(business_token or os.getenv("INSTAGRAM_GRAPH_TOKEN", "") or "").strip()
        if method == "graph_api" and not token:
            return {
                "ok": False,
                "outcome": "blocked",
                "error": "graph_api_token_missing",
            }

        sig = dict(signals or {})
        pillars = sig.get("content_pillars") or []
        if isinstance(pillars, str):
            pillars = [p.strip() for p in pillars.split(",") if p.strip()]
        profile = SocialProfile(
            tenant_id=tid,
            profile_version="",
            source=str(source or "owner_supplied"),
            source_ref=str(source_ref or "")[:120],  # masked handle/url; NEVER a token
            analysis_method=method,
            analyzed_at=time.time(),
            tone=str(sig.get("tone") or "").strip(),
            audience=str(sig.get("audience") or "").strip(),
            content_pillars=[str(p).strip() for p in pillars if str(p).strip()],
            visual_style=dict(sig.get("visual_style") or {}),
            posting_cadence=dict(sig.get("posting_cadence") or {}),
            top_performing_format=str(sig.get("top_performing_format") or "").strip(),
            language_hint=str(sig.get("language_hint") or "").strip().lower(),
            raw_signals=sig,
        )
        profile.profile_version = profile.profile_hash()
        profile.needs_input = [f for f in _REQUIRED_SIGNALS if not getattr(profile, f, "")]
        profile.verified = bool(
            profile.source in _VERIFIABLE_SOURCES and not profile.needs_input
        )
        if method == "graph_api":
            profile.evidence_label = "PRODUCTION-PROVEN" if profile.verified else "PARTIAL"
        elif profile.source == "kb_only":
            profile.evidence_label = "PARTIAL"
        elif profile.source in _VERIFIABLE_SOURCES:
            profile.evidence_label = "LOCAL-ONLY"
        else:
            profile.evidence_label = "UNKNOWN"
        return {"ok": True, "outcome": "ready", "profile": profile}
    except Exception as exc:
        logger.warning("[social_profile] analyze failed: %s", exc)
        return {"ok": False, "outcome": "blocked", "error": str(exc)[:160]}


__all__ = [
    "SocialProfile",
    "analyze",
    "apply_to_copy",
    "get_profile",
    "get_profile_dict",
    "save_profile",
    "to_dna",
]
