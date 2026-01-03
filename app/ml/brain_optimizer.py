"""
Brain Optimizer - Dynamic Prompt and Response Optimization
Continuously improves LLM Brain based on learned patterns

Features:
- Dynamic prompt selection based on context
- RAG (Retrieval Augmented Generation) for similar conversations
- A/B testing of response variants
- Real-time prompt adjustment
- Industry-specific optimization
"""
import json
import asyncio
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

from app.utils.logger import setup_logger
from app.ml.feedback_loop import FeedbackLoop, CallOutcome
from app.ml.vector_store import VectorStore

logger = setup_logger(__name__)


@dataclass
class OptimizedPrompt:
    """An optimized prompt for a specific context"""
    prompt_id: str
    prompt_type: str  # system, greeting, objection, closing
    
    # Context
    industry: str = "general"
    language: str = "hinglish"
    
    # The prompt content
    content: str = ""
    
    # Performance metrics
    times_used: int = 0
    success_count: int = 0
    success_rate: float = 0.0
    
    # A/B testing
    is_control: bool = True
    variant_id: Optional[str] = None
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    source: str = "manual"  # manual, learned, generated


@dataclass
class ConversationContext:
    """Context for a conversation to optimize responses"""
    call_id: str
    tenant_id: str
    
    # Lead info
    lead_industry: str
    lead_company: str
    lead_city: str
    
    # Conversation state
    current_intent: str
    conversation_history: List[Dict]
    
    # Agent state
    agent_persona: str = "sales_agent"
    language: str = "hinglish"
    
    # Similar conversations (for RAG)
    similar_conversations: List[Dict] = field(default_factory=list)


