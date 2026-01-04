"""
Agent Brain - Vertex AI Powered Sub-Agent Intelligence System
Self-training, context-aware agents that understand the project deeply

Powers the 13 specialized sub-agents defined in .github/copilot-instructions.md:
- Voice AI Engineer, Lead Generation Architect, ML/AI Optimizer
- Revenue Engineer, Pricing Optimizer, Growth Hacker
- Integration Master, Security Guardian, Backend Architect
- Frontend Architect, DevOps & Infra Specialist, QA Automator
- Product Strategist

Features:
- Project context embedding and retrieval (RAG)
- Self-improvement via accepted suggestion tracking
- Domain-specific knowledge bases per agent
- Vertex AI Gemini for reasoning and suggestions
- Continuous learning from codebase changes
"""
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from app.utils.logger import setup_logger
from app.ml.vector_store import VectorStore

logger = setup_logger(__name__)


class AgentRole(Enum):
    """Specialized sub-agent roles powered by Vertex AI"""
    VOICE_AI = "voice_ai"
    LEADS = "leads"
    ML = "ml"
    BILLING = "billing"
    PRICING = "pricing"
    GROWTH = "growth"
    INTEGRATIONS = "integrations"
    SECURITY = "security"
    BACKEND = "backend"
    FRONTEND = "frontend"
    INFRA = "infra"
    QA = "qa"
    PRODUCT = "product"


@dataclass
class AgentContext:
    """Context for an agent to reason about a task"""
    agent_role: AgentRole
    task_description: str
    
    # File context
    current_file: str = ""
    file_content: str = ""
    related_files: List[str] = field(default_factory=list)
    
    # Project knowledge (from RAG)
    relevant_patterns: List[Dict] = field(default_factory=list)
    similar_code: List[Dict] = field(default_factory=list)
    
    # Constraints
    priority: str = "medium"  # revenue > security > scale > features
    roi_impact: str = ""
    risk_level: str = "low"
    
    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AgentSuggestion:
    """A suggestion from a sub-agent to the main agent"""
    agent_role: AgentRole
    suggestion_id: str
    
    # The suggestion
    action: str
    reasoning: str  # billionaire reasoning
    code_snippet: str = ""
    
    # Impact assessment
    impact_category: str = ""  # revenue, security, scale, ux
    estimated_impact: str = ""
    
    # Quality gates
    tests_required: List[str] = field(default_factory=list)
    security_checks: List[str] = field(default_factory=list)
    risk_level: str = "low"
    
    # Tracking
    created_at: datetime = field(default_factory=datetime.now)
    accepted: Optional[bool] = None
    accepted_at: Optional[datetime] = None
    
    def to_formatted_string(self) -> str:
        """Format as per copilot-instructions suggestion format"""
        return (
            f"[@agent:{self.agent_role.value}] suggests: {self.action} "
            f"because {self.reasoning}. "
            f"Tests: {', '.join(self.tests_required) or 'none'}. "
            f"Risk: {self.risk_level}."
        )


