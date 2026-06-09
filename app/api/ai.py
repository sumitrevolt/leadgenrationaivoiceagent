"""
AI API
Secure backend endpoints for AI/LLM operations
All API keys are stored server-side only
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth_deps import get_current_user_optional
from app.config import settings
from app.models.user import User
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/ai", tags=["AI"])


# ============================================================================
# Request/Response Models
# ============================================================================


class GenerateScriptRequest(BaseModel):
    """Generate sales script request"""

    product_info: str
    target_audience: str


class GenerateTranscriptRequest(BaseModel):
    """Generate call transcript request"""

    agent_name: str
    company_name: str
    industry: str
    outcome: str


class StrategySuggestionRequest(BaseModel):
    """Strategy suggestion request"""

    target_industries: list[str]
    monthly_leads_goal: int
    monthly_appointments_goal: int
    agent_aggressiveness: str


class ABTestVariantRequest(BaseModel):
    """A/B test variant request"""

    original_script: str
    was_winning: bool


class AIResponse(BaseModel):
    """Generic AI response"""

    content: str
    model: str = "gemini-1.5-flash"


# ============================================================================
# AI Client - Server-side only
# ============================================================================


async def call_vertex_ai(prompt: str, system_instruction: str = "") -> str:
    """
    Call Vertex AI/Gemini - API key is ONLY on server side
    """
    try:
        # Try Vertex AI first (GCP)
        if settings.google_cloud_project_id:
            try:
                import vertexai
                from vertexai.generative_models import GenerativeModel

                vertexai.init(
                    project=settings.google_cloud_project_id,
                    location=settings.google_cloud_location,
                )

                model = GenerativeModel(
                    model_name="gemini-1.5-flash",
                    system_instruction=system_instruction if system_instruction else None,
                )

                response = model.generate_content(prompt)
                return response.text
            except Exception as e:
                logger.warning(f"Vertex AI failed, trying Gemini API: {e}")

        # Fallback to Gemini API
        if settings.gemini_api_key:
            import google.generativeai as genai

            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")

            full_prompt = f"{system_instruction}\n\n{prompt}" if system_instruction else prompt
            response = model.generate_content(full_prompt)
            return response.text

        # No AI available
        raise HTTPException(
            status_code=503,
            detail="AI service not configured. Please set up Vertex AI or Gemini API key.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AI generation error: {e}")
        raise HTTPException(status_code=500, detail=f"AI generation failed: {str(e)}")


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/generate-script", response_model=AIResponse)
async def generate_sales_script(
    request: GenerateScriptRequest,
    current_user: User | None = Depends(get_current_user_optional),
):
    """
    Generate a B2B sales script
    """
    system_instruction = """You are an expert B2B sales scriptwriter. Create a compelling, concise cold call script with:
1. **Opener:** Brief, engaging introduction
2. **Pitch:** Clear value proposition
3. **Objection Handling:** Common objection and response
4. **Call to Action:** Clear next step

Format in Markdown."""

    prompt = f"""
**Product/Service Description:**
{request.product_info}

**Target Audience:**
{request.target_audience}

Generate the sales script now.
"""

    content = await call_vertex_ai(prompt, system_instruction)
    return AIResponse(content=content)


@router.post("/generate-transcript", response_model=AIResponse)
async def generate_call_transcript(
    request: GenerateTranscriptRequest,
    current_user: User | None = Depends(get_current_user_optional),
):
    """
    Generate a realistic call transcript
    """
    system_instruction = f"""You are a call transcript generator. Create a realistic, brief call transcript.
- AI agent: {request.agent_name} from "AuraLeads AI"
- Prospect: {request.company_name} ({request.industry})
- Format with speaker labels."""

    prompt = f"""
Generate a call transcript with outcome: {request.outcome}

Rules:
- 'Appointment Set': Prospect agrees to meeting
- 'Voicemail': Agent leaves concise message
- 'Completed': Interest but needs follow-up
- 'No Answer': Just "[No Answer]"
"""

    content = await call_vertex_ai(prompt, system_instruction)
    return AIResponse(content=content)


@router.post("/strategy-suggestion", response_model=AIResponse)
async def get_strategy_suggestion(
    request: StrategySuggestionRequest,
    current_user: User | None = Depends(get_current_user_optional),
):
    """
    Get AI-powered strategy suggestions
    """
    system_instruction = """You are a world-class B2B marketing strategist. Provide 2-3 actionable suggestions for improving lead generation campaigns. Focus on expanding target market and optimizing approach. Format in Markdown."""

    prompt = f"""
