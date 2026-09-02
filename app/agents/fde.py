"""Forward Deployed Engineer (FDE) agents — 2026 agentic-workflow pattern.

FDE = ek agent jo CLIENT ke "environment" me ghus ke uske liye **automation +
marketing + website deploy karta** — multi-step, autonomously. (OpenAI/ServiceNow/
EY 2026 FDE model: client ke saath ja ke agentic workflow deploy karo.)

Yahan har "skill" = EXISTING platform capability ka wrapper (niche_pack,
post_generator, review_engine, embed_widget, journeys, content_schedule, …) —
**REBUILD NAHI**. Ek client-brief milne par FDE free-LLM se **deployment plan**
banata (kaunse skills, kis order), fir skills chalata aur report deta.

Ban-safe: skills content/setup DRAFT karte (auto-publish/auto-send nahi). Free-stack.
Import-safe, koi handler kabhi raise nahi karta (deploy report me ok/skip aata).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Awaitable, Callable

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

Ctx = dict[str, Any]


def _ctx_norm(ctx: Ctx) -> Ctx:
    """Client context fill (client_id ho to clients_store se enrich)."""
    c = dict(ctx or {})
    cid = c.get("client_id")
    if cid and not c.get("business_name"):
        try:
            from app.marketing import clients_store

            rec = clients_store.get_client(str(cid)) or {}
            c.setdefault("business_name", rec.get("business_name"))
            c.setdefault("niche", rec.get("niche"))
            c.setdefault("city", rec.get("city"))
            c.setdefault("slug", rec.get("slug"))
        except Exception:
            pass
    c["business_name"] = (c.get("business_name") or "Aapka Business").strip()
    c["niche"] = (c.get("niche") or "general").strip().lower()
    c["city"] = (c.get("city") or "").strip()
    return c


# --------------------------------------------------------------------------- #
# SKILL HANDLERS — har ek existing capability wrap karta (lazy import, defensive)
# --------------------------------------------------------------------------- #
async def _sk_marketing_pack(ctx: Ctx) -> dict[str, Any]:
    from app.marketing import niche_pack

    p = await niche_pack.build_pack(
        ctx["niche"], business_name=ctx["business_name"], city=ctx["city"], count=3
    )
    return {
        "ok": True,
        "summary": f"{len(p.get('posts', []))} themed posts + {len(p.get('hashtags', []))} hashtags + offer",
        "data": p,
    }


async def _sk_social_posts(ctx: Ctx) -> dict[str, Any]:
    from app.marketing.post_generator import generate_post

    posts = []
    for occ in ("offer post", "customer trust post"):
        p = await generate_post(ctx["business_name"], ctx["niche"], occasion=occ)
        posts.append(
            {
                "occasion": occ,
                "caption": p.get("caption") or p.get("post_text"),
                "hashtags": p.get("hashtags"),
            }
        )
    return {"ok": True, "summary": f"{len(posts)} ready social posts", "data": posts}


async def _sk_hashtags(ctx: Ctx) -> dict[str, Any]:
    from app.marketing import hashtags

    h = await hashtags.research(ctx["niche"], ctx["city"])
    tags = (h.get("hashtags") or h.get("tags") or []) if isinstance(h, dict) else (h or [])
    return {"ok": True, "summary": f"{len(tags)} trending hashtags + best-time", "data": h}


async def _sk_gbp_content(ctx: Ctx) -> dict[str, Any]:
    from app.marketing import gbp_text

    g = await gbp_text.gbp_texts(ctx["business_name"], ctx["niche"], ctx["city"])
    return {"ok": True, "summary": "Google Business Profile description + posts ready", "data": g}


async def _sk_festival_posts(ctx: Ctx) -> dict[str, Any]:
    from app.marketing import festivals

    up = festivals.upcoming(45)
    return {
        "ok": True,
        "summary": f"{len(up)} upcoming festivals queued for greeting posts",
        "data": up[:6],
    }


async def _sk_review_kit(ctx: Ctx) -> dict[str, Any]:
    from app.marketing import review_engine

    r = await review_engine.request_review(ctx["business_name"], place_query=ctx["business_name"])
    return {
        "ok": True,
        "summary": "Google review-request kit (WhatsApp msg + link)",
        "data": {"message": r.get("message"), "review_link": r.get("review_link")},
    }


async def _sk_competitor(ctx: Ctx) -> dict[str, Any]:
    from app.marketing import competitor

    c = await competitor.compare_tips(ctx["business_name"], ctx["niche"], "")
    return {"ok": True, "summary": "Competitor edge tips ready", "data": c}


async def _sk_minisite(ctx: Ctx) -> dict[str, Any]:
    slug = ctx.get("slug")
    if not slug:
        return {
            "ok": False,
            "summary": "client slug missing — pehle client onboard karo (auto mini-site)",
        }
    return {
        "ok": True,
        "summary": f"Mini-site live: /b/{slug} (booking + reviews + posts)",
        "data": {"url": f"/b/{slug}"},
    }


async def _sk_embed_widget(ctx: Ctx) -> dict[str, Any]:
    slug = ctx.get("slug")
    if not slug:
        return {"ok": False, "summary": "client slug missing for embed widget"}
    from app.marketing import embed_widget

    snip = embed_widget.snippet(slug)
    return {
        "ok": True,
        "summary": "Website lead-capture widget snippet ready (1-line embed)",
        "data": {"snippet": snip},
    }


async def _sk_drip_journey(ctx: Ctx) -> dict[str, Any]:
    from app.marketing import journeys

    rec = journeys.add_journey(
        f"{ctx['business_name']} — inquiry follow-up",
        "inquiry_received",
        [
            {"type": "draft_whatsapp", "params": {"topic": "naye inquiry ka turant follow-up"}},
            {"type": "draft_email", "params": {"topic": "thank-you + next step"}},
        ],
        condition={},
        enabled=False,
    )
    return {
        "ok": True,
        "summary": "Inquiry→WhatsApp+email drip rule created (disabled, review karke ON)",
        "data": {"journey_id": rec.get("id")},
    }


async def _sk_content_schedule(ctx: Ctx) -> dict[str, Any]:
    from app.marketing import content_schedule

    try:
        content_schedule.schedule(
            client_id=ctx.get("client_id") or "", topic=f"{ctx['niche']} weekly post", date=""
        )  # type: ignore
    except Exception:
        pass
    items = content_schedule.list_scheduled(limit=5)
    return {
        "ok": True,
        "summary": f"Content calendar set up ({len(items)} items queued)",
        "data": items[:5],
    }


async def _sk_niche_snapshot(ctx: Ctx) -> dict[str, Any]:
    """GHL-style niche template → client (mini-site, widget, journeys, festivals)."""
    from app.platform import client_snapshots

    cid = str(ctx.get("client_id") or "").strip()
    if not cid:
        cap = client_snapshots.capture_from_niche(ctx["niche"])
        return {
            "ok": cap.get("ok", False),
            "summary": (
                f"Niche template captured: {ctx['niche']}"
                if cap.get("ok")
                else cap.get("error", "fail")
            ),
            "data": cap,
        }
    res = client_snapshots.apply_niche_to_client(cid, ctx.get("niche"))
    return {
        "ok": res.get("ok", False),
        "summary": (
            f"Niche snapshot applied ({res.get('niche_key', ctx['niche'])})"
            if res.get("ok")
            else res.get("error", "apply fail")
        ),
        "data": res,
    }


# Skill registry: key -> {category, title, desc, handler}
SKILLS: dict[str, dict[str, Any]] = {
    # ---- marketing ----
    "marketing_pack": {
        "category": "marketing",
        "title": "Niche marketing pack",
        "handler": _sk_marketing_pack,
    },
    "social_posts": {"category": "marketing", "title": "Social posts", "handler": _sk_social_posts},
    "hashtags": {"category": "marketing", "title": "Trending hashtags", "handler": _sk_hashtags},
    "gbp_content": {
        "category": "marketing",
        "title": "Google Business Profile content",
        "handler": _sk_gbp_content,
    },
    "festival_posts": {
        "category": "marketing",
        "title": "Festival greeting posts",
        "handler": _sk_festival_posts,
    },
    "review_kit": {
        "category": "marketing",
        "title": "Review-generation kit",
        "handler": _sk_review_kit,
    },
    "competitor": {
        "category": "marketing",
        "title": "Competitor edge analysis",
        "handler": _sk_competitor,
    },
    # ---- website ----
    "minisite": {"category": "website", "title": "Mini-site (/b/slug)", "handler": _sk_minisite},
    "embed_widget": {
        "category": "website",
        "title": "Website lead-capture widget",
        "handler": _sk_embed_widget,
    },
    # ---- automation ----
    "drip_journey": {
        "category": "automation",
        "title": "Inquiry drip journey",
        "handler": _sk_drip_journey,
    },
    "content_schedule": {
        "category": "automation",
        "title": "Content calendar",
        "handler": _sk_content_schedule,
    },
    "niche_snapshot": {
        "category": "automation",
        "title": "Niche setup snapshot (GHL clone)",
        "handler": _sk_niche_snapshot,
    },
}

# FDE personas — har ek apni category(s) ke skills deploy karta.
FDE_AGENTS: dict[str, dict[str, Any]] = {
    "isha_fde": {"name": "Isha", "role": "Marketing FDE", "categories": ["marketing"]},
    "veer": {"name": "Veer", "role": "Website FDE", "categories": ["website"]},
    "aarav": {"name": "Aarav", "role": "Automation FDE", "categories": ["automation"]},
    "neo": {
        "name": "Neo",
        "role": "Full-stack FDE",
        "categories": ["automation", "marketing", "website"],
    },
}


def list_skills(category: str | None = None) -> list[dict[str, str]]:
    return [
        {"key": k, "category": v["category"], "title": v["title"]}
        for k, v in SKILLS.items()
        if not category or v["category"] == category
    ]


def list_agents() -> list[dict[str, Any]]:
    out = []
    for k, v in FDE_AGENTS.items():
        skills = [sk for sk, sv in SKILLS.items() if sv["category"] in v["categories"]]
        out.append(
            {
                "key": k,
                "name": v["name"],
                "role": v["role"],
                "categories": v["categories"],
                "skills": skills,
            }
        )
    return out


def _agent_skill_keys(agent_key: str) -> list[str]:
    cats = (FDE_AGENTS.get(agent_key) or FDE_AGENTS["neo"])["categories"]
    return [k for k, v in SKILLS.items() if v["category"] in cats]


async def plan_deployment(brief: str, skill_keys: list[str]) -> list[str]:
    """free-LLM se ordered skill subset chuno (brief ke hisaab se). Fail -> sab skills."""
    if not brief.strip():
        return skill_keys
    try:
        from app.voice_agent import free_ai

        catalog = ", ".join(skill_keys)
        sys = (
            "Tum ek Forward Deployed Engineer ho. Available skills: " + catalog + ". "
            "User ke brief ke hisaab se SIRF ek JSON array lautao relevant skill-keys ka, "
            'priority order me, e.g. ["marketing_pack","review_kit"]. Sirf JSON array, aur kuch nahi.'
        )
        raw, _ = await free_ai.chat(
            sys, [{"role": "user", "content": brief}], max_tokens=120, temperature=0.1
        )
        i, j = raw.find("["), raw.rfind("]")
        if i != -1 and j != -1:
            picked = json.loads(raw[i : j + 1])
            picked = [p for p in picked if p in skill_keys]
            if picked:
                return picked
    except Exception as e:
        logger.debug(f"[fde] plan skip: {e}")
    return skill_keys


async def deploy(
    ctx: Ctx,
    agent: str = "neo",
    brief: str = "",
    skills: list[str] | None = None,
    max_steps: int = 8,
) -> dict[str, Any]:
    """FDE deployment: client ke liye plan banao + skills execute karo + report do.

    ctx: {business_name, niche, city, slug?, client_id?}. Kabhi raise nahi karta.
    """
    c = _ctx_norm(ctx)
    agent_key = agent if agent in FDE_AGENTS else "neo"
    candidate = skills if skills else _agent_skill_keys(agent_key)
    candidate = [k for k in candidate if k in SKILLS]
    plan = await plan_deployment(brief, candidate)
    plan = plan[: max(1, min(max_steps, len(plan)))]

    steps: list[dict[str, Any]] = []
    for key in plan:
        sk = SKILLS.get(key)
        if not sk:
            continue
        try:
            res = await sk["handler"](c)
        except Exception as e:  # noqa: BLE001
            res = {"ok": False, "summary": f"skip ({str(e)[:80]})"}
        steps.append({"skill": key, "title": sk["title"], "category": sk["category"], **res})

    ok_n = sum(1 for s in steps if s.get("ok"))
    report = {
        "ok": True,
        "id": uuid.uuid4().hex[:12],
        "at": datetime.now().isoformat(),
        "status": "pending",
        "agent": FDE_AGENTS[agent_key]["name"],
        "role": FDE_AGENTS[agent_key]["role"],
        "client": {"business_name": c["business_name"], "niche": c["niche"], "city": c["city"]},
        "deployed": ok_n,
        "total": len(steps),
        "steps": steps,
    }
    # Additive persistence sink so the deploy report can surface in the unified
    # approval cockpit (approvals_bridge). Best-effort; never blocks the return.
    try:
        os.makedirs("data", exist_ok=True)
        with open(os.path.join("data", "fde_deploys.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(report, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return report


__all__ = ["SKILLS", "FDE_AGENTS", "list_skills", "list_agents", "plan_deployment", "deploy"]
