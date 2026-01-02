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