# Agent-specific knowledge domains and file patterns
AGENT_KNOWLEDGE_MAP: Dict[AgentRole, Dict] = {
    AgentRole.VOICE_AI: {
        "file_patterns": ["app/voice_agent/**", "app/telephony/**", "app/llm/**"],
        "domain_keywords": ["twilio", "exotel", "websocket", "asr", "tts", "barge-in", "call", "voice"],
        "priority": "revenue",
        "expertise": [
            "Real-time call loop optimization",
            "ASR/TTS latency reduction",
            "LLM fallback chains",
            "Machine detection and voicemail handling",
            "Prompt engineering for conversational AI",
        ],
    },
    AgentRole.LEADS: {
        "file_patterns": ["app/lead_scraper/**", "app/automation/campaign_manager.py"],
        "domain_keywords": ["scrape", "lead", "google maps", "indiamart", "justdial", "dnd", "score"],
        "priority": "revenue",
        "expertise": [
            "Web scraping optimization",
            "Lead deduplication algorithms",
            "DND compliance checking",
            "Lead scoring models",
            "Campaign batching and queuing",
        ],
    },
    AgentRole.ML: {
        "file_patterns": ["app/ml/**", "data/vectorstore/**", "models/**"],
        "domain_keywords": ["train", "model", "embedding", "vector", "classifier", "a/b test"],
        "priority": "scale",
        "expertise": [
            "Intent classification training",
            "Lead scoring optimization",
            "RAG and semantic search",
            "A/B testing frameworks",
            "Model versioning and rollback",
        ],
    },
    AgentRole.BILLING: {
        "file_patterns": ["app/billing/**", "app/api/billing.py"],
        "domain_keywords": ["stripe", "razorpay", "subscription", "invoice", "payment", "webhook"],
        "priority": "revenue",
        "expertise": [
            "Payment gateway integration",
            "Subscription lifecycle management",
            "Webhook signature verification",
            "Revenue leakage prevention",
            "Metered billing and quotas",
        ],
    },
    AgentRole.PRICING: {
        "file_patterns": ["app/billing/**", "app/api/analytics.py", "frontend/src/**pricing**"],
        "domain_keywords": ["price", "plan", "upsell", "trial", "upgrade", "promo", "paywall"],
        "priority": "revenue",
        "expertise": [
            "Dynamic pricing experiments",
            "Trial-to-paid conversion optimization",
            "Usage-based throttles",
            "Promo code strategies",
            "Upsell CTA placement",
        ],
    },
    AgentRole.GROWTH: {
        "file_patterns": ["app/automation/**", "app/platform.py"],
        "domain_keywords": ["activation", "retention", "onboard", "report", "alert", "whatsapp"],
        "priority": "revenue",
        "expertise": [
            "Tenant acquisition automation",
            "Activation loop design",
            "WhatsApp/email notification triggers",
            "Conversion funnel optimization",
            "Churn prediction and prevention",
        ],
    },
    AgentRole.INTEGRATIONS: {
        "file_patterns": ["app/integrations/**", "app/api/webhooks.py"],
        "domain_keywords": ["hubspot", "zoho", "sheets", "crm", "oauth", "sync", "webhook"],
        "priority": "scale",
        "expertise": [
            "CRM bidirectional sync",
            "OAuth2 flow implementation",
            "Webhook idempotency",
            "Retry with exponential backoff",
            "Rate limit handling",
        ],
    },
    AgentRole.SECURITY: {
        "file_patterns": ["app/middleware/**", "app/api/auth_deps.py", "app/exceptions.py"],
        "domain_keywords": ["auth", "jwt", "rbac", "rate limit", "validation", "secret", "xss", "sql injection"],
        "priority": "security",
        "expertise": [
            "JWT authentication patterns",
            "Role-based access control",
            "Input validation and sanitization",
            "Secret management best practices",
            "Security header configuration",
        ],
    },
    AgentRole.BACKEND: {
        "file_patterns": ["app/api/**", "app/models/**", "app/cache.py", "alembic/**"],
        "domain_keywords": ["fastapi", "sqlalchemy", "pydantic", "async", "alembic", "migration"],
        "priority": "scale",
        "expertise": [
            "FastAPI dependency injection",
            "Async SQLAlchemy patterns",
            "Pydantic v2 validation",
            "N+1 query prevention",
            "Connection pooling",
        ],
    },
    AgentRole.FRONTEND: {
        "file_patterns": ["frontend/src/**", "frontend/package.json"],
        "domain_keywords": ["react", "typescript", "tailwind", "component", "hook", "query"],
        "priority": "features",
        "expertise": [
            "React component patterns",
            "TypeScript best practices",
            "Tailwind CSS styling",
            "React Query state management",
            "Accessible UI components",
        ],
    },
    AgentRole.INFRA: {
        "file_patterns": ["Dockerfile*", "docker-compose*.yml", "cloudbuild.yaml", "infrastructure/**", "*.tf"],
        "domain_keywords": ["docker", "terraform", "cloud run", "gcp", "deploy", "ci/cd"],
        "priority": "scale",
        "expertise": [
            "Multi-stage Docker builds",
            "Terraform module design",
            "Cloud Run autoscaling",
            "Secret Manager integration",
            "CI/CD pipeline optimization",
        ],
    },
    AgentRole.QA: {
        "file_patterns": ["tests/**", "app/tests/**"],
        "domain_keywords": ["test", "pytest", "fixture", "mock", "coverage", "e2e"],
        "priority": "scale",
        "expertise": [
            "Pytest fixture design",
            "Async test patterns",
            "Mock strategies for external services",
            "Integration test isolation",
            "Coverage optimization",
        ],
    },
    AgentRole.PRODUCT: {
        "file_patterns": ["README.md", "docs/**", "CHANGELOG.md"],
        "domain_keywords": ["documentation", "api", "readme", "feature", "roadmap", "positioning"],
        "priority": "features",
        "expertise": [
            "Technical documentation",
            "API documentation standards",
            "Feature narrative and positioning",
            "User experience optimization",
            "Competitive differentiation",
        ],
    },
}


