from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.utils.logger import setup_logger
from app.voice_agent.free_ai import chat

logger = setup_logger(__name__)
router = APIRouter(tags=["Growth"])


class TriageRequest(BaseModel):
    message_body: str
    channel: str = "email"


@router.post("/triage/classify")
async def classify_inbound(req: TriageRequest, _user=Depends(require_admin)):
    """Auto-classify inbound emails/messages using free LLM to prevent Inbox noise."""
    system = "You are an AI Triage Assistant for a B2B Marketing Agency."
    prompt = f"Channel: {req.channel}\nMessage:\n{req.message_body}\n\n"
    prompt += "Classify this inbound lead reply into exactly one of these CATEGORY strings: 'INTERESTED', 'DND_UNSUBSCRIBE', 'NOT_INTERESTED', 'QUESTION_NEEDS_HUMAN'.\n"
    prompt += "Also extract 'reason' (string) and 'suggested_action' (string). Output purely as JSON with keys 'category', 'reason', and 'suggested_action'. No markdown blocks."

    try:
        reply_text, provider = await chat(
            system=system, messages=[{"role": "user", "content": prompt}], temperature=0.1
        )
        if not reply_text:
            raise HTTPException(status_code=500, detail="Failed to triage message.")

        cleaned = reply_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]

        data = json.loads(cleaned.strip())

        valid_categories = {
            "INTERESTED",
            "DND_UNSUBSCRIBE",
            "NOT_INTERESTED",
            "QUESTION_NEEDS_HUMAN",
        }
        cat = data.get("category", "")
        if cat not in valid_categories:
            data["category"] = "QUESTION_NEEDS_HUMAN"

        return {"success": True, "provider": provider, "data": data}
    except json.JSONDecodeError as e:
        logger.error(f"Triage JSON parse error: {e}. Raw: {reply_text}")
        raise HTTPException(status_code=500, detail="AI returned invalid formatting. Try again.")
    except Exception as e:
        logger.error(f"Triage classification failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
