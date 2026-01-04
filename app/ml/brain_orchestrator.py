"""
Brain Orchestrator - Coordinates the Three-Brain Architecture
Master Controller for the LeadGen AI Voice Agent Platform

The Three Brains:
1. Sub-Agent Brain (agent_brain.py) - Powers 13 specialized dev sub-agents
2. Voice Agent Brain (voice_agent_brain.py) - Handles real-time voice calls
3. Production Brain (production_brain.py) - Ensures operational excellence

This orchestrator:
- Routes requests to appropriate brain
- Coordinates cross-brain actions
- Manages brain health and failover
- Aggregates insights across brains
- Provides unified API for brain interactions
- AUTO-TRAINS brains based on behavior (Billionaire Mode)
- Deep web search for continuous learning
- MCP integration for enhanced capabilities
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class BrainType(Enum):
    """The three brains in our architecture"""
    SUB_AGENT = "sub_agent"       # Development assistance
    VOICE_AGENT = "voice_agent"   # Real-time calls
    PRODUCTION = "production"     # Operational excellence


class BrainStatus(Enum):
    """Brain operational status"""
    ACTIVE = "active"
    IDLE = "idle"
    BUSY = "busy"
    TRAINING = "training"         # Brain is being trained
    ERROR = "error"
    OFFLINE = "offline"


@dataclass
class BrainHealth:
    """Health status of a brain"""
    brain: BrainType
    status: BrainStatus
    last_used: datetime
    requests_handled: int
    avg_response_ms: float
    error_count: int
    details: Dict[str, Any]
    billionaire_mode: bool = True  # Always on


@dataclass
class BrainAction:
    """An action performed by a brain"""
    id: str
    brain: BrainType
    action_type: str
    input_summary: str
    output_summary: str
    success: bool
    duration_ms: int
    timestamp: datetime
    user_accepted: Optional[bool] = None  # For learning


class BrainOrchestrator:
    """
    Master Orchestrator for the Three-Brain Architecture
    
    BILLIONAIRE MODE ENABLED:
    - Routes requests, coordinates actions
    - Auto-trains brains based on behavior
    - Deep web search for knowledge updates
    - Applies billionaire mindset to all decisions
    
    Usage:
    ```python
    orchestrator = get_brain_orchestrator()
    
    # Route to appropriate brain
    response = await orchestrator.route_request(request_type, data)
    
    # Get unified insights
    insights = await orchestrator.get_unified_insights()
    
    # Train all brains
    await orchestrator.train_all_brains_now()
    
    # Health dashboard
    health = await orchestrator.get_all_brain_health()
    ```
    """
    
    def __init__(self):
        self._sub_agent_brain = None
        self._voice_agent_brain = None
        self._production_brain = None
        self._auto_trainer = None
        
        # Billionaire mode enabled
        self.billionaire_mode = True
        
        # Tracking
        self.brain_health: Dict[BrainType, BrainHealth] = {}
        self.action_history: List[BrainAction] = []
        
        # Initialize health tracking
        for brain_type in BrainType:
            self.brain_health[brain_type] = BrainHealth(
                brain=brain_type,
                status=BrainStatus.IDLE,
                last_used=datetime.now(),
                requests_handled=0,
                avg_response_ms=0,
                error_count=0,
                details={},
                billionaire_mode=True,
            )
        
        logger.info("🧠 Brain Orchestrator initialized - Three-Brain Architecture ready (BILLIONAIRE MODE)")
    
    @property
    def auto_trainer(self):
        """Lazy load Brain Auto-Trainer"""
        if self._auto_trainer is None:
            try:
                from app.ml.brain_auto_trainer import get_brain_auto_trainer
                self._auto_trainer = get_brain_auto_trainer()
                logger.info("🎓 Brain Auto-Trainer connected")
            except Exception as e:
                logger.warning(f"Failed to load Auto-Trainer: {e}")
        return self._auto_trainer
    
    @property
    def sub_agent_brain(self):
        """Lazy load Sub-Agent Brain (Brain #1)"""
        if self._sub_agent_brain is None:
            try:
                from app.ml.agent_brain import get_agent_brain
                self._sub_agent_brain = get_agent_brain()
                logger.info("🤖 Sub-Agent Brain connected")
            except Exception as e:
                logger.error(f"Failed to load Sub-Agent Brain: {e}")
        return self._sub_agent_brain
    
    @property
    def voice_agent_brain(self):
        """Lazy load Voice Agent Brain (Brain #2)"""
        if self._voice_agent_brain is None:
            try:
                from app.ml.voice_agent_brain import get_voice_agent_brain
                self._voice_agent_brain = get_voice_agent_brain()
                logger.info("📞 Voice Agent Brain connected")
            except Exception as e:
                logger.error(f"Failed to load Voice Agent Brain: {e}")
        return self._voice_agent_brain
    
    @property
    def production_brain(self):
        """Lazy load Production Brain (Brain #3)"""
        if self._production_brain is None:
            try:
                from app.ml.production_brain import get_production_brain
                self._production_brain = get_production_brain()
                logger.info("🏭 Production Brain connected")
            except Exception as e:
                logger.error(f"Failed to load Production Brain: {e}")
        return self._production_brain
    
    async def route_request(
        self,
        request_type: str,
        data: Dict[str, Any],
        preferred_brain: Optional[BrainType] = None,
    ) -> Dict[str, Any]:
        """
        Route a request to the appropriate brain based on type.
        
        Args:
            request_type: Type of request (e.g., "code_suggestion", "start_call", "health_check")
            data: Request data
            preferred_brain: Optional preferred brain to use
            
        Returns:
            Response from the appropriate brain
        """
        import time
        import uuid
        
        start_time = time.time()
        action_id = str(uuid.uuid4())[:8]
        
        # Determine which brain to use
        brain_type = preferred_brain or self._determine_brain(request_type)
        
        # Update brain status
        self.brain_health[brain_type].status = BrainStatus.BUSY
        
        try:
            response = await self._execute_on_brain(brain_type, request_type, data)
            success = True
            
        except Exception as e:
            logger.error(f"Brain {brain_type.value} failed: {e}")
            response = {"error": str(e), "brain": brain_type.value}
            success = False
            self.brain_health[brain_type].error_count += 1
        
        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Update health tracking
        health = self.brain_health[brain_type]
        health.status = BrainStatus.IDLE
        health.last_used = datetime.now()
        health.requests_handled += 1
        
        # Update rolling average
        total_ms = health.avg_response_ms * (health.requests_handled - 1) + duration_ms
        health.avg_response_ms = total_ms / health.requests_handled
        
        # Record action
        action = BrainAction(
            id=action_id,
            brain=brain_type,
            action_type=request_type,
            input_summary=str(data)[:100],
            output_summary=str(response)[:100],
            success=success,
            duration_ms=duration_ms,
            timestamp=datetime.now(),
        )
        self.action_history.append(action)
        
        # Keep last 1000 actions
        self.action_history = self.action_history[-1000:]
        
        # Record behavior for auto-training (Billionaire Mode)
        if self.auto_trainer:
            self.auto_trainer.record_behavior(
                brain_type=brain_type.value,
                action=request_type,
                input_data=data,
                output_data=response,
                success=success,
                latency_ms=duration_ms,
            )
        
        return response
    
    def _determine_brain(self, request_type: str) -> BrainType:
        """Determine which brain should handle a request type"""
        
        # Sub-Agent Brain requests (development assistance)
        sub_agent_requests = {
            "code_suggestion", "detect_agent", "project_context",
            "file_analysis", "code_review", "refactoring",
            "test_generation", "documentation",
        }
        
        # Voice Agent Brain requests (real-time calls)
        voice_agent_requests = {
            "start_call", "end_call", "process_speech",
            "generate_greeting", "handle_objection",
            "schedule_appointment", "call_transfer",
        }
        
        # Production Brain requests (operational)
        production_requests = {
            "health_check", "metrics_analysis", "scaling_recommendation",
            "cost_optimization", "production_readiness", "growth_insights",
            "alert_management", "dashboard_data",
        }
        
        if request_type in sub_agent_requests:
            return BrainType.SUB_AGENT
        elif request_type in voice_agent_requests:
            return BrainType.VOICE_AGENT
        elif request_type in production_requests:
            return BrainType.PRODUCTION
        else:
            # Default to production brain for unknown requests
            logger.warning(f"Unknown request type '{request_type}', routing to Production Brain")
            return BrainType.PRODUCTION
    
    async def _execute_on_brain(
        self,
        brain_type: BrainType,
        request_type: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a request on a specific brain"""
        
        if brain_type == BrainType.SUB_AGENT:
            return await self._execute_sub_agent(request_type, data)
            
        elif brain_type == BrainType.VOICE_AGENT:
            return await self._execute_voice_agent(request_type, data)
            
        elif brain_type == BrainType.PRODUCTION:
            return await self._execute_production(request_type, data)
        
        raise ValueError(f"Unknown brain type: {brain_type}")
    
    async def _execute_sub_agent(self, request_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute request on Sub-Agent Brain"""
        brain = self.sub_agent_brain
        if not brain:
            raise RuntimeError("Sub-Agent Brain not available")
        
        if request_type == "detect_agent":
            file_path = data.get("file_path", "")
            content = data.get("content", "")
            agents = brain.detect_agent(file_path, content)
            return {"agents": [a.value for a in agents]}
        
        elif request_type == "code_suggestion":
            file_path = data.get("file_path", "")
            content = data.get("content", "")
            cursor_position = data.get("cursor_position", 0)
            
            suggestion = await brain.generate_suggestion(
                file_path=file_path,
                content=content,
                cursor_position=cursor_position,
            )
            
            return {
                "suggestion": suggestion.suggestion if suggestion else None,
                "agent": suggestion.agent.value if suggestion else None,
                "confidence": suggestion.confidence if suggestion else 0,
            }
        
        elif request_type == "project_context":
            file_path = data.get("file_path", "")
            context = await brain.get_project_context(file_path)
            return {"context": context}
        
        return {"error": f"Unknown sub-agent request: {request_type}"}
    
    async def _execute_voice_agent(self, request_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute request on Voice Agent Brain"""
        brain = self.voice_agent_brain
        if not brain:
            raise RuntimeError("Voice Agent Brain not available")
        
        if request_type == "start_call":
            call_state = await brain.start_call(
                call_id=data.get("call_id", ""),
                lead_id=data.get("lead_id", ""),
                lead_name=data.get("lead_name", ""),
                lead_phone=data.get("lead_phone", ""),
                company_name=data.get("company_name"),
                industry=data.get("industry", "general"),
                campaign_id=data.get("campaign_id"),
                custom_script=data.get("custom_script"),
            )
            return {
                "call_id": call_state.call_id,
                "state": "active",
                "industry": call_state.industry,
            }
        
        elif request_type == "generate_greeting":
            call_id = data.get("call_id", "")
            response = await brain.generate_greeting(call_id)
            return {
                "text": response.text,
                "emotion": response.emotion,
                "intent": response.next_expected_intent.value if response.next_expected_intent else None,
            }
        
        elif request_type == "process_speech":
            call_id = data.get("call_id", "")
            customer_text = data.get("customer_text", "")
            response = await brain.process_customer_speech(call_id, customer_text)
            return {
                "text": response.text,
                "action": response.action,
                "emotion": response.emotion,
                "detected_intent": response.detected_intent.value if response.detected_intent else None,
            }
        
        elif request_type == "end_call":
            call_id = data.get("call_id", "")
            outcome = data.get("outcome", "completed")
            notes = data.get("notes", "")
            result = await brain.end_call(call_id, outcome, notes)
            return result
        
        return {"error": f"Unknown voice agent request: {request_type}"}
    
    async def _execute_production(self, request_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute request on Production Brain"""
        brain = self.production_brain
        if not brain:
            raise RuntimeError("Production Brain not available")
        
        if request_type == "health_check":
            health_checks = await brain.run_health_checks()
            return {
                "checks": {
                    name: {
                        "status": check.status.value,
                        "message": check.message,
                        "latency_ms": check.latency_ms,
                    }
                    for name, check in health_checks.items()
                }
            }
        
        elif request_type == "metrics_analysis":
            from app.ml.production_brain import SystemMetrics
            metrics = SystemMetrics(**data.get("metrics", {}))
            recommendations = await brain.analyze_metrics(metrics)
            return {
                "recommendations": [
                    {
                        "id": rec.id,
                        "type": rec.type.value,
                        "priority": rec.priority,
                        "title": rec.title,
                        "description": rec.description,
                        "action": rec.action_required,
                    }
                    for rec in recommendations
                ]
            }
        
        elif request_type == "production_readiness":
            result = await brain.run_production_readiness_check()
            return result
        
        elif request_type == "growth_insights":
            insights = await brain.get_growth_insights()
            return insights
        
        elif request_type == "dashboard_data":
            return brain.get_dashboard_data()
        
        return {"error": f"Unknown production request: {request_type}"}
    
    async def get_all_brain_health(self) -> Dict[str, Any]:
        """Get health status of all brains"""
        return {
            brain_type.value: {
                "status": health.status.value,
                "last_used": health.last_used.isoformat(),
                "requests_handled": health.requests_handled,
                "avg_response_ms": round(health.avg_response_ms, 2),
                "error_count": health.error_count,
                "uptime_score": self._calculate_uptime_score(health),
            }
            for brain_type, health in self.brain_health.items()
        }
    
    def _calculate_uptime_score(self, health: BrainHealth) -> float:
        """Calculate uptime score (0-100) based on health metrics"""
        if health.requests_handled == 0:
            return 100.0
        
        error_rate = health.error_count / health.requests_handled
        uptime = max(0, 100 - (error_rate * 100))
        
        # Penalize high latency
        if health.avg_response_ms > 5000:
            uptime *= 0.8
        elif health.avg_response_ms > 3000:
            uptime *= 0.9
        
        return round(uptime, 1)
    
    async def get_unified_insights(self) -> Dict[str, Any]:
        """Get unified insights from all three brains"""
        insights = {
            "timestamp": datetime.now().isoformat(),
            "brain_health": await self.get_all_brain_health(),
            "insights": {},
        }
        
        # Get production insights
        try:
            production_insights = await self.route_request("growth_insights", {})
            insights["insights"]["growth"] = production_insights
        except Exception as e:
            logger.warning(f"Failed to get production insights: {e}")
        
        # Get production readiness
        try:
            readiness = await self.route_request("production_readiness", {})
            insights["insights"]["production_readiness"] = {
                "score": readiness.get("overall_score", 0),
                "passed": len(readiness.get("passed", [])),
                "failed": len(readiness.get("failed", [])),
            }
        except Exception as e:
            logger.warning(f"Failed to get readiness: {e}")
        
        # Get recent action summary
        recent_actions = [a for a in self.action_history if a.timestamp > datetime.now() - timedelta(hours=1)]
        insights["recent_activity"] = {
            "actions_last_hour": len(recent_actions),
            "by_brain": {
                brain_type.value: len([a for a in recent_actions if a.brain == brain_type])
                for brain_type in BrainType
            },
            "success_rate": (
                len([a for a in recent_actions if a.success]) / len(recent_actions) * 100
                if recent_actions else 100
            ),
        }
        
        return insights
    
    async def coordinate_brains(
        self,
        task: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Coordinate multiple brains for complex tasks.
        
        Example: Before deploying, check production readiness and run code review.
        """
        results = {}
        
        if task == "pre_deployment":
            # Run production readiness check
            results["production_readiness"] = await self.route_request(
                "production_readiness", {}
            )
            
            # Get health status
            results["health_checks"] = await self.route_request(
                "health_check", {}
            )
            
            # Summary
            readiness_score = results["production_readiness"].get("overall_score", 0)
            all_healthy = all(
                c["status"] == "healthy"
                for c in results["health_checks"].get("checks", {}).values()
            )
            
            results["ready_to_deploy"] = readiness_score > 90 and all_healthy
            results["summary"] = (
                "✅ Ready to deploy!" if results["ready_to_deploy"]
                else f"⚠️ Not ready: readiness={readiness_score:.0f}%, healthy={all_healthy}"
            )
        
        elif task == "daily_report":
            # Get insights from all brains
            results["growth_insights"] = await self.route_request("growth_insights", {})
            results["health"] = await self.get_all_brain_health()
            results["activity"] = {
                "actions_today": len([
                    a for a in self.action_history
                    if a.timestamp.date() == datetime.now().date()
                ]),
            }
        
        return results
    
    def get_brain_statistics(self) -> Dict[str, Any]:
        """Get detailed statistics about brain usage"""
        # Group actions by brain
        by_brain = {}
        for brain_type in BrainType:
            brain_actions = [a for a in self.action_history if a.brain == brain_type]
            
            by_brain[brain_type.value] = {
                "total_actions": len(brain_actions),
                "successful": len([a for a in brain_actions if a.success]),
                "failed": len([a for a in brain_actions if not a.success]),
                "avg_duration_ms": (
                    sum(a.duration_ms for a in brain_actions) / len(brain_actions)
                    if brain_actions else 0
                ),
                "action_types": list(set(a.action_type for a in brain_actions)),
            }
        
        return {
            "period": "all_time",
            "total_actions": len(self.action_history),
            "by_brain": by_brain,
            "billionaire_mode": self.billionaire_mode,
        }
    
    async def train_all_brains_now(self) -> Dict[str, Any]:
        """
        Immediately train all three brains (Billionaire Mode).
        Uses behavior analysis, web search, and skill enhancement.
        """
        if not self.auto_trainer:
            return {"error": "Auto-trainer not available"}
        
        logger.info("🚀 Starting immediate training for all brains (Billionaire Mode)")
        
        # Mark all brains as training
        for brain_type in BrainType:
            self.brain_health[brain_type].status = BrainStatus.TRAINING
        
        try:
            from app.ml.brain_auto_trainer import TrainingTrigger
            results = await self.auto_trainer.train_all_brains(TrainingTrigger.BEHAVIOR)
            
            return {
                "success": True,
                "sessions": {
                    brain: {
                        "session_id": session.session_id,
                        "improvement": f"{session.improvement:.1%}",
                        "patterns_learned": session.patterns_learned,
                        "web_searches": session.web_searches,
                        "status": session.status,
                    }
                    for brain, session in results.items()
                },
                "billionaire_mode": True,
            }
        finally:
            # Reset brain status
            for brain_type in BrainType:
                self.brain_health[brain_type].status = BrainStatus.IDLE
    
    async def train_single_brain(self, brain_type: str) -> Dict[str, Any]:
        """Train a specific brain immediately"""
        if not self.auto_trainer:
            return {"error": "Auto-trainer not available"}
        
        from app.ml.brain_auto_trainer import TrainingTrigger
        session = await self.auto_trainer.train_brain(brain_type, TrainingTrigger.BEHAVIOR)
        
        return {
            "success": True,
            "session_id": session.session_id,
            "improvement": f"{session.improvement:.1%}",
            "patterns_learned": session.patterns_learned,
            "skills_enhanced": session.skills_enhanced,
        }
    
    async def enhance_brain_skills(self, brain_type: str, skills: List[str]) -> Dict[str, Any]:
        """Enhance specific skills in a brain"""
        if not self.auto_trainer:
            return {"error": "Auto-trainer not available"}
        
        from app.ml.brain_auto_trainer import SkillCategory
        skill_enums = [SkillCategory(s) for s in skills if s in [e.value for e in SkillCategory]]
        
        return await self.auto_trainer.enhance_skills(brain_type, skill_enums)
    
    def get_training_report(self) -> Dict[str, Any]:
        """Get comprehensive training report"""
        if not self.auto_trainer:
            return {"error": "Auto-trainer not available"}
        
        return self.auto_trainer.get_training_report()
    
    def record_user_feedback(
        self,
        action_id: str,
        accepted: bool,
        feedback_score: Optional[float] = None,
    ):
        """Record user feedback for an action (for learning)"""
        # Find the action
        for action in self.action_history:
            if action.id == action_id:
                action.user_accepted = accepted
                
                # Also record in auto-trainer
                if self.auto_trainer:
                    self.auto_trainer.record_behavior(
                        brain_type=action.brain.value,
                        action=action.action_type,
                        input_data=action.input_summary,
                        output_data=action.output_summary,
                        success=action.success,
                        latency_ms=action.duration_ms,
                        user_accepted=accepted,
                        feedback_score=feedback_score,
                    )
                break


# Singleton instance
_orchestrator_instance = None


def get_brain_orchestrator() -> BrainOrchestrator:
    """Get or create the singleton BrainOrchestrator instance"""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = BrainOrchestrator()
    return _orchestrator_instance


# Convenience functions for direct brain access
async def ask_sub_agent(file_path: str, content: str, **kwargs) -> Dict[str, Any]:
    """Quick helper to get a code suggestion from Sub-Agent Brain"""
    orchestrator = get_brain_orchestrator()
    return await orchestrator.route_request("code_suggestion", {
        "file_path": file_path,
        "content": content,
        **kwargs,
    })


async def start_voice_call(call_id: str, lead_id: str, lead_name: str, **kwargs) -> Dict[str, Any]:
    """Quick helper to start a call with Voice Agent Brain"""
    orchestrator = get_brain_orchestrator()
    return await orchestrator.route_request("start_call", {
        "call_id": call_id,
        "lead_id": lead_id,
        "lead_name": lead_name,
        **kwargs,
    })


async def check_production_health() -> Dict[str, Any]:
    """Quick helper to check production health"""
    orchestrator = get_brain_orchestrator()
    return await orchestrator.route_request("health_check", {})


async def get_growth_insights() -> Dict[str, Any]:
    """Quick helper to get growth insights"""
    orchestrator = get_brain_orchestrator()
    return await orchestrator.route_request("growth_insights", {})


async def train_all_brains_now() -> Dict[str, Any]:
    """Quick helper to train all brains immediately (Billionaire Mode)"""
    orchestrator = get_brain_orchestrator()
    return await orchestrator.train_all_brains_now()


async def train_brain(brain_type: str) -> Dict[str, Any]:
    """Quick helper to train a specific brain"""
    orchestrator = get_brain_orchestrator()
    return await orchestrator.train_single_brain(brain_type)


def get_training_status() -> Dict[str, Any]:
    """Quick helper to get training status"""
    orchestrator = get_brain_orchestrator()
    return orchestrator.get_training_report()


def record_feedback(action_id: str, accepted: bool, score: Optional[float] = None):
    """Record user feedback for brain learning"""
    orchestrator = get_brain_orchestrator()
    orchestrator.record_user_feedback(action_id, accepted, score)
