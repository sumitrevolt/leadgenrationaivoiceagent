"""Performance-learning data contract — recommendations only, never auto-mutate prompts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class CreativeLearningLink:
    """creative_revision → publish → platform metrics → leads → booking/revenue."""

    creative_id: str
    revision: int
    tenant_id: str
    publish_record_id: str = ""
    platform: str = ""
    metrics: dict[str, float] = field(default_factory=dict)
    lead_event_ids: list[str] = field(default_factory=list)
    booking_ids: list[str] = field(default_factory=list)
    revenue_inr: float | None = None
    source: str = "manual_import"  # postiz|social_api|manual_import
    verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def recommend(
    link: CreativeLearningLink, *, recipe_stats: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Produce non-mutating recommendations. Never silently changes production prompts."""
    recs: list[str] = []
    metrics = link.metrics or {}
    # Only recommend when metrics are verified — never fabricate
    if not link.verified or not metrics:
        return {
            "ok": True,
            "recommendations": [],
            "note": "no_verified_metrics",
            "auto_mutate_prompts": False,
            "auto_spend": False,
        }
    hook = metrics.get("avg_watch_s") or metrics.get("hook_retention")
    if hook is not None and hook < 2.0:
        recs.append("Increase hook length / strengthen first 2s")
    if metrics.get("ctr") is not None and metrics.get("ctr", 0) < 0.01:
        recs.append("Change CTA")
    if recipe_stats:
        best = recipe_stats.get("prefer_recipe")
        if best:
            recs.append(f"Prefer recipe: {best}")
        aspect = recipe_stats.get("prefer_aspect")
        if aspect:
            recs.append(f"Change aspect ratio to {aspect}")
        if recipe_stats.get("reuse_winning_structure"):
            recs.append("Reuse a verified winning structure")
    return {
        "ok": True,
        "recommendations": recs,
        "auto_mutate_prompts": False,
        "auto_spend": False,
        "link": link.to_dict(),
    }


__all__ = ["CreativeLearningLink", "recommend"]
