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