Current campaign settings:
- Target Industries: {', '.join(request.target_industries)}
- Monthly Leads Goal: {request.monthly_leads_goal}
- Monthly Appointments Goal: {request.monthly_appointments_goal}
- Agent Aggressiveness: {request.agent_aggressiveness}

Provide strategic suggestions for improvement.
"""

    content = await call_vertex_ai(prompt, system_instruction)
    return AIResponse(content=content)


@router.post("/ab-test-variant", response_model=AIResponse)
async def generate_ab_test_variant(
    request: ABTestVariantRequest, current_user: User | None = Depends(get_current_user_optional)
):
    """
    Generate A/B test script variant
    """
    system_instruction = """You are an A/B testing copywriter for B2B sales. Create a new script opener variant.
- If original was winner: Try completely different angle
- If original was loser: Improve based on potential weaknesses
Output ONLY the new opener text."""

    status = "WINNER" if request.was_winning else "LOSER"
    prompt = f"""
Original script opener:
"{request.original_script}"

This was the {status} of the last A/B test.
Generate a new creative opener.
"""

    content = await call_vertex_ai(prompt, system_instruction)
    return AIResponse(content=content)


@router.get("/health")
async def ai_health_check():
    """
    Check AI service availability
    """
    has_vertex = bool(settings.google_cloud_project_id)
    has_gemini = bool(settings.gemini_api_key)

    return {
        "status": "available" if (has_vertex or has_gemini) else "unavailable",
        "vertex_ai": has_vertex,
        "gemini_api": has_gemini,
        "default_model": settings.default_llm,
    }


# ============================================================================
# NL CRM COMMAND BAR ("talk to your CRM") — Expedify-style.
# Hinglish NL -> free-LLM intent -> ALLOWLISTED safe actions over existing data.
# READ/DRAFT only (koi auto-send/auto-write nahi — ban-safe + 1-click culture).
# Free-stack: app.voice_agent.free_ai chain (Cerebras/Groq/…). Kabhi raise nahi.
# ============================================================================
import json as _json  # noqa: E402

_CMD_ACTIONS = {"stats", "list_clients", "find_client", "draft_followup", "draft_message", "help"}

_CMD_SYSTEM = (
    "Tum LeadGenAI CRM ka command-parser ho. User Hinglish/English me request karega. "
    "SIRF ek JSON object lautao, aur kuch nahi: "
    '{"action":"<stats|list_clients|find_client|draft_followup|draft_message|help>",'
    '"params":{"query":"<naam/keyword agar ho>","status":"<active|inactive agar ho>",'
    '"topic":"<message ka topic agar ho>"},"reply":"<ek line Hinglish acknowledgement>"}. '
    "Samajh na aaye to action=help. Koi explanation mat do, sirf JSON."
)


def _extract_json(text: str) -> dict:
    """LLM output se pehla JSON object nikaalo (code-fence safe). Fail -> {}."""
    if not text:
        return {}
    t = text.strip()
    i, j = t.find("{"), t.rfind("}")
    if i != -1 and j != -1 and j > i:
        t = t[i : j + 1]
    try:
        d = _json.loads(t)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _cmd_stats() -> dict:
    """Lightweight CRM snapshot — clients + inquiries counts (pure, no DB session)."""
    out = {"clients": 0, "active_clients": 0, "inquiries": 0}
    try:
        from app.marketing import clients_store

        cl = clients_store.list_clients()
        out["clients"] = len(cl)
        out["active_clients"] = sum(1 for c in cl if str(c.get("status")) == "active")
    except Exception:
        pass
    try:
        import os

        f = os.path.join("data", "inquiries.jsonl")
        if os.path.exists(f):
            with open(f, encoding="utf-8") as fh:
                out["inquiries"] = sum(1 for _ in fh)
    except Exception:
        pass
    return out


async def _cmd_draft(topic: str, who: str) -> dict:
    """Hinglish follow-up/message DRAFT (auto-send NAHI). free-LLM se."""
    from app.voice_agent import free_ai

    sys = (
        "Tum ek polite Indian sales assistant ho. Ek SHORT (2-3 line) Hinglish "
        "follow-up message likho. Sirf message, koi explanation nahi."
    )
    prompt = f"Kis ke liye: {who or 'customer'}. Topic: {topic or 'general follow-up'}."
    reply, prov = await free_ai.chat(
        sys, [{"role": "user", "content": prompt}], max_tokens=160, temperature=0.7
    )
    return {
        "draft": reply or "Namaste! Aapki inquiry ke baare me follow-up kar rahe hain. Kaise help karein?",
        "provider": prov,
        "auto_sent": False,
    }


class CommandIn(BaseModel):
    """NL command bar input."""

    query: str
    client_id: str | None = None


@router.post("/command")
async def nl_command(req: CommandIn, user: User = Depends(get_current_user_optional)):
    """NL CRM command bar — Hinglish NL -> intent -> SAFE read/draft action.

    Auto-send/auto-write kabhi nahi (sirf data dikhata + draft deta). free-LLM
    se intent parse, allowlisted actions hi execute. Defensive: kuch bhi fail =>
    help fallback, kabhi 500 nahi (except validation).
    """
    q = (req.query or "").strip()
    if len(q) < 2:
        raise HTTPException(
            status_code=422,
            detail="Kuch likho — e.g. 'stats dikhao' ya 'solar client ko follow-up draft karo'.",
        )
    from app.voice_agent import free_ai

    raw, provider = await free_ai.chat(
        _CMD_SYSTEM, [{"role": "user", "content": q}], max_tokens=200, temperature=0.1
    )
    intent = _extract_json(raw)
    action = intent.get("action")
    if action not in _CMD_ACTIONS:
        action = "help"
    params = intent.get("params") if isinstance(intent.get("params"), dict) else {}
    human = str(intent.get("reply") or "").strip()
    data = None
    try:
        if action == "stats":
            data = _cmd_stats()
        elif action == "list_clients":
            from app.marketing import clients_store

            st = params.get("status") or None
            data = [
                {
                    "id": c.get("id"),
                    "business_name": c.get("business_name"),
                    "niche": c.get("niche"),
                    "city": c.get("city"),
                    "plan": c.get("plan"),
                    "status": c.get("status"),
                }
                for c in clients_store.list_clients(st)[:25]
            ]
        elif action == "find_client":
            from app.marketing import clients_store

            kw = str(params.get("query") or "").strip().lower()
            matches = [
                c
                for c in clients_store.list_clients()
                if kw
                and (
                    kw in str(c.get("business_name", "")).lower()
                    or kw in str(c.get("niche", "")).lower()
                    or kw in str(c.get("city", "")).lower()
                )
            ]
            data = [
                {
                    "id": c.get("id"),
                    "business_name": c.get("business_name"),
                    "niche": c.get("niche"),
                    "city": c.get("city"),
                    "plan": c.get("plan"),
                }
                for c in matches[:15]
            ]
        elif action in ("draft_followup", "draft_message"):
            data = await _cmd_draft(params.get("topic") or q, params.get("query") or "")
        else:
            action = "help"
            data = {
                "capabilities": [
                    "stats dikhao",
                    "clients list karo",
                    "'X' naam ka client dhoondo",
                    "'X' client ko follow-up draft karo",
                    "diwali offer ka message draft karo",
                ]
            }
    except Exception as e:
        logger.warning(f"[nl-command] action {action} failed: {e}")
        action = "help"
        data = {"error": "Yeh command abhi process nahi hui, dobara try karo."}
    if not human:
        human = {
            "stats": "Yeh raha CRM snapshot.",
            "list_clients": "Yeh tumhare clients hain.",
            "find_client": "Yeh matching clients mile.",
            "draft_followup": "Follow-up draft taiyaar (review karke bhejo).",
            "draft_message": "Message draft taiyaar.",
            "help": "Main yeh kar sakta hoon:",
        }.get(action, "Done.")
    return {"ok": True, "action": action, "reply": human, "data": data, "provider": provider}


# ============================================================================
# POST-CALL AI QUALIFIER ("qualify leads 24/7") — Expedify-style voice boost.
# Real-time path ke BAHAR: call transcript -> structured qualification + draft.
# ============================================================================
class QualifyCallIn(BaseModel):
    """Post-call qualification input."""

    transcript: str
    context: dict | None = None


@router.post("/qualify-call")
async def qualify_call(req: QualifyCallIn, user: User = Depends(get_current_user_optional)):
    """Call transcript -> AI lead qualification (interest/qualified/appointment/
    budget/summary/next-action/follow-up draft). free-LLM, latency-safe (post-call)."""
    tx = (req.transcript or "").strip()
    if len(tx) < 10:
        raise HTTPException(status_code=422, detail="Transcript chahiye (chhota/khaali hai).")
    from app.voice_agent.call_qualifier import qualify_transcript

    return await qualify_transcript(tx, req.context or {})
