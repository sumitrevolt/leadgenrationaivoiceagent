"""Channel Experiment Engine — naye FREE+LEGAL customer-approach ways khud try,
measure aur scale karta (multi-armed bandit, epsilon-greedy).

PROBLEM: community/seo/partnership/linkedin drafters EXIST karte the par koi
system unhe regularly CHALATA nahi tha, na outcomes track karta tha, na seekhta
tha kaunsa channel kaam kar raha. Yeh engine roz kuch channels pick karta
(70% exploit best-performing, 30% explore naya), assets generate karta (sab
ban-safe drafts ya live SEO pages), aur outcome ratio se agli baar better pick.

Channels (sab free + legal, ToS-safe — auto-POST kahin nahi, sirf draft/own-site):
  seo_page (live niche×city landing) · quora · reddit · whatsapp_group ·
  linkedin_article · medium · partnership (CA/web-designer/IT pitch) · linkedin_dm

GATED `CHANNEL_EXPERIMENTS=1` (default OFF = run_daily no-op). Reuse only:
seo_pages, community_content, partnerships, linkedin_assist, growth_engine
best-niche. Store: data/channel_experiments.jsonl (runs) + channel_outcomes.jsonl.
Import-safe, kabhi raise nahi.
"""

from __future__ import annotations

import json
import os
import random
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_RUNS = os.path.join("data", "channel_experiments.jsonl")
_OUTCOMES = os.path.join("data", "channel_outcomes.jsonl")

EPSILON = 0.3  # explore probability
CHANNELS = [
    "seo_page",
    "quora",
    "reddit",
    "whatsapp_group",
    "linkedin_article",
    "medium",
    "partnership",
    "linkedin_dm",
    # naye customer-approach channels (social_channels.py — sab ban-safe drafts)
    "instagram_comment",
    "youtube_shorts",
    "gbp_qna",
    "whatsapp_status",
    "micro_influencer",
    "local_pr",
    "event_outreach",
    "listing_optimizer",
]

