"""
AI API
Secure backend endpoints for AI/LLM operations
All API keys are stored server-side only
"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.config import settings
from app.utils.logger import setup_logger
from app.api.auth_deps import get_current_user, get_current_user_optional
from app.models.user import User

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
    target_industries: List[str]
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
                    location=settings.google_cloud_location
                )
                
                model = GenerativeModel(
                    model_name="gemini-1.5-flash",
                    system_instruction=system_instruction if system_instruction else None
                )
                
                response = model.generate_content(prompt)
                return response.text
            except Exception as e:
                logger.warning(f"Vertex AI failed, trying Gemini API: {e}")
        
        # Fallback to Gemini API
        if settings.gemini_api_key:
            import google.generativeai as genai
            
            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            full_prompt = f"{system_instruction}\n\n{prompt}" if system_instruction else prompt
            response = model.generate_content(full_prompt)
            return response.text
        
        # No AI available
        raise HTTPException(
            status_code=503,
            detail="AI service not configured. Please set up Vertex AI or Gemini API key."
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
    current_user: Optional[User] = Depends(get_current_user_optional)
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
    current_user: Optional[User] = Depends(get_current_user_optional)
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
    current_user: Optional[User] = Depends(get_current_user_optional)
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
    request: ABTestVariantRequest,
    current_user: Optional[User] = Depends(get_current_user_optional)
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
        "default_model": settings.default_llm
    }
