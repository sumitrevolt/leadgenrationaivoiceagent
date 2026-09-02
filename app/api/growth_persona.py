from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.utils.logger import setup_logger
from app.voice_agent.free_ai import chat

logger = setup_logger(__name__)
router = APIRouter(tags=["Growth"])


class PersonaRequest(BaseModel):
    niche: str
    product_description: str


@router.post("/persona/architect")
async def build_persona(req: PersonaRequest, _user=Depends(require_admin)):
    """Auto-generate an Ideal Customer Profile (ICP) and Cold Outreach frameworks using free LLM chain."""
    system = "You are an expert B2B Marketing Architect specializing in local businesses."
    prompt = f"Product: {req.product_description}\nTarget Niche: {req.niche}\n\n"
    prompt += "Output strictly in JSON format with exactly these keys:\n"
    prompt += "- target_roles (list of strings)\n"
    prompt += "- pain_points (list of strings)\n"
    prompt += "- value_prop (string)\n"
    prompt += (
        "- cold_email_architect (dict with 'subject_lines' (list) and 'body_frameworks' (list))\n"
    )

    try:
        reply_text, provider = await chat(
            system=system, messages=[{"role": "user", "content": prompt}], temperature=0.7
        )
        if not reply_text:
            raise HTTPException(status_code=500, detail="Failed to generate persona via AI.")

        # Clean markdown code block if present
        cleaned = reply_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]

        data = json.loads(cleaned.strip())
        return {"success": True, "provider": provider, "data": data}
    except json.JSONDecodeError as e:
        logger.error(f"Persona JSON parse error: {e}. Raw: {reply_text}")
        raise HTTPException(status_code=500, detail="AI returned invalid formatting. Try again.")
    except Exception as e:
        logger.error(f"Persona generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