class AgentBrain:
    """
    Vertex AI powered brain for sub-agents
    
    Capabilities:
    1. Context-aware reasoning using project knowledge
    2. Self-improvement via suggestion tracking
    3. RAG for code pattern retrieval
    4. Billionaire-mindset decision making
    5. Multi-agent coordination
    """
    
    def __init__(
        self,
        data_dir: str = "data/agent_brain",
        vector_store: VectorStore = None,
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self._vector_store = vector_store
        
        # Suggestion history for learning
        self.suggestion_history: List[AgentSuggestion] = []
        self._load_history()
        
        # Agent performance metrics
        self.agent_metrics: Dict[AgentRole, Dict] = {
            role: {
                "suggestions_made": 0,
                "suggestions_accepted": 0,
                "acceptance_rate": 0.0,
                "avg_impact": 0.0,
            }
            for role in AgentRole
        }
        self._load_metrics()
        
        logger.info("🧠 Agent Brain initialized with Vertex AI power")
    
    @property
    def vector_store(self) -> VectorStore:
        """Lazy load vector store"""
        if self._vector_store is None:
            self._vector_store = VectorStore(
                persist_directory="data/agent_vectorstore",
                collection_name="code_patterns"
            )
        return self._vector_store
    
    def _load_history(self):
        """Load suggestion history from disk"""
        history_file = self.data_dir / "suggestion_history.json"
        if history_file.exists():
            try:
                with open(history_file, "r") as f:
                    data = json.load(f)
                    # Convert to dataclass objects
                    for item in data:
                        item["agent_role"] = AgentRole(item["agent_role"])
                        item["created_at"] = datetime.fromisoformat(item["created_at"])
                        if item.get("accepted_at"):
                            item["accepted_at"] = datetime.fromisoformat(item["accepted_at"])
                        self.suggestion_history.append(AgentSuggestion(**item))
                logger.info(f"📚 Loaded {len(self.suggestion_history)} suggestions from history")
            except Exception as e:
                logger.warning(f"Failed to load history: {e}")
    
    def _save_history(self):
        """Save suggestion history to disk"""
        history_file = self.data_dir / "suggestion_history.json"
        try:
            data = []
            for s in self.suggestion_history[-1000:]:  # Keep last 1000
                item = {
                    "agent_role": s.agent_role.value,
                    "suggestion_id": s.suggestion_id,
                    "action": s.action,
                    "reasoning": s.reasoning,
                    "code_snippet": s.code_snippet,
                    "impact_category": s.impact_category,
                    "estimated_impact": s.estimated_impact,
                    "tests_required": s.tests_required,
                    "security_checks": s.security_checks,
                    "risk_level": s.risk_level,
                    "created_at": s.created_at.isoformat(),
                    "accepted": s.accepted,
                    "accepted_at": s.accepted_at.isoformat() if s.accepted_at else None,
                }
                data.append(item)
            with open(history_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save history: {e}")
    
    def _load_metrics(self):
        """Load agent metrics from disk"""
        metrics_file = self.data_dir / "agent_metrics.json"
        if metrics_file.exists():
            try:
                with open(metrics_file, "r") as f:
                    data = json.load(f)
                    for role_str, metrics in data.items():
                        role = AgentRole(role_str)
                        self.agent_metrics[role] = metrics
                logger.info("📊 Loaded agent metrics")
            except Exception as e:
                logger.warning(f"Failed to load metrics: {e}")
    
    def _save_metrics(self):
        """Save agent metrics to disk"""
        metrics_file = self.data_dir / "agent_metrics.json"
        try:
            data = {role.value: metrics for role, metrics in self.agent_metrics.items()}
            with open(metrics_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")
    
    def detect_agent(self, file_path: str, content: str = "") -> List[AgentRole]:
        """
        Detect which agent(s) should handle a file based on patterns
        
        Args:
            file_path: Path to the file being edited
            content: Optional file content for keyword matching
        
        Returns:
            List of relevant agents, primary first
        """
        matched_agents = []
        
        file_path_lower = file_path.lower().replace("\\", "/")
        content_lower = content.lower()
        
        for role, config in AGENT_KNOWLEDGE_MAP.items():
            score = 0
            
            # Check file patterns
            for pattern in config["file_patterns"]:
                # Simple glob matching
                pattern_clean = pattern.replace("**", "").replace("*", "").lower()
                if pattern_clean in file_path_lower:
                    score += 10
            
            # Check keywords in content
            for keyword in config["domain_keywords"]:
                if keyword in content_lower:
                    score += 2
            
            if score > 0:
                matched_agents.append((role, score))
        
        # Sort by score descending
        matched_agents.sort(key=lambda x: x[1], reverse=True)
        
        # Return roles only
        return [agent for agent, _ in matched_agents[:3]]  # Top 3
    
    async def get_project_context(
        self,
        query: str,
        agent_role: AgentRole,
        limit: int = 5
    ) -> List[Dict]:
        """
        Retrieve relevant project patterns via RAG
        
        Args:
            query: The task or question
            agent_role: Which agent is asking
            limit: Max patterns to retrieve
        
        Returns:
            List of relevant code patterns and examples
        """
        try:
            # Get agent's domain keywords to enhance query
            config = AGENT_KNOWLEDGE_MAP.get(agent_role, {})
            keywords = config.get("domain_keywords", [])
            enhanced_query = f"{query} {' '.join(keywords[:3])}"
            
            # Search vector store
            results = await self.vector_store.search(
                query=enhanced_query,
                limit=limit,
                filter_metadata={"domain": agent_role.value}
            )
            
            return results
        except Exception as e:
            logger.warning(f"RAG retrieval failed: {e}")
            return []
    
    async def generate_suggestion(
        self,
        context: AgentContext,
        use_vertex: bool = True
    ) -> AgentSuggestion:
        """
        Generate a suggestion using Vertex AI Gemini
        
        Args:
            context: The agent context with task and file info
            use_vertex: Whether to use Vertex AI (or fallback to templates)
        
        Returns:
            A formatted suggestion
        """
        import uuid
        
        agent_config = AGENT_KNOWLEDGE_MAP.get(context.agent_role, {})
        
        if use_vertex:
            try:
                from app.llm.vertex_client import get_vertex_client
                
                client = get_vertex_client()
                
                # Build the prompt with billionaire mindset
                system_prompt = self._build_agent_system_prompt(context.agent_role, agent_config)
                user_prompt = self._build_suggestion_prompt(context)
                
                full_prompt = f"{system_prompt}\n\n{user_prompt}"
                
                response, _ = await client.generate(
                    prompt=full_prompt,
                    max_tokens=1000,
                    temperature=0.7
                )
                
                # Parse the response into a suggestion
                suggestion = self._parse_llm_response(
                    response=response,
                    agent_role=context.agent_role,
                    context=context
                )
                
            except Exception as e:
                logger.warning(f"Vertex AI failed, using template: {e}")
                suggestion = self._generate_template_suggestion(context, agent_config)
        else:
            suggestion = self._generate_template_suggestion(context, agent_config)
        
        suggestion.suggestion_id = str(uuid.uuid4())[:8]
        
        # Track the suggestion
        self.suggestion_history.append(suggestion)
        self.agent_metrics[context.agent_role]["suggestions_made"] += 1
        self._save_history()
        self._save_metrics()
        
        return suggestion
    
    def _build_agent_system_prompt(self, role: AgentRole, config: Dict) -> str:
        """Build system prompt for an agent with billionaire mindset"""
        expertise = "\n".join(f"- {e}" for e in config.get("expertise", []))
        priority = config.get("priority", "features")
        
        return f"""You are the {role.value.replace('_', ' ').title()} sub-agent for the LeadGen AI Voice Agent platform.

## Your Expertise
{expertise}

## Priority Focus
Your suggestions must prioritize: {priority.upper()}
Priority hierarchy: Revenue > Security > Scale > Features

## Billionaire Mindset
- Every suggestion must have measurable ROI impact
- Automate anything done twice
- Design for 10,000× scale
- No secrets in code, security by default
- Quality without drag: tests alongside features

## Output Format
Provide suggestions in this exact format:
ACTION: [What to do]
REASONING: [Why, with billionaire reasoning]
CODE: [Optional code snippet]
IMPACT: [Revenue/Security/Scale/UX impact]
TESTS: [Required tests]
RISK: [low/medium/high]
"""
    
    def _build_suggestion_prompt(self, context: AgentContext) -> str:
        """Build the user prompt with context"""
        prompt = f"""## Task
{context.task_description}

## Current File
{context.current_file}

## File Content (excerpt)
```
{context.file_content[:2000]}
```

## Related Files
{', '.join(context.related_files[:5])}

## Relevant Patterns from Codebase
{json.dumps(context.relevant_patterns[:3], indent=2)}

Generate a high-impact suggestion following billionaire principles.
Focus on: {context.priority} priority.
"""
        return prompt
    
    def _parse_llm_response(
        self,
        response: str,
        agent_role: AgentRole,
        context: AgentContext
    ) -> AgentSuggestion:
        """Parse LLM response into structured suggestion"""
        # Extract sections using simple parsing
        action = ""
        reasoning = ""
        code = ""
        impact = ""
        tests = []
        risk = "low"
        
        lines = response.split("\n")
        current_section = ""
        
        for line in lines:
            if line.startswith("ACTION:"):
                action = line.replace("ACTION:", "").strip()
                current_section = "action"
            elif line.startswith("REASONING:"):
                reasoning = line.replace("REASONING:", "").strip()
                current_section = "reasoning"
            elif line.startswith("CODE:"):
                current_section = "code"
            elif line.startswith("IMPACT:"):
                impact = line.replace("IMPACT:", "").strip()
                current_section = "impact"
            elif line.startswith("TESTS:"):
                tests_str = line.replace("TESTS:", "").strip()
                tests = [t.strip() for t in tests_str.split(",") if t.strip()]
                current_section = "tests"
            elif line.startswith("RISK:"):
                risk = line.replace("RISK:", "").strip().lower()
                current_section = "risk"
            elif current_section == "code":
                code += line + "\n"
            elif current_section == "reasoning":
                reasoning += " " + line.strip()
        
        return AgentSuggestion(
            agent_role=agent_role,
            suggestion_id="",
            action=action or "Review and optimize",
            reasoning=reasoning or "Improve code quality and performance",
            code_snippet=code.strip(),
            impact_category=AGENT_KNOWLEDGE_MAP.get(agent_role, {}).get("priority", "features"),
            estimated_impact=impact or "Medium",
            tests_required=tests,
            risk_level=risk if risk in ["low", "medium", "high"] else "low",
        )
    
    def _generate_template_suggestion(
        self,
        context: AgentContext,
        config: Dict
    ) -> AgentSuggestion:
        """Generate a template-based suggestion when Vertex AI is unavailable"""
        expertise = config.get("expertise", ["Code optimization"])
        priority = config.get("priority", "features")
        
        return AgentSuggestion(
            agent_role=context.agent_role,
            suggestion_id="",
            action=f"Review {context.current_file} for {expertise[0].lower()}",
            reasoning=f"Improves {priority} by applying {context.agent_role.value} best practices",
            impact_category=priority,
            estimated_impact="Medium - aligns with billionaire principles",
            tests_required=["Unit tests for changes"],
            risk_level="low",
        )
    
    def record_suggestion_outcome(
        self,
        suggestion_id: str,
        accepted: bool
    ):
        """
        Record whether a suggestion was accepted
        
        Args:
            suggestion_id: The suggestion ID
            accepted: Whether it was accepted by the user
        """
        for suggestion in self.suggestion_history:
            if suggestion.suggestion_id == suggestion_id:
                suggestion.accepted = accepted
                suggestion.accepted_at = datetime.now() if accepted else None
                
                # Update metrics
                metrics = self.agent_metrics[suggestion.agent_role]
                if accepted:
                    metrics["suggestions_accepted"] += 1
                
                total = metrics["suggestions_made"]
                if total > 0:
                    metrics["acceptance_rate"] = metrics["suggestions_accepted"] / total
                
                self._save_history()
                self._save_metrics()
                
                logger.info(
                    f"📝 Suggestion {suggestion_id} {'accepted' if accepted else 'rejected'} "
                    f"| Agent: {suggestion.agent_role.value} "
                    f"| Rate: {metrics['acceptance_rate']:.1%}"
                )
                return
        
        logger.warning(f"Suggestion {suggestion_id} not found in history")
    
    def get_top_performing_agents(self, top_n: int = 5) -> List[Tuple[AgentRole, Dict]]:
        """Get agents sorted by acceptance rate"""
        sorted_agents = sorted(
            self.agent_metrics.items(),
            key=lambda x: (x[1]["acceptance_rate"], x[1]["suggestions_made"]),
            reverse=True
        )
        return sorted_agents[:top_n]
    
    async def train_on_accepted_suggestions(self):
        """
        Self-improvement: Learn from accepted suggestions
        
        Adds accepted suggestion patterns to vector store for future RAG
        """
        accepted = [s for s in self.suggestion_history if s.accepted]
        
        if not accepted:
            logger.info("No accepted suggestions to train on")
            return
        
        logger.info(f"🎓 Training on {len(accepted)} accepted suggestions...")
        
        for suggestion in accepted[-100:]:  # Last 100 accepted
            try:
                # Add to vector store as a successful pattern
                await self.vector_store.add_conversation(
                    conversation_id=suggestion.suggestion_id,
                    user_message=suggestion.action,
                    agent_response=suggestion.code_snippet or suggestion.reasoning,
                    outcome="accepted",
                    industry=suggestion.impact_category,
                    language="code",
                    tenant_id="agent_brain",
                    intent=suggestion.agent_role.value,
                    metadata={
                        "reasoning": suggestion.reasoning,
                        "tests": suggestion.tests_required,
                        "risk": suggestion.risk_level,
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to embed suggestion: {e}")
        
        logger.info("✅ Agent brain training complete")
    
    def get_agent_report(self) -> Dict:
        """Generate a report on agent performance"""
        return {
            "total_suggestions": len(self.suggestion_history),
            "accepted_suggestions": sum(1 for s in self.suggestion_history if s.accepted),
            "overall_acceptance_rate": (
                sum(1 for s in self.suggestion_history if s.accepted) / 
                len(self.suggestion_history) if self.suggestion_history else 0
            ),
            "agent_metrics": {
                role.value: metrics 
                for role, metrics in self.agent_metrics.items()
            },
            "top_agents": [
                {"agent": role.value, **metrics}
                for role, metrics in self.get_top_performing_agents(5)
            ],
        }


# Singleton instance
_agent_brain_instance = None


def get_agent_brain() -> AgentBrain:
    """Get or create the singleton AgentBrain instance"""
    global _agent_brain_instance
    if _agent_brain_instance is None:
        _agent_brain_instance = AgentBrain()
    return _agent_brain_instance