# social_channels.py se serve hone wale channels (draft via social draft fn)
_SOCIAL_V2 = {
    "instagram_comment",
    "youtube_shorts",
    "gbp_qna",
    "whatsapp_status",
    "micro_influencer",
    "local_pr",
    "event_outreach",
    "listing_optimizer",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _enabled() -> bool:
    return os.environ.get("CHANNEL_EXPERIMENTS", "0").strip().lower() in ("1", "true", "yes")


def _read(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return rows


def _append(path: str, rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def stats() -> dict[str, Any]:
    """Per-channel: assets launched, outcomes recorded, score (outcome/asset ratio,
    Laplace-smoothed taaki naya channel zero pe na mare). Kabhi raise nahi."""
    out: dict[str, dict[str, Any]] = {
        ch: {"assets": 0, "outcomes": 0, "score": 0.0} for ch in CHANNELS
    }
    try:
        for r in _read(_RUNS):
            ch = r.get("channel")
            if ch in out:
                out[ch]["assets"] += int(r.get("assets", 1) or 1)
        for r in _read(_OUTCOMES):
            ch = r.get("channel")
            if ch in out:
                out[ch]["outcomes"] += int(r.get("value", 1) or 1)
        for ch, d in out.items():
            d["score"] = round((d["outcomes"] + 1) / (d["assets"] + 2), 4)  # Laplace
    except Exception:
        pass
    return out


def pick_channels(n: int = 3, rng: random.Random | None = None) -> list[str]:
    """Epsilon-greedy: har slot 30% random explore / 70% best-score exploit
    (bina repeat). Pure function (rng inject = testable)."""
    rng = rng or random.Random()
    st = stats()
    ranked = sorted(CHANNELS, key=lambda c: st[c]["score"], reverse=True)
    picked: list[str] = []
    for _ in range(min(n, len(CHANNELS))):
        pool = [c for c in CHANNELS if c not in picked]
        if not pool:
            break
        if rng.random() < EPSILON:
            picked.append(rng.choice(pool))
        else:
            picked.append(next(c for c in ranked if c in pool))
    return picked


def _pick_niche_city() -> tuple[str, str]:
    """Best-performing niche (growth_engine learning) + rotating city."""
    niche = "general"
    try:
        from app.platform import growth_engine

        niche = str(growth_engine.latest_pulse().get("best_niche") or "") or "general"
    except Exception:
        pass
    if niche == "general":
        try:
            from app.niches import NICHES

            keys = list(NICHES.keys())
            niche = keys[_now().day % len(keys)] if keys else "general"
        except Exception:
            pass
    cities = ["Pune", "Mumbai", "Nagpur", "Nashik", "Thane", "Aurangabad", "Solapur"]
    try:
        env_c = [c.strip() for c in os.environ.get("PROSPECT_CITIES", "").split(",") if c.strip()]
        if env_c:
            cities = env_c
    except Exception:
        pass
    return niche, cities[_now().toordinal() % len(cities)]


async def _generate(channel: str, niche: str, city: str) -> dict[str, Any]:
    """Channel-specific asset generate (sab reuse, rebuild nahi). Draft = human
    1-click post; seo_page = LIVE page (own site, fully legal inbound)."""
    if channel == "seo_page":
        from app.marketing import seo_pages

        page = await seo_pages.generate_page(niche, city)
        # SEO page = LIVE own-site page → auto-record as outcome (fully legal/safe)
        if page and (page.get("url") or page.get("slug")):
            record_outcome("seo_page", value=1)
        return {
            "kind": "live_page",
            "assets": 1,
            "detail": str(page.get("url") or page.get("slug") or "")[:200],
        }
    if channel == "partnership":
        from app.marketing import partnerships

        res = await partnerships.draft_batch(city=city)
        drafts = res.get("drafts") or res.get("results") or []
        return {
            "kind": "draft",
            "assets": max(1, len(drafts)),
            "detail": f"{len(drafts)} partner pitches",
        }
    if channel == "linkedin_dm":
        from app.marketing import linkedin_assist

        res = await linkedin_assist.draft_outreach(f"{niche} owner", f"{niche} {city}", niche)
        return {"kind": "draft", "assets": 1, "detail": str(res.get("comment") or "")[:150]}
    if channel in _SOCIAL_V2:
        from app.marketing import social_channels

        res = await social_channels.draft(channel, niche=niche, city=city)
        return {"kind": "draft", "assets": 1, "detail": str(res.get("draft") or "")[:150]}
    # community platforms (quora/reddit/whatsapp_group/linkedin_article/medium)
    from app.marketing import community_content

    res = await community_content.draft_content(
        channel, topic=f"{niche} ko naye customer kaise milein ({city})", niche=niche
    )
    return {
        "kind": "draft",
        "assets": 1,
        "detail": str(res.get("draft") or res.get("content") or "")[:150],
    }


async def run_daily(n: int = 3) -> dict[str, Any]:
    """Roz ke channel experiments. GATED CHANNEL_EXPERIMENTS=1 — off = no-op."""
    if not _enabled():
        return {"enabled": False}
    launched: list[dict[str, Any]] = []
    try:
        niche, city = _pick_niche_city()
        for ch in pick_channels(n):
            try:
                asset = await _generate(ch, niche, city)
                rec = {
                    "id": uuid.uuid4().hex[:12],
                    "channel": ch,
                    "niche": niche,
                    "city": city,
                    **asset,
                    "at": _now().isoformat(),
                }
                _append(_RUNS, rec)
                launched.append(rec)
            except Exception as e:
                logger.debug(f"[experiments] {ch} skip: {e}")
        if launched:
            try:
                from app.platform import team

                team.log_event(
                    "isha",
                    "channel_experiments",
                    f"{len(launched)} experiments ({', '.join(r['channel'] for r in launched)}) — {niche}/{city}",
                )
            except Exception:
                pass
        return {"enabled": True, "launched": launched, "niche": niche, "city": city}
    except Exception as e:
        logger.warning(f"[experiments] run_daily failed: {e}")
        return {"enabled": True, "error": str(e)}


def record_outcome(
    channel: str, kind: str = "inquiry", value: int = 1, note: str = ""
) -> dict[str, Any]:
    """Outcome attribute karo (inquiry/reply/signup jo bhi channel se aaya) —
    bandit isi se seekhta. Kabhi raise nahi."""
    try:
        ch = (channel or "").strip().lower()
        if ch not in CHANNELS:
            return {"ok": False, "error": f"unknown channel (valid: {CHANNELS})"}
        _append(
            _OUTCOMES,
            {
                "channel": ch,
                "kind": (kind or "inquiry")[:30],
                "value": max(1, int(value)),
                "note": note[:200],
                "at": _now().isoformat(),
            },
        )
        # RL reward spine (Phase 0, logging-only) — INERT unless RL_ENGINE=1, never raises.
        try:
            from app.agents.rl import reward as _rl_reward

            _rl_reward.record_reward(
                "outreach",
                ch,
                _rl_reward.outreach_reward({"kind": kind}),
                ref=f"chexp:{ch}:{kind}:{_now().isoformat()}",
            )
        except Exception:
            pass
        return {"ok": True, "stats": stats()[ch]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def recent(limit: int = 30) -> list[dict[str, Any]]:
    rows = _read(_RUNS)
    return rows[-limit:][::-1]