class BrainOptimizer:
    """
    Optimizes LLM Brain responses using learned patterns
    
    Key capabilities:
    1. Select best prompt for context
    2. Inject RAG context from similar successful conversations
    3. Run A/B tests on response variants
    4. Dynamically adjust prompts based on conversation flow
    5. Personalize responses per industry/lead
    """
    
    def __init__(
        self,
        data_dir: str = "data/optimizer",
        feedback_loop: FeedbackLoop = None,
        vector_store: VectorStore = None,
        tenant_id: str = None
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.tenant_id = tenant_id
        
        self.feedback_loop = feedback_loop or FeedbackLoop()
        self._vector_store = vector_store
        
        # Optimized prompts by type
        self.prompts: Dict[str, List[OptimizedPrompt]] = {
            "system": [],
            "greeting": [],
            "value_proposition": [],
            "objection_handler": [],
            "closing": [],
            "appointment": []
        }
        
        # A/B test assignments (call_id -> variant)
        self.ab_assignments: Dict[str, str] = {}
        
        # Load existing optimizations
        self._load_optimizations()
        
        logger.info("🧠 Brain Optimizer initialized")
    
    @property
    def vector_store(self):
        """Lazy load vector store"""
        if self._vector_store is None:
            self._vector_store = VectorStore()
        return self._vector_store
    
    def _load_optimizations(self):
        """Load optimized prompts from disk"""
        prompts_file = self.data_dir / "optimized_prompts.json"
        if prompts_file.exists():
            try:
                with open(prompts_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                for prompt_type, prompts in data.items():
                    if prompt_type in self.prompts:
                        for p in prompts:
                            self.prompts[prompt_type].append(
                                OptimizedPrompt(
                                    prompt_id=p.get("prompt_id", ""),
                                    prompt_type=prompt_type,
                                    industry=p.get("industry", "general"),
                                    content=p.get("content", ""),
                                    success_rate=p.get("success_rate", 0.0)
                                )
                            )
                
                logger.info("📂 Loaded optimized prompts")
            except Exception as e:
                logger.warning(f"Failed to load prompts: {e}")
    
    def _save_optimizations(self):
        """Save optimized prompts to disk"""
        prompts_file = self.data_dir / "optimized_prompts.json"
        
        data = {
            prompt_type: [
                {
                    "prompt_id": p.prompt_id,
                    "industry": p.industry,
                    "content": p.content,
                    "success_rate": p.success_rate,
                    "times_used": p.times_used
                }
                for p in prompts
            ]
            for prompt_type, prompts in self.prompts.items()
        }
        
        with open(prompts_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    async def get_optimized_system_prompt(
        self,
        agent_type: str,
        industry: str,
        language: str = "hinglish",
        base_prompt: str = None
    ) -> str:
        """
        Get an optimized system prompt for the context
        
        Args:
            agent_type: Type of agent (sales_agent, qualifier, etc.)
            industry: Lead's industry
            language: Preferred language
            base_prompt: Default prompt to use if no optimization available
        
        Returns:
            Optimized system prompt
        """
        
        # Find matching optimized prompts
        candidates = [
            p for p in self.prompts["system"]
            if p.industry in (industry, "general") and p.success_rate > 0.3
        ]
        
        if not candidates:
            return base_prompt or self._get_default_system_prompt(agent_type)
        
        # Sort by success rate weighted by usage
        candidates.sort(
            key=lambda p: p.success_rate * min(1.0, p.times_used / 20),
            reverse=True
        )
        
        best = candidates[0]
        
        # Inject industry-specific context
        enhanced_prompt = self._enhance_prompt_for_industry(
            best.content, industry, language
        )
        
        return enhanced_prompt
    
    def _get_default_system_prompt(self, agent_type: str) -> str:
        """Get default system prompt"""
        
        prompts = {
            "sales_agent": """You are an AI sales agent for LeadGen AI Solutions.
You speak naturally in Hinglish (Hindi + English mix).
Your goal is to:
1. Introduce the AI voice agent service
2. Qualify the lead
3. Handle objections professionally
4. Book a demo appointment

Be conversational, not scripted. Listen actively and respond to what the customer says.""",

            "qualifier": """You are a lead qualification agent.
Your job is to determine:
1. Is this the decision maker?
2. Do they have budget?
3. What's their timeline?
4. What are their pain points?

Ask questions naturally and listen to their answers.""",

            "appointment_booker": """You are an appointment booking agent.
After qualifying interest, your job is to:
1. Suggest specific time slots
2. Confirm the meeting
3. Get necessary contact details

Be efficient but friendly."""
        }
        
        return prompts.get(agent_type, prompts["sales_agent"])
    
    def _enhance_prompt_for_industry(
        self,
        prompt: str,
        industry: str,
        language: str
    ) -> str:
        """Add industry-specific context to prompt"""
        
        industry_context = {
            "solar": """
Industry Context (Solar):
- Common pain points: High electricity bills, power cuts, unreliable grid
- Budget concerns: EMI options available, government subsidies
- Decision factors: Roof space, ownership, electricity consumption""",

            "real_estate": """
Industry Context (Real Estate):
- Common pain points: Lead quality, follow-up time, missed opportunities
- Budget concerns: ROI on marketing spend
- Decision factors: Project locations, target buyer segment""",

            "digital_marketing": """
Industry Context (Digital Marketing):
- Common pain points: Client acquisition, scaling campaigns, team bandwidth
- Budget concerns: Cost per lead, client retainers
- Decision factors: Services offered, client base size""",

            "education": """
Industry Context (Education):
- Common pain points: Admission inquiries, counselor workload, lead conversion
- Budget concerns: Marketing budget per admission
- Decision factors: Courses offered, student demographics"""
        }
        
        context = industry_context.get(industry, "")
        
        if context:
            return f"{prompt}\n\n{context}"
        
        return prompt
    
    async def get_rag_context(
        self,
        context: ConversationContext,
        current_query: str,
        top_k: int = 3
    ) -> List[Dict]:
        """
        Get relevant context from similar successful conversations
        
        Uses vector similarity to find:
        - Similar objections and how they were handled
        - Similar leads and what worked
        - Industry-specific successful patterns
        """
        
        try:
            # Search for similar conversations
            similar = await self.vector_store.search_similar(
                query=current_query,
                industry=context.lead_industry,
                outcome_filter="successful",
                top_k=top_k
            )
            
            # Format as context
            rag_context = []
            for s in similar:
                rag_context.append({
                    "similarity": s.get("score", 0),
                    "response_used": s.get("agent_response", ""),
                    "outcome": s.get("outcome", ""),
                    "industry": s.get("industry", "")
                })
            
            return rag_context
            
        except Exception as e:
            logger.warning(f"RAG context retrieval failed: {e}")
            return []
    
    async def get_optimized_response(
        self,
        context: ConversationContext,
        response_type: str,  # objection_handler, greeting, closing
        base_response: str = None
    ) -> Tuple[str, Dict]:
        """
        Get an optimized response for the situation
        
        Returns:
            (optimized_response, metadata)
        """
        
        metadata = {
            "source": "base",
            "variant": None,
            "rag_used": False
        }
        
        # 1. Check for learned best response
        learned = self.feedback_loop.get_best_response(
            response_type=response_type,
            industry=context.lead_industry,
            language=context.language,
            fallback=None
        )
        
        if learned:
            metadata["source"] = "learned"
            return learned, metadata
        
        # 2. Check for A/B test variant
        ab_response, variant = self._get_ab_variant(
            context.call_id,
            response_type
        )
        
        if ab_response:
            metadata["source"] = "ab_test"
            metadata["variant"] = variant
            return ab_response, metadata
        
        # 3. Try RAG enhancement
        if base_response:
            rag_context = await self.get_rag_context(
                context=context,
                current_query=context.current_intent,
                top_k=2
            )
            
            if rag_context:
                enhanced = self._enhance_with_rag(base_response, rag_context)
                metadata["source"] = "rag_enhanced"
                metadata["rag_used"] = True
                return enhanced, metadata
        
        # 4. Return base response
        return base_response or "", metadata
    
    def _get_ab_variant(
        self,
        call_id: str,
        response_type: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Get A/B test variant for this call"""
        
        # Check if already assigned
        assignment_key = f"{call_id}_{response_type}"
        if assignment_key in self.ab_assignments:
            return None, self.ab_assignments[assignment_key]
        
        # Check for active variants
        variants = [
            p for p in self.prompts.get(response_type, [])
            if p.variant_id and not p.is_control
        ]
        
        if not variants:
            return None, None
        
        # 20% chance to get variant
        if random.random() < 0.2:
            variant = random.choice(variants)
            self.ab_assignments[assignment_key] = variant.variant_id
            return variant.content, variant.variant_id
        
        return None, "control"
    
    def _enhance_with_rag(
        self,
        base_response: str,
        rag_context: List[Dict]
    ) -> str:
        """Enhance response with RAG context"""
        
        # If we have a highly successful similar response, use elements from it
        if rag_context and rag_context[0].get("similarity", 0) > 0.8:
            similar_response = rag_context[0].get("response_used", "")
            
            # For now, just return the similar response
            # In production, could use LLM to blend
            if similar_response:
                return similar_response
        
        return base_response
    
    async def get_objection_response(
        self,
        objection_type: str,
        context: ConversationContext,
        base_response: str = None
    ) -> str:
        """
        Get best response for a specific objection
        
        Uses feedback loop to select highest-performing response
        """
        
        # Get best from feedback loop
        best = self.feedback_loop.get_best_objection_response(
            objection_type=objection_type,
            fallback=base_response
        )
        
        if best:
            # Personalize for industry
            personalized = self._personalize_response(
                best,
                context.lead_industry,
                context.lead_company
            )
            return personalized
        
        return base_response or "Main samajh sakta hoon. Kya aur koi concern hai?"
    
    def _personalize_response(
        self,
        response: str,
        industry: str,
        company: str
    ) -> str:
        """Add personalization to response"""
        
        # Simple personalization (could be more sophisticated)
        personalized = response
        
        if company:
            personalized = personalized.replace(
                "aapki company",
                f"{company}"
            )
        
        return personalized
    
    async def record_response_outcome(
        self,
        call_id: str,
        response_type: str,
        response_used: str,
        outcome: CallOutcome,
        context: ConversationContext
    ):
        """
        Record outcome for a response to improve future selection
        """
        
        # Update feedback loop
        await self.feedback_loop.record_outcome(
            call_id=call_id,
            tenant_id=context.tenant_id,
            industry=context.lead_industry,
            language=context.language,
            responses_used=[{
                "type": response_type,
                "content": response_used,
                "intent": context.current_intent
            }],
            outcome=outcome
        )
        
        # Update local prompt stats
        for prompt in self.prompts.get(response_type, []):
            if prompt.content == response_used:
                prompt.times_used += 1
                if outcome == CallOutcome.SUCCESS:
                    prompt.success_count += 1
                prompt.success_rate = prompt.success_count / prompt.times_used
        
        # Record A/B test result
        assignment_key = f"{call_id}_{response_type}"
        if assignment_key in self.ab_assignments:
            variant = self.ab_assignments[assignment_key]
            # Log A/B result for analysis
            logger.info(
                f"📊 A/B Result: {response_type} | "
                f"variant={variant} | outcome={outcome.value}"
            )
        
        self._save_optimizations()
    
    def add_prompt_variant(
        self,
        prompt_type: str,
        content: str,
        industry: str = "general",
        is_control: bool = False
    ):
        """Add a new prompt variant for testing"""
        
        variant_id = f"v{len(self.prompts[prompt_type]) + 1}"
        
        prompt = OptimizedPrompt(
            prompt_id=f"{prompt_type}_{variant_id}",
            prompt_type=prompt_type,
            industry=industry,
            content=content,
            is_control=is_control,
            variant_id=variant_id,
            source="manual"
        )
        
        self.prompts[prompt_type].append(prompt)
        self._save_optimizations()
        
        logger.info(f"➕ Added prompt variant: {prompt_type}/{variant_id}")
    
    def get_ab_test_results(self) -> Dict:
        """Get A/B testing results"""
        
        results = {}
        
        for prompt_type, prompts in self.prompts.items():
            if not prompts:
                continue
            
            control = [p for p in prompts if p.is_control]
            variants = [p for p in prompts if not p.is_control]
            
            if control and variants:
                results[prompt_type] = {
                    "control": {
                        "success_rate": control[0].success_rate,
                        "times_used": control[0].times_used
                    },
                    "variants": [
                        {
                            "id": v.variant_id,
                            "success_rate": v.success_rate,
                            "times_used": v.times_used,
                            "lift": (
                                (v.success_rate - control[0].success_rate)
                                / control[0].success_rate * 100
                                if control[0].success_rate > 0 else 0
                            )
                        }
                        for v in variants
                    ]
                }
        
        return results
    
    def get_optimization_stats(self) -> Dict:
        """Get optimization statistics"""
        
        return {
            "total_prompts": sum(len(p) for p in self.prompts.values()),
            "prompt_types": {
                ptype: len(prompts)
                for ptype, prompts in self.prompts.items()
            },
            "ab_tests_active": len([
                p for prompts in self.prompts.values()
                for p in prompts if p.variant_id and not p.is_control
            ]),
            "total_ab_assignments": len(self.ab_assignments)
        }


# Singleton instance
brain_optimizer = BrainOptimizer()
