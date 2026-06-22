"""ICP generator — per-client ideal customer profile from niche + KB + free_ai."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_DIR = os.path.join("data", "icp")


def _icp_path(client_id: str) -> str:
    safe = "".join(c for c in client_id if c.isalnum() or c in "-_")[:40]
    return os.path.join(_DIR, f"{safe or 'global'}.json")


async def generate(
    *,
    client_id: str = "",
    business_name: str = "",
    niche: str = "general",
    city: str = "",
    brief: str = "",
) -> dict[str, Any]:
    """Generate ICP JSON for prospector targeting. Never raises."""
    os.makedirs(_DIR, exist_ok=True)
    niche_data: dict[str, Any] = {}
    try:
        from app.niches import NICHES

        niche_data = dict(NICHES.get(niche, {}) or {})
    except Exception:
        pass
    sys_prompt = (
        "You are an ICP (Ideal Customer Profile) agent for Indian local SMB lead gen.\n"
        "Return ONLY valid JSON with keys: title, industries, company_size, "
        "geography, pain_points (array), buying_signals (array), "
        "disqualifiers (array), prospect_keywords (array), pitch_angle (string).\n"
        "Hinglish OK in string values. Be specific to niche and city."
    )
    user = (
        f"Business: {business_name}\nNiche: {niche}\nCity: {city}\n"
        f"Brief: {brief}\nNiche metadata: {json.dumps(niche_data, ensure_ascii=False)[:1200]}"
    )
    icp: dict[str, Any] = {
        "id": uuid.uuid4().hex[:12],
        "client_id": client_id,
        "niche": niche,
        "city": city,
        "business_name": business_name,
    }
    try:
        from app.voice_agent import free_ai

        reply, _ = await free_ai.chat(
            sys_prompt,
            [{"role": "user", "content": user}],
            max_tokens=700,
            temperature=0.35,
        )
        raw = (reply or "").strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = json.loads(raw[start:end])
            if isinstance(parsed, dict):
                icp.update(parsed)
    except Exception as e:
        icp["fallback"] = True
        icp["pain_points"] = niche_data.get("content_focus") or ["local visibility", "leads"]
        icp["prospect_keywords"] = niche_data.get("keywords") or [niche, city]
        icp["pitch_angle"] = niche_data.get("pitch_hook") or f"{niche} businesses in {city}"
        icp["error"] = str(e)[:120]
    try:
        with open(_icp_path(client_id), "w", encoding="utf-8") as f:
            json.dump(icp, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    try:
        from app.platform.team import log_event

        log_event(
            "kiran",
            "icp_generated",
            f"ICP {niche}/{city} for {business_name or client_id or 'global'}",
            meta={"client_id": client_id, "niche": niche},
            status="ok",
        )
    except Exception:
        pass
    return {"ok": True, "icp": icp}


def get(client_id: str = "") -> dict[str, Any]:
    try:
        with open(_icp_path(client_id), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


__all__ = ["generate", "get"]
