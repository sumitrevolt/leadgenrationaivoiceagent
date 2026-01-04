"""
ML Training API Endpoints
Manage and monitor ML training for the voice agent
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime

from app.ml import (
    get_training_scheduler,
    stop_training_scheduler,
    MLTrainingScheduler,
    TrainingScheduleConfig
)
from app.ml.auto_trainer import AutoTrainer
from app.ml.feedback_loop import FeedbackLoop
from app.ml.data_pipeline import ConversationDataPipeline
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/ml", tags=["ML Training"])


# Request/Response Models
class TrainingConfigUpdate(BaseModel):
    nightly_training_hour: Optional[int] = None
    nightly_training_minute: Optional[int] = None
    weekly_training_enabled: Optional[bool] = None
    min_conversations_for_training: Optional[int] = None


class ManualTrainingRequest(BaseModel):
    training_type: str = "nightly"  # "nightly" or "weekly"
    tenant_id: Optional[str] = "default"


class FeedbackSubmission(BaseModel):
    conversation_id: str
    outcome: str  # "appointment_booked", "callback", "interested", "not_interested", etc.
    call_duration: float
    notes: Optional[str] = None
    appointment_booked: bool = False
    callback_scheduled: bool = False


# Endpoints
@router.get("/status")
async def get_ml_status():
    """Get current ML system status"""
    
    try:
        scheduler = await get_training_scheduler()
        status = await scheduler.get_training_status()
        
        return {
            "status": "active",
            "ml_enabled": True,
            "scheduler": status
        }
    except Exception as e:
        logger.error(f"Failed to get ML status: {e}")
        return {
            "status": "error",
            "ml_enabled": False,
            "error": str(e)
        }


@router.get("/metrics")
async def get_ml_metrics():
    """Get ML training metrics and performance"""
    
    try:
        scheduler = await get_training_scheduler()
        metrics = await scheduler.get_training_metrics()
        
        return {
            "success": True,
            "metrics": metrics
        }
    except Exception as e:
        logger.error(f"Failed to get ML metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/train")
async def trigger_training(
    request: ManualTrainingRequest,
    background_tasks: BackgroundTasks
):
    """Manually trigger a training run"""
    
    try:
        scheduler = await get_training_scheduler(tenant_id=request.tenant_id)
        
        # Run training in background
        background_tasks.add_task(
            scheduler.run_training_now,
            training_type=request.training_type
        )
        
        return {
            "success": True,
            "message": f"{request.training_type} training started in background",
            "training_type": request.training_type
        }
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to trigger training: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback")
async def submit_call_feedback(feedback: FeedbackSubmission):
    """Submit call outcome feedback for ML learning"""
    
    try:
        feedback_loop = FeedbackLoop()
        data_pipeline = ConversationDataPipeline()
        
        # Record feedback
        await feedback_loop.record_call_feedback(
            conversation_id=feedback.conversation_id,
            outcome=feedback.outcome,
            duration=feedback.call_duration,
            appointment_booked=feedback.appointment_booked,
            callback_scheduled=feedback.callback_scheduled,
            notes=feedback.notes
        )
        
        return {
            "success": True,
            "message": "Feedback recorded for learning",
            "conversation_id": feedback.conversation_id
        }
    except Exception as e:
        logger.error(f"Failed to submit feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/insights")
async def get_ml_insights():
    """Get AI-generated insights from ML analysis"""
    
    try:
        feedback_loop = FeedbackLoop()
        
        insights = await feedback_loop.get_insights()
        
        return {
            "success": True,
            "insights": insights
        }
    except Exception as e:
        logger.error(f"Failed to get insights: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/best-responses")
async def get_best_responses(
    industry: Optional[str] = None,
    intent: Optional[str] = None,
    limit: int = 10
):
    """Get best performing response patterns"""
    
    try:
        feedback_loop = FeedbackLoop()
        
        responses = await feedback_loop.get_top_responses(
            industry=industry,
            intent_type=intent,
            limit=limit
        )
        
        return {
            "success": True,
            "responses": responses
        }
    except Exception as e:
        logger.error(f"Failed to get best responses: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/objection-handlers")
async def get_objection_handlers(industry: Optional[str] = None):
    """Get best objection handling responses by industry"""
    
    try:
        feedback_loop = FeedbackLoop()
        
        handlers = await feedback_loop.get_objection_handlers(industry=industry)
        
        return {
            "success": True,
            "objection_handlers": handlers
        }
    except Exception as e:
        logger.error(f"Failed to get objection handlers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/training-history")
async def get_training_history(limit: int = 20):
    """Get training run history"""
    
    try:
        scheduler = await get_training_scheduler()
        
        history = [
            {
                "run_id": r.run_id,
                "started_at": r.started_at.isoformat(),
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "status": r.status,
                "models_trained": r.models_trained,
                "improvements": r.improvements
            }
            for r in scheduler.training_history[-limit:]
        ]
        
        return {
            "success": True,
            "history": history
        }
    except Exception as e:
        logger.error(f"Failed to get training history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data-stats")
async def get_data_statistics():
    """Get statistics about training data"""
    
    try:
        data_pipeline = ConversationDataPipeline()
        stats = await data_pipeline.get_stats()
        
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Failed to get data stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ab-test")
async def create_ab_test(
    test_name: str,
    variants: List[str],
    metric: str = "success_rate"
):
    """Create a new A/B test for response variants"""
    
    try:
        feedback_loop = FeedbackLoop()
        
        test_id = await feedback_loop.create_ab_test(
            name=test_name,
            variants=variants,
            metric=metric
        )
        
        return {
            "success": True,
            "test_id": test_id,
            "message": f"A/B test '{test_name}' created with {len(variants)} variants"
        }
    except Exception as e:
        logger.error(f"Failed to create A/B test: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ab-test/{test_id}")
async def get_ab_test_results(test_id: str):
    """Get results for a specific A/B test"""
    
    try:
        feedback_loop = FeedbackLoop()
        
        results = await feedback_loop.get_ab_test_result(test_id)
        
        if not results:
            raise HTTPException(status_code=404, detail="A/B test not found")
        
        return {
            "success": True,
            "test_id": test_id,
            "results": results
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get A/B test results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scheduler/start")
async def start_scheduler():
    """Start the ML training scheduler"""
    
    try:
        scheduler = await get_training_scheduler()
        
        if scheduler.is_running:
            return {
                "success": True,
                "message": "Scheduler already running"
            }
        
        await scheduler.start()
        
        return {
            "success": True,
            "message": "ML training scheduler started"
        }
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scheduler/stop")
async def stop_scheduler():
    """Stop the ML training scheduler"""
    
    try:
        await stop_training_scheduler()
        
        return {
            "success": True,
            "message": "ML training scheduler stopped"
        }
    except Exception as e:
        logger.error(f"Failed to stop scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========================================
# BRAIN TRAINING API - Billionaire Mode
# ========================================

class BrainTrainingRequest(BaseModel):
    brain_type: str = "all"  # "all", "sub_agent", "voice_agent", "production"
    trigger: str = "scheduled"  # "scheduled", "behavior", "error_rate", "user_feedback"
    force: bool = False


class BrainFeedbackRequest(BaseModel):
    brain_type: str
    action: str
    accepted: bool
    feedback_score: Optional[float] = None


@router.get("/brain/status")
async def get_brain_training_status():
    """
    Get brain training status for all three brains
    
    Returns training history, behavior counts, and last training times.
    """
    try:
        from app.ml.brain_auto_trainer import get_brain_auto_trainer
        trainer = get_brain_auto_trainer()
        
        status = {
            "billionaire_mode": True,
            "last_training": {
                k: v.isoformat() for k, v in trainer.last_training.items()
            },
            "behavior_counts": {
                k: len(v) for k, v in trainer.behaviors.items()
            },
            "total_sessions": len(trainer.training_sessions),
            "brains": ["sub_agent", "voice_agent", "production"],
            "recent_sessions": [],
        }
        
        # Add last 10 training sessions
        for session in trainer.training_sessions[-10:]:
            status["recent_sessions"].append({
                "session_id": session.session_id,
                "brain_type": session.brain_type,
                "trigger": session.trigger.value,
                "status": session.status,
                "improvement": session.improvement,
                "behaviors_analyzed": session.behaviors_analyzed,
                "patterns_learned": session.patterns_learned,
                "web_searches": session.web_searches,
                "skills_enhanced": session.skills_enhanced,
                "started_at": session.started_at.isoformat(),
                "completed_at": session.completed_at.isoformat() if session.completed_at else None,
            })
        
        return {"success": True, "status": status}
        
    except Exception as e:
        logger.error(f"Failed to get brain training status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/brain/train")
async def train_brains(
    request: BrainTrainingRequest,
    background_tasks: BackgroundTasks
):
    """
    Trigger brain training manually
    
    Can train all brains or a specific brain.
    """
    try:
        if request.brain_type == "all":
            # Use Celery for all brains training
            from app.tasks.brain_training import train_all_brains
            task = train_all_brains.delay(force=request.force)
            
            return {
                "success": True,
                "message": "All brains training started",
                "task_id": task.id,
                "brain_type": "all",
            }
        else:
            # Train specific brain
            from app.tasks.brain_training import train_brain
            task = train_brain.delay(request.brain_type, request.trigger)
            
            return {
                "success": True,
                "message": f"{request.brain_type} brain training started",
                "task_id": task.id,
                "brain_type": request.brain_type,
            }
            
    except Exception as e:
        logger.error(f"Failed to trigger brain training: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/brain/train/now")
async def train_brains_immediate(request: BrainTrainingRequest):
    """
    Train brains immediately (synchronous, for testing)
    
    WARNING: This blocks the request until training completes.
    Use /brain/train for production workloads.
    """
    try:
        from app.ml.brain_orchestrator import get_brain_orchestrator
        orchestrator = get_brain_orchestrator()
        
        if not orchestrator.auto_trainer:
            raise HTTPException(status_code=503, detail="Brain auto-trainer not available")
        
        from app.ml.brain_auto_trainer import TrainingTrigger
        
        trigger_map = {
            "behavior": TrainingTrigger.BEHAVIOR,
            "performance": TrainingTrigger.PERFORMANCE,
            "scheduled": TrainingTrigger.SCHEDULED,
            "web_update": TrainingTrigger.WEB_UPDATE,
            "user_feedback": TrainingTrigger.USER_FEEDBACK,
            "error_rate": TrainingTrigger.ERROR_RATE,
        }
        trigger_enum = trigger_map.get(request.trigger, TrainingTrigger.SCHEDULED)
        
        results = {}
        
        if request.brain_type == "all":
            brain_types = ["sub_agent", "voice_agent", "production"]
        else:
            brain_types = [request.brain_type]
        
        for brain_type in brain_types:
            session = await orchestrator.auto_trainer.train_brain(brain_type, trigger_enum)
            results[brain_type] = {
                "session_id": session.session_id,
                "status": session.status,
                "improvement": session.improvement,
                "behaviors_analyzed": session.behaviors_analyzed,
                "patterns_learned": session.patterns_learned,
            }
        
        return {
            "success": True,
            "message": "Brain training completed",
            "results": results,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to train brains: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/brain/feedback")
async def record_brain_feedback(request: BrainFeedbackRequest):
    """
    Record user feedback for brain actions
    
    Used to improve brain training based on what users accept/reject.
    """
    try:
        from app.ml.brain_auto_trainer import get_brain_auto_trainer
        trainer = get_brain_auto_trainer()
        
        # Find matching behavior and update
        behaviors = trainer.behaviors.get(request.brain_type, [])
        updated = False
        
        for behavior in reversed(behaviors):
            if behavior.action == request.action and behavior.user_accepted is None:
                behavior.user_accepted = request.accepted
                behavior.feedback_score = request.feedback_score
                updated = True
                break
        
        if updated:
            logger.info(f"📝 Recorded feedback for {request.brain_type}/{request.action}: accepted={request.accepted}")
            return {
                "success": True,
                "message": "Feedback recorded",
                "brain_type": request.brain_type,
                "action": request.action,
                "accepted": request.accepted,
            }
        else:
            return {
                "success": False,
                "message": "No matching behavior found to update",
            }
            
    except Exception as e:
        logger.error(f"Failed to record feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/brain/metrics")
async def get_brain_metrics():
    """
    Get detailed brain training metrics
    
    Includes success rates, latency, and improvement trends.
    """
    try:
        from app.ml.brain_auto_trainer import get_brain_auto_trainer
        trainer = get_brain_auto_trainer()
        
        metrics = {
            "brains": {},
            "overall": {
                "total_behaviors": 0,
                "total_sessions": len(trainer.training_sessions),
                "avg_improvement": 0,
            }
        }
        
        total_improvement = 0
        completed_sessions = [s for s in trainer.training_sessions if s.status == "completed"]
        
        for brain_type in ["sub_agent", "voice_agent", "production"]:
            behaviors = trainer.behaviors.get(brain_type, [])
            sessions = [s for s in completed_sessions if s.brain_type == brain_type]
            
            # Calculate behavior metrics
            successful = [b for b in behaviors if b.success]
            accepted = [b for b in behaviors if b.user_accepted]
            
            brain_metrics = {
                "total_behaviors": len(behaviors),
                "success_rate": len(successful) / len(behaviors) if behaviors else 0,
                "acceptance_rate": len(accepted) / len([b for b in behaviors if b.user_accepted is not None]) if any(b.user_accepted is not None for b in behaviors) else 0,
                "avg_latency_ms": sum(b.latency_ms for b in behaviors) / len(behaviors) if behaviors else 0,
                "total_sessions": len(sessions),
                "avg_improvement": sum(s.improvement for s in sessions) / len(sessions) if sessions else 0,
                "last_trained": trainer.last_training.get(brain_type, None),
            }
            
            if brain_metrics["last_trained"]:
                brain_metrics["last_trained"] = brain_metrics["last_trained"].isoformat()
            
            metrics["brains"][brain_type] = brain_metrics
            metrics["overall"]["total_behaviors"] += len(behaviors)
            total_improvement += brain_metrics["avg_improvement"]
        
        metrics["overall"]["avg_improvement"] = total_improvement / 3
        
        return {"success": True, "metrics": metrics}
        
    except Exception as e:
        logger.error(f"Failed to get brain metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/brain/health")
async def get_brain_health():
    """
    Get health status of all three brains
    """
    try:
        from app.ml.brain_orchestrator import get_brain_orchestrator
        orchestrator = get_brain_orchestrator()
        
        health = {}
        for brain_type, brain_health in orchestrator.brain_health.items():
            health[brain_type.value] = {
                "status": brain_health.status.value,
                "last_used": brain_health.last_used.isoformat(),
                "requests_handled": brain_health.requests_handled,
                "avg_response_ms": round(brain_health.avg_response_ms, 2),
                "error_count": brain_health.error_count,
                "billionaire_mode": brain_health.billionaire_mode,
            }
        
        return {
            "success": True,
            "health": health,
            "billionaire_mode": orchestrator.billionaire_mode,
        }
        
    except Exception as e:
        logger.error(f"Failed to get brain health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# VERTEX AI PRODUCTION-READY CONTINUOUS TRAINING ENDPOINTS
# Billionaire Mode - Maximum AI Leverage for Project Readiness
# ============================================================================


class VertexTrainRequest(BaseModel):
    brain_type: str = "all"  # "all", "sub_agent", "voice_agent", "production"
    priority: int = 3  # 1=CRITICAL, 2=HIGH, 3=NORMAL, 4=LOW, 5=MAINTENANCE
    trigger_reason: str = "manual"


@router.get("/vertex/status")
async def get_vertex_training_status():
    """
    Get Vertex AI continuous training status
    
    Returns comprehensive status for production readiness:
    - Training configuration
    - Per-brain training status
    - Billionaire metrics (revenue impact, scale readiness)
    """
    try:
        from app.ml.vertex_continuous_trainer import get_vertex_continuous_trainer
        trainer = get_vertex_continuous_trainer()
        
        status = await trainer.get_training_status()
        return {
            "success": True,
            "production_ready": True,
            "status": status,
        }
        
    except Exception as e:
        logger.error(f"Failed to get Vertex status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vertex/train")
async def trigger_vertex_training(
    request: VertexTrainRequest,
    background_tasks: BackgroundTasks,
):
    """
    Trigger Vertex AI training for brains (async via Celery)
    
    BILLIONAIRE MODE: Uses Vertex AI for intelligent training with:
    - Behavior pattern analysis
    - Improvement generation aligned with revenue goals
    - Knowledge updates from latest best practices
    """
    try:
        from app.tasks.brain_training import vertex_train_all, vertex_train_brain
        
        if request.brain_type == "all":
            task = vertex_train_all.delay()
            return {
                "success": True,
                "message": "Vertex AI training started for ALL brains",
                "task_id": task.id,
                "billionaire_mode": True,
            }
        else:
            task = vertex_train_brain.delay(
                request.brain_type,
                request.priority,
                request.trigger_reason,
            )
            return {
                "success": True,
                "message": f"Vertex AI training started for {request.brain_type}",
                "task_id": task.id,
                "priority": request.priority,
            }
            
    except Exception as e:
        logger.error(f"Failed to trigger Vertex training: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vertex/train/now")
async def vertex_train_now(request: VertexTrainRequest):
    """
    Immediate Vertex AI training (synchronous)
    
    Use this for production-critical training needs.
    Runs training immediately and returns results.
    """
    try:
        from app.ml.vertex_continuous_trainer import get_vertex_continuous_trainer
        trainer = get_vertex_continuous_trainer()
        
        if request.brain_type == "all":
            results = await trainer.train_all_brains_now()
            return {
                "success": True,
                "message": "Vertex AI training completed for all brains",
                "results": results,
            }
        else:
            from app.ml.vertex_continuous_trainer import TrainingPriority
            priority_map = {
                1: TrainingPriority.CRITICAL,
                2: TrainingPriority.HIGH,
                3: TrainingPriority.NORMAL,
                4: TrainingPriority.LOW,
                5: TrainingPriority.MAINTENANCE,
            }
            priority = priority_map.get(request.priority, TrainingPriority.NORMAL)
            
            metrics = await trainer.train_brain_with_vertex(
                request.brain_type,
                priority,
                request.trigger_reason,
            )
            
            return {
                "success": True,
                "message": f"Vertex AI training completed for {request.brain_type}",
                "results": {
                    "brain_type": metrics.brain_type,
                    "improvement_percent": metrics.improvement_percent,
                    "training_duration_seconds": metrics.training_duration_seconds,
                    "vertex_calls": metrics.vertex_calls,
                    "behaviors_analyzed": metrics.behaviors_analyzed,
                    "patterns_discovered": metrics.patterns_discovered,
                    "skills_enhanced": metrics.skills_enhanced,
                    "revenue_impact_score": metrics.revenue_impact_score,
                    "scale_readiness_score": metrics.scale_readiness_score,
                    "automation_score": metrics.automation_score,
                },
            }
            
    except Exception as e:
        logger.error(f"Failed immediate Vertex training: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vertex/continuous/start")
async def start_vertex_continuous():
    """
    Start Vertex AI continuous training loop
    
    This enables 24/7 automated training with:
    - Health checks every 15 minutes
    - Auto-training when issues detected
    - Revenue-focused optimization
    """
    try:
        from app.ml.vertex_continuous_trainer import (
            get_vertex_continuous_trainer,
            start_continuous_training,
        )
        
        result = await start_continuous_training()
        return {
            "success": True,
            "message": "Vertex AI continuous training started",
            "billionaire_mode": True,
            "status": result,
        }
        
    except Exception as e:
        logger.error(f"Failed to start continuous training: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vertex/continuous/stop")
async def stop_vertex_continuous():
    """Stop Vertex AI continuous training loop"""
    try:
        from app.ml.vertex_continuous_trainer import stop_continuous_training
        
        result = await stop_continuous_training()
        return {
            "success": True,
            "message": "Vertex AI continuous training stopped",
            "status": result,
        }
        
    except Exception as e:
        logger.error(f"Failed to stop continuous training: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class VertexBehaviorRecord(BaseModel):
    brain_type: str
    action: str
    success: bool
    latency_ms: int
    user_accepted: Optional[bool] = None


@router.post("/vertex/behavior")
async def record_vertex_behavior(behavior: VertexBehaviorRecord):
    """
    Record a brain behavior for Vertex AI training
    
    This feeds the continuous training system with data
    to improve brain performance over time.
    """
    try:
        from app.ml.vertex_continuous_trainer import record_brain_behavior
        
        record_brain_behavior(
            brain_type=behavior.brain_type,
            action=behavior.action,
            success=behavior.success,
            latency_ms=behavior.latency_ms,
            user_accepted=behavior.user_accepted,
        )
        
        return {
            "success": True,
            "message": "Behavior recorded for training",
            "brain_type": behavior.brain_type,
            "action": behavior.action,
        }
        
    except Exception as e:
        logger.error(f"Failed to record behavior: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vertex/production-readiness")
async def get_production_readiness():
    """
    Get production readiness assessment for all brains
    
    BILLIONAIRE MINDSET: Ensure everything is ready for 10,000x scale
    
    Returns scores for:
    - Scale readiness (can handle 10,000x load)
    - Revenue impact (aligned with revenue goals)
    - Automation level (minimal manual intervention)
    - Training freshness (recently trained)
    """
    try:
        from app.ml.vertex_continuous_trainer import get_vertex_continuous_trainer
        trainer = get_vertex_continuous_trainer()
        
        status = await trainer.get_training_status()
        
        # Calculate overall production readiness
        brains = status.get("brains", {})
        total_ready = sum(1 for b in brains.values() if b.get("ready_for_production", False))
        all_trained = all(b.get("last_trained") for b in brains.values())
        
        # Get latest training metrics
        metrics = {}
        for brain_type in ["sub_agent", "voice_agent", "production"]:
            recent = [m for m in trainer.training_history if m.brain_type == brain_type][-1:]
            if recent:
                m = recent[0]
                metrics[brain_type] = {
                    "revenue_impact": m.revenue_impact_score,
                    "scale_readiness": m.scale_readiness_score,
                    "automation": m.automation_score,
                    "last_improvement": f"{m.improvement_percent:.1f}%",
                }
            else:
                metrics[brain_type] = {
                    "revenue_impact": 0.5,
                    "scale_readiness": 0.5,
                    "automation": 0.5,
                    "last_improvement": "N/A",
                }
        
        overall_score = (
            sum(m.get("revenue_impact", 0) for m in metrics.values()) +
            sum(m.get("scale_readiness", 0) for m in metrics.values()) +
            sum(m.get("automation", 0) for m in metrics.values())
        ) / 9  # 3 metrics * 3 brains
        
        return {
            "success": True,
            "production_ready": overall_score > 0.6 and all_trained,
            "overall_score": round(overall_score * 100, 1),
            "brains_ready": f"{total_ready}/3",
            "all_trained": all_trained,
            "billionaire_mode": True,
            "metrics": metrics,
            "recommendations": [
                "Run vertex/train/now to train all brains immediately" if not all_trained else None,
                "Start continuous training for 24/7 optimization" if not status.get("is_running") else None,
                "Scale readiness needs improvement" if overall_score < 0.7 else None,
            ],
        }
        
    except Exception as e:
        logger.error(f"Failed to get production readiness: {e}")
        raise HTTPException(status_code=500, detail=str(e))