"""Typed, versioned CreativeSpec — serializable, deterministic, queue-safe."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

SPEC_VERSION = "1.0"

_ALLOWED_PLATFORMS = frozenset(
    {"instagram", "facebook", "youtube", "whatsapp", "linkedin", "tiktok", "generic"}
)
_ALLOWED_ASPECTS = frozenset({"9:16", "1:1", "16:9", "4:5"})
_ALLOWED_LANGS = frozenset({"hinglish", "hi", "en", "gu", "mr", "ta", "te", "bn"})
_ALLOWED_PROVIDERS = frozenset(
    {"deterministic", "hyperframes", "qwen_image", "flux_schnell", "wan22", "comfyui"}
)
_TENANT_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{1,58}[a-z0-9]$", re.I)
_PLACEHOLDER_RE = re.compile(
    r"\{\{|\[\s*(insert|todo|tbd|placeholder|xxx)\s*\]|lorem ipsum|test_tenant",
    re.I,
)


@dataclass
class SceneSpec:
    index: int
    role: str
    text: str
    duration_s: float = 4.0
    asset_ids: list[str] = field(default_factory=list)

    def validate(self) -> list[str]:
        errs: list[str] = []
        if self.index < 0:
            errs.append("scene.index negative")
        if not (self.text or "").strip():
            errs.append(f"scene[{self.index}].text empty")
        if _PLACEHOLDER_RE.search(self.text or ""):
            errs.append(f"scene[{self.index}].text has placeholder")
        if self.duration_s <= 0 or self.duration_s > 30:
            errs.append(f"scene[{self.index}].duration_s out of bounds")
        return errs


@dataclass
class CreativeSpec:
    """Versioned creative brief — worker-queue safe (JSON serializable)."""

    creative_id: str
    tenant_id: str
    goal: str
    audience: str
    offer: str
    language: str
    platform: str
    aspect_ratio: str
    recipe: str
    brand_revision: str = "v1"
    source_asset_ids: list[str] = field(default_factory=list)
    script: str = ""
    scenes: list[SceneSpec] = field(default_factory=list)
    captions: dict[str, str] = field(default_factory=dict)
    cta: str = ""
    claims: list[str] = field(default_factory=list)
    provider: str = "deterministic"
    # Optional render-template selector. Empty = the provider's configured
    # default. Additive with a default so existing stored records keep loading
    # unchanged; validated against the provider's exact allowlist, never used
    # as a path.
    template_id: str = ""
    model_name: str = "ffmpeg-template"
    model_version: str = "pinned"
    seed: int = 0
    prompt_version: str = "1"
    input_hashes: dict[str, str] = field(default_factory=dict)
    output_hash: str = ""
    output_asset_id: str = ""
    job_id: str = ""
    fallback_from: str = ""
    provider_warnings: list[str] = field(default_factory=list)
    licence_snapshot: dict[str, Any] = field(default_factory=dict)
    qa_results: dict[str, Any] = field(default_factory=dict)
    approval_revision: int = 0
    publish_targets: list[str] = field(default_factory=list)
    status: str = "queued"
    failure_reason: str = ""
    render_duration_ms: int = 0
    change_note: str = ""
    previous_output_hash: str = ""
    spec_version: str = SPEC_VERSION

    @staticmethod
    def new_id() -> str:
        return f"cr_{uuid.uuid4().hex[:12]}"

    def validate(self) -> list[str]:
        errs: list[str] = []
        if not self.creative_id:
            errs.append("creative_id required")
        if not self.tenant_id or not _TENANT_RE.match(self.tenant_id):
            errs.append("tenant_id invalid")
        if not (self.goal or "").strip():
            errs.append("goal required")
        if self.language not in _ALLOWED_LANGS:
            errs.append(f"language not allowed: {self.language}")
        if self.platform not in _ALLOWED_PLATFORMS:
            errs.append(f"platform not allowed: {self.platform}")
        if self.aspect_ratio not in _ALLOWED_ASPECTS:
            errs.append(f"aspect_ratio not allowed: {self.aspect_ratio}")
        if self.provider not in _ALLOWED_PROVIDERS:
            errs.append(f"provider not allowed: {self.provider}")
        if not (self.recipe or "").strip():
            errs.append("recipe required")
        for claim in self.claims:
            if _PLACEHOLDER_RE.search(claim or ""):
                errs.append("claim contains unresolved placeholder")
            if re.search(r"\b(guaranteed|100%\s*results?|#1\s*in\s*india)\b", claim or "", re.I):
                errs.append("claim uses prohibited absolute marketing language")
        for sc in self.scenes:
            errs.extend(sc.validate())
        for key, val in (self.captions or {}).items():
            if _PLACEHOLDER_RE.search(val or ""):
                errs.append(f"caption[{key}] has placeholder")
        if self.cta and _PLACEHOLDER_RE.search(self.cta):
            errs.append("cta has placeholder")
        return errs

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CreativeSpec:
        raw = dict(data or {})
        scenes_in = raw.pop("scenes", []) or []
        scenes = [SceneSpec(**s) if isinstance(s, dict) else s for s in scenes_in]
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in raw.items() if k in known}
        return cls(scenes=scenes, **filtered)

    def canonical_json(self) -> str:
        """Deterministic JSON for hashing (excludes volatile workflow/QA fields)."""
        d = self.to_dict()
        for drop in (
            "qa_results",
            "render_duration_ms",
            "failure_reason",
            "output_hash",
            "status",  # workflow state must not invalidate content hashes
        ):
            d.pop(drop, None)
        return json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    def spec_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def caption_hash(self) -> str:
        payload = json.dumps(self.captions or {}, sort_keys=True, ensure_ascii=False)
        payload += "|" + (self.cta or "")
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def channel_hash(self) -> str:
        targets = sorted(str(t).lower() for t in (self.publish_targets or []))
        return hashlib.sha256("|".join(targets).encode("utf-8")).hexdigest()

    def compute_input_hashes(self) -> dict[str, str]:
        slides = "|".join(s.text for s in self.scenes)
        base = {
            "goal": _h(self.goal),
            "offer": _h(self.offer),
            "script": _h(self.script),
            "scenes": _h(slides),
            "brand_revision": _h(self.brand_revision),
            "source_assets": _h("|".join(sorted(self.source_asset_ids or []))),
        }
        self.input_hashes = base
        return base


def _h(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()[:16]


def validate_customer_fields(
    *,
    tenant_id: str,
    goal: str,
    offer: str = "",
    language: str = "hinglish",
    platform: str = "instagram",
    aspect_ratio: str = "9:16",
    cta: str = "",
    claims: list[str] | None = None,
) -> list[str]:
    """Validate customer-controlled fields before constructing a full spec."""
    probe = CreativeSpec(
        creative_id="cr_probe",
        tenant_id=tenant_id,
        goal=goal,
        audience="",
        offer=offer or "",
        language=language,
        platform=platform,
        aspect_ratio=aspect_ratio,
        recipe="offer_announcement",
        cta=cta or "",
        claims=list(claims or []),
    )
    return [e for e in probe.validate() if not e.startswith("scene")]


__all__ = [
    "CreativeSpec",
    "SPEC_VERSION",
    "SceneSpec",
    "validate_customer_fields",
]
