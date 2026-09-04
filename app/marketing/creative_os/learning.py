"""Performance-learning data contract — recommendations, recipe learning, and KB feedback loop.

Learns from verified post-publish metrics (watch time, hook retention, CTR, leads)
to optimize future video recipe selection and scene hook pacing.
"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_LOCK = threading.Lock()
_DEFAULT_DIR = os.path.join("data", "creative_os", "learning")


@dataclass
class CreativeLearningLink:
    """creative_revision → publish → platform metrics → leads → booking/revenue."""

    creative_id: str
    revision: int
    tenant_id: str
    publish_record_id: str = ""
    platform: str = ""
    recipe: str = ""
    metrics: dict[str, float] = field(default_factory=dict)
    lead_event_ids: list[str] = field(default_factory=list)
    booking_ids: list[str] = field(default_factory=list)
    revenue_inr: float | None = None
    source: str = "manual_import"  # postiz|social_api|manual_import
    verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CreativeLearningLink:
        valid_keys = {
            "creative_id",
            "revision",
            "tenant_id",
            "publish_record_id",
            "platform",
            "recipe",
            "metrics",
            "lead_event_ids",
            "booking_ids",
            "revenue_inr",
            "source",
            "verified",
        }
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


_MEM_STORE: dict[str, list[dict[str, Any]]] = {}


def record_learning(link: CreativeLearningLink) -> dict[str, Any]:
    """Persist a verified or imported learning link to the tenant's append-only ledger."""
    try:
        tid = str(link.tenant_id or "default")
        payload = link.to_dict()
        with _LOCK:
            _MEM_STORE.setdefault(tid, []).append(payload)
        return {"ok": True, "creative_id": link.creative_id, "tenant_id": link.tenant_id}
    except Exception as exc:
        logger.warning("[creative_learning] record_learning failed: %s", exc)
        return {"ok": False, "error": str(exc)[:160]}


def get_learning_history(tenant_id: str, limit: int = 100) -> list[CreativeLearningLink]:
    """Retrieve historical learning records for this tenant."""
    tid = str(tenant_id or "default")
    with _LOCK:
        raw = list(_MEM_STORE.get(tid, []))
    records: list[CreativeLearningLink] = []
    for data in raw[-limit:]:
        try:
            records.append(CreativeLearningLink.from_dict(data))
        except Exception:
            continue
    return records


def get_tenant_recipe_stats(tenant_id: str) -> dict[str, Any]:
    """Aggregate performance metrics across recipes for this tenant."""
    history = get_learning_history(tenant_id)
    if not history:
        return {
            "ok": True,
            "tenant_id": tenant_id,
            "sample_count": 0,
            "prefer_recipe": "",
            "prefer_aspect": "9:16",
            "avg_watch_s": 0.0,
            "hook_improvement_needed": False,
            "recipes": {},
        }

    from app.marketing.creative_os.store import get_record

    recipe_aggregates: dict[str, dict[str, Any]] = {}
    all_watches: list[float] = []

    for item in history:
        if not item.verified:
            continue
        m = item.metrics or {}
        watch = m.get("avg_watch_s") or m.get("hook_retention") or 0.0
        ctr = m.get("ctr") or 0.0
        leads = len(item.lead_event_ids)

        rec_name = item.recipe
        if not rec_name:
            rec = get_record(item.tenant_id, item.creative_id)
            if rec.get("ok"):
                rec_name = str((rec.get("record") or {}).get("recipe") or "")

        rec_name = rec_name or "offer_announcement"

        if rec_name not in recipe_aggregates:
            recipe_aggregates[rec_name] = {
                "count": 0,
                "total_watch_s": 0.0,
                "total_ctr": 0.0,
                "total_leads": 0,
            }

        stats = recipe_aggregates[rec_name]
        stats["count"] += 1
        stats["total_watch_s"] += float(watch)
        stats["total_ctr"] += float(ctr)
        stats["total_leads"] += leads

        if watch > 0:
            all_watches.append(watch)

    best_recipe = ""
    best_score = -1.0
    computed_recipes: dict[str, Any] = {}

    for r_name, agg in recipe_aggregates.items():
        cnt = agg["count"] or 1
        avg_watch = agg["total_watch_s"] / cnt
        avg_ctr = agg["total_ctr"] / cnt
        # Composite score: watch time + CTR + leads
        score = (avg_watch * 1.5) + (avg_ctr * 100.0) + (agg["total_leads"] * 2.0)
        computed_recipes[r_name] = {
            "count": cnt,
            "avg_watch_s": round(avg_watch, 2),
            "avg_ctr": round(avg_ctr, 4),
            "total_leads": agg["total_leads"],
            "score": round(score, 2),
        }
        if score > best_score:
            best_score = score
            best_recipe = r_name

    overall_avg_watch = sum(all_watches) / len(all_watches) if all_watches else 0.0
    hook_needed = overall_avg_watch > 0 and overall_avg_watch < 2.5

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "sample_count": len(history),
        "prefer_recipe": best_recipe,
        "prefer_aspect": "9:16",
        "avg_watch_s": round(overall_avg_watch, 2),
        "hook_improvement_needed": hook_needed,
        "recipes": computed_recipes,
    }


def suggest_next_creative_strategy(tenant_id: str) -> dict[str, Any]:
    """Actionable recommendation for the next video run based on verified learnings."""
    stats = get_tenant_recipe_stats(tenant_id)
    pref_recipe = stats.get("prefer_recipe") or "offer_announcement"
    hook_needed = bool(stats.get("hook_improvement_needed"))

    recommendations: list[str] = []
    if pref_recipe:
        recommendations.append(f"Prefer recipe: {pref_recipe} (highest verified performance)")
    if hook_needed:
        recommendations.append("Strengthen first 2s hook with immediate visual benefit/question")

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "prefer_recipe": pref_recipe,
        "prefer_aspect": "9:16",
        "hook_improvement_needed": hook_needed,
        "recommendations": recommendations,
        "sample_count": stats.get("sample_count", 0),
    }


def sync_creative_learning_to_kb(
    tenant_id: str, insight: str, source: str = "creative_learning"
) -> bool:
    """Store a high-converting creative learning chunk into Qdrant/KB client namespace."""
    text = str(insight or "").strip()
    if not text:
        return False
    try:
        from app.voice_agent.knowledge_base import get_knowledge_base

        kb = get_knowledge_base()
        kb.add_documents(
            [text],
            source=source,
            namespace=f"client:{tenant_id}",
        )
        logger.info(
            "[creative_learning] Synced learning chunk to KB (namespace=client:%s)", tenant_id
        )
        return True
    except Exception as exc:
        logger.debug("[creative_learning] sync_creative_learning_to_kb skip: %s", exc)
        return False


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


__all__ = [
    "CreativeLearningLink",
    "get_learning_history",
    "get_tenant_recipe_stats",
    "recommend",
    "record_learning",
    "suggest_next_creative_strategy",
    "sync_creative_learning_to_kb",
]
