"""
Brain Training Celery Tasks
Continuous, Automated Brain Training for the Three-Brain Architecture

This module provides:
- Scheduled brain training every 6 hours
- On-demand training via Celery tasks
- Behavior-based training triggers
- Web knowledge updates
- Training metrics and reporting

BILLIONAIRE MODE: Trains brains to think and act like billionaires
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import json
from pathlib import Path

from celery import shared_task

from app.worker import celery_app
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Training data directory
TRAINING_DATA_DIR = Path("data/brain_training")
TRAINING_DATA_DIR.mkdir(parents=True, exist_ok=True)


def run_async(coro):
    """Run async coroutine in sync context"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    name="app.tasks.brain_training.train_all_brains",
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
    autoretry_for=(Exception,),
    acks_late=True,
)
def train_all_brains(self, force: bool = False) -> Dict[str, Any]:
    """
    Train all three brains (Sub-Agent, Voice Agent, Production)
    
    This is the main training task that runs every 6 hours.
    It coordinates training across all brains and ensures
    continuous improvement.
    
    Args:
        force: Force training even if not enough behaviors collected
        
    Returns:
        Training results for all brains
    """
    logger.info("🎓 Starting ALL BRAINS training (Celery scheduled)")
    
    try:
        from app.ml.brain_orchestrator import get_brain_orchestrator
        orchestrator = get_brain_orchestrator()
        
        # Run the async training
        results = run_async(_train_all_brains_async(orchestrator, force))
        
        # Save training report
        _save_training_report("all_brains", results)
        
        logger.info(f"✅ ALL BRAINS training completed: {results}")
        return results
        
    except Exception as e:
        logger.error(f"❌ Brain training failed: {e}")
        raise self.retry(exc=e)


async def _train_all_brains_async(orchestrator, force: bool) -> Dict[str, Any]:
    """Async implementation of brain training"""
    results = {
        "started_at": datetime.now().isoformat(),
        "brains": {},
        "total_improvement": 0,
        "status": "running",
    }
    
    brain_types = ["sub_agent", "voice_agent", "production"]
    
    for brain_type in brain_types:
        try:
            if orchestrator.auto_trainer:
                from app.ml.brain_auto_trainer import TrainingTrigger
                session = await orchestrator.auto_trainer.train_brain(
                    brain_type=brain_type,
                    trigger=TrainingTrigger.SCHEDULED,
                )
                
                results["brains"][brain_type] = {
                    "status": session.status,
                    "behaviors_analyzed": session.behaviors_analyzed,
                    "patterns_learned": session.patterns_learned,
                    "web_searches": session.web_searches,
                    "improvement": session.improvement,
                    "skills_enhanced": session.skills_enhanced,
                }
                results["total_improvement"] += session.improvement
            else:
                results["brains"][brain_type] = {"status": "trainer_not_available"}
                
        except Exception as e:
            logger.error(f"Brain {brain_type} training failed: {e}")
            results["brains"][brain_type] = {"status": "failed", "error": str(e)}
    
    results["completed_at"] = datetime.now().isoformat()
    results["status"] = "completed"
    results["total_improvement"] /= len(brain_types) if brain_types else 1
    
    return results


@celery_app.task(
    bind=True,
    name="app.tasks.brain_training.train_brain",
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    acks_late=True,
)
def train_brain(self, brain_type: str, trigger: str = "scheduled") -> Dict[str, Any]:
    """
    Train a specific brain
    
    Args:
        brain_type: One of 'sub_agent', 'voice_agent', 'production'
        trigger: Training trigger type
        
    Returns:
        Training session results
    """
    logger.info(f"🎓 Starting {brain_type} brain training (trigger: {trigger})")
    
    try:
        from app.ml.brain_auto_trainer import get_brain_auto_trainer, TrainingTrigger
        trainer = get_brain_auto_trainer()
        
        # Map string trigger to enum
        trigger_map = {
            "behavior": TrainingTrigger.BEHAVIOR,
            "performance": TrainingTrigger.PERFORMANCE,
            "scheduled": TrainingTrigger.SCHEDULED,
            "web_update": TrainingTrigger.WEB_UPDATE,
            "user_feedback": TrainingTrigger.USER_FEEDBACK,
            "error_rate": TrainingTrigger.ERROR_RATE,
        }
        trigger_enum = trigger_map.get(trigger, TrainingTrigger.SCHEDULED)
        
        # Run async training
        session = run_async(trainer.train_brain(brain_type, trigger_enum))
        
        result = {
            "session_id": session.session_id,
            "brain_type": brain_type,
            "trigger": trigger,
            "status": session.status,
            "behaviors_analyzed": session.behaviors_analyzed,
            "patterns_learned": session.patterns_learned,
            "web_searches": session.web_searches,
            "improvement": session.improvement,
            "skills_enhanced": session.skills_enhanced,
            "started_at": session.started_at.isoformat(),
            "completed_at": session.completed_at.isoformat() if session.completed_at else None,
        }
        
        _save_training_report(brain_type, result)
        
        logger.info(f"✅ {brain_type} training completed: {session.improvement:.1%} improvement")
        return result
        
    except Exception as e:
        logger.error(f"❌ Brain training failed: {e}")
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    name="app.tasks.brain_training.continuous_training_check",
    max_retries=1,
    acks_late=True,
)
def continuous_training_check(self) -> Dict[str, Any]:
    """
    Continuous training health check - runs every hour
    
    Checks if any brain needs immediate training based on:
    - Error rate threshold (>10%)
    - User feedback rejection rate (>30%)
    - Performance degradation
    
    Triggers immediate training if needed.
    """
    logger.info("🔍 Running continuous training check...")
    
    try:
        from app.ml.brain_auto_trainer import get_brain_auto_trainer
        trainer = get_brain_auto_trainer()
        
        brains_to_train = []
        checks = {}
        
        for brain_type in ["sub_agent", "voice_agent", "production"]:
            behaviors = trainer.behaviors.get(brain_type, [])
            recent = [b for b in behaviors if b.timestamp > datetime.now() - timedelta(hours=1)]
            
            check_result = {
                "total_behaviors": len(behaviors),
                "recent_behaviors": len(recent),
                "needs_training": False,
                "reason": None,
            }
            
            if len(recent) >= 10:
                # Check error rate
                error_rate = len([b for b in recent if not b.success]) / len(recent)
                check_result["error_rate"] = error_rate
                
                if error_rate > 0.1:
                    check_result["needs_training"] = True
                    check_result["reason"] = f"High error rate: {error_rate:.1%}"
                    brains_to_train.append((brain_type, "error_rate"))
                
                # Check rejection rate
                feedback_behaviors = [b for b in recent if b.user_accepted is not None]
                if len(feedback_behaviors) >= 5:
                    rejection_rate = len([b for b in feedback_behaviors if not b.user_accepted]) / len(feedback_behaviors)
                    check_result["rejection_rate"] = rejection_rate
                    
                    if rejection_rate > 0.3 and check_result["reason"] is None:
                        check_result["needs_training"] = True
                        check_result["reason"] = f"High rejection rate: {rejection_rate:.1%}"
                        brains_to_train.append((brain_type, "user_feedback"))
            
            checks[brain_type] = check_result
        
        # Trigger training for brains that need it
        training_triggered = []
        for brain_type, trigger in brains_to_train:
            logger.info(f"⚡ Triggering immediate training for {brain_type} (reason: {trigger})")
            train_brain.delay(brain_type, trigger)
            training_triggered.append(brain_type)
        
        result = {
            "checked_at": datetime.now().isoformat(),
            "checks": checks,
            "training_triggered": training_triggered,
        }
        
        logger.info(f"✅ Continuous training check completed. Triggered: {training_triggered}")
        return result
        
    except Exception as e:
        logger.error(f"❌ Continuous training check failed: {e}")
        return {"error": str(e), "checked_at": datetime.now().isoformat()}


@celery_app.task(
    bind=True,
    name="app.tasks.brain_training.web_knowledge_update",
    max_retries=2,
    default_retry_delay=600,
    acks_late=True,
)
def web_knowledge_update(self) -> Dict[str, Any]:
    """
    Update brains with latest web knowledge
    
    Performs deep web search for each brain's topics and
    incorporates new knowledge into brain training.
    
    Runs daily at 4 AM.
    """
    logger.info("🌐 Starting web knowledge update for all brains...")
    
    try:
        from app.ml.brain_auto_trainer import get_brain_auto_trainer
        trainer = get_brain_auto_trainer()
        
        results = {}
        for brain_type in ["sub_agent", "voice_agent", "production"]:
            try:
                knowledge = run_async(trainer._deep_web_search(brain_type))
                results[brain_type] = {
                    "status": "success",
                    "topics_searched": len(knowledge),
                    "knowledge_items": len(knowledge),
                }
            except Exception as e:
                results[brain_type] = {"status": "failed", "error": str(e)}
        
        logger.info(f"✅ Web knowledge update completed: {results}")
        return {
            "updated_at": datetime.now().isoformat(),
            "results": results,
        }
        
    except Exception as e:
        logger.error(f"❌ Web knowledge update failed: {e}")
        raise self.retry(exc=e)


@celery_app.task(
    name="app.tasks.brain_training.get_training_status",
)
def get_training_status() -> Dict[str, Any]:
    """
    Get current training status for all brains
    
    Returns:
        Training status including last training times,
        behavior counts, and recent training sessions
    """
    try:
        from app.ml.brain_auto_trainer import get_brain_auto_trainer
        trainer = get_brain_auto_trainer()
        
        status = {
            "last_training": {
                k: v.isoformat() for k, v in trainer.last_training.items()
            },
            "behavior_counts": {
                k: len(v) for k, v in trainer.behaviors.items()
            },
            "total_sessions": len(trainer.training_sessions),
            "recent_sessions": [],
        }
        
        # Add last 5 training sessions
        for session in trainer.training_sessions[-5:]:
            status["recent_sessions"].append({
                "session_id": session.session_id,
                "brain_type": session.brain_type,
                "trigger": session.trigger.value,
                "status": session.status,
                "improvement": session.improvement,
                "completed_at": session.completed_at.isoformat() if session.completed_at else None,
            })
        
        return status
        
    except Exception as e:
        logger.error(f"Failed to get training status: {e}")
        return {"error": str(e)}


@celery_app.task(
    name="app.tasks.brain_training.record_feedback",
)
def record_feedback(
    brain_type: str,
    action: str,
    accepted: bool,
    feedback_score: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Record user feedback for a brain action
    
    Used to improve brain training based on what users accept/reject.
    
    Args:
        brain_type: Which brain performed the action
        action: Action type
        accepted: Whether user accepted the suggestion
        feedback_score: Optional 0-1 score
        
    Returns:
        Confirmation of feedback recording
    """
    try:
        from app.ml.brain_auto_trainer import get_brain_auto_trainer
        from app.ml.vertex_continuous_trainer import record_brain_behavior
        
        trainer = get_brain_auto_trainer()
        
        # Find most recent behavior of this type and update
        behaviors = trainer.behaviors.get(brain_type, [])
        for behavior in reversed(behaviors):
            if behavior.action == action and behavior.user_accepted is None:
                behavior.user_accepted = accepted
                behavior.feedback_score = feedback_score
                
                # Also record in Vertex trainer
                record_brain_behavior(
                    brain_type=brain_type,
                    action=action,
                    success=accepted,
                    latency_ms=behavior.latency_ms,
                    user_accepted=accepted,
                )
                
                logger.info(f"📝 Recorded feedback for {brain_type}/{action}: accepted={accepted}")
                
                return {
                    "status": "recorded",
                    "brain_type": brain_type,
                    "action": action,
                    "accepted": accepted,
                    "feedback_score": feedback_score,
                }
        
        return {"status": "no_matching_behavior_found"}
        
    except Exception as e:
        logger.error(f"Failed to record feedback: {e}")
        return {"error": str(e)}


# ============================================================================
# PRODUCTION-READY VERTEX AI CONTINUOUS TRAINING TASKS
# ============================================================================

@celery_app.task(
    bind=True,
    name="app.tasks.brain_training.vertex_train_all",
    max_retries=3,
    default_retry_delay=300,
    autoretry_for=(Exception,),
    acks_late=True,
)
def vertex_train_all(self, force: bool = False) -> Dict[str, Any]:
    """
    PRODUCTION-READY: Train all brains using Vertex AI
    
    This is the billionaire-mode training that uses Vertex AI for:
    - Intelligent behavior pattern analysis
    - Improvement generation with billionaire mindset
    - Knowledge updates from latest best practices
    - Skill enhancement aligned with revenue goals
    
    Runs every 6 hours via Celery beat.
    """
    logger.info("🚀 VERTEX AI TRAINING: All brains (BILLIONAIRE MODE)")
    
    try:
        from app.ml.vertex_continuous_trainer import get_vertex_continuous_trainer
        trainer = get_vertex_continuous_trainer()
        
        results = run_async(trainer.train_all_brains_now())
        
        _save_training_report("vertex_all_brains", results)
        
        logger.info(f"✅ VERTEX AI training completed: {results}")
        return results
        
    except Exception as e:
        logger.error(f"❌ Vertex AI training failed: {e}")
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    name="app.tasks.brain_training.vertex_continuous_check",
    max_retries=1,
    acks_late=True,
)
def vertex_continuous_check(self) -> Dict[str, Any]:
    """
    PRODUCTION-READY: Continuous health check with auto-training
    
    Runs every 15 minutes to check brain health and trigger
    training if error rates or rejection rates exceed thresholds.
    
    Billionaire principle: Fix problems before they impact revenue
    """
    logger.info("🔍 VERTEX: Continuous health check...")
    
    try:
        from app.ml.vertex_continuous_trainer import get_vertex_continuous_trainer
        trainer = get_vertex_continuous_trainer()
        
        brains_trained = []
        checks = {}
        
        for brain_type in ["sub_agent", "voice_agent", "production"]:
            should_train, priority, reason = run_async(trainer._should_train(brain_type))
            
            checks[brain_type] = {
                "should_train": should_train,
                "priority": priority.name,
                "reason": reason,
                "behaviors_pending": len(trainer.behavior_buffer.get(brain_type, [])),
            }
            
            if should_train:
                # Trigger async training
                vertex_train_brain.delay(brain_type, priority.value, reason)
                brains_trained.append(brain_type)
                logger.info(f"⚡ Triggered Vertex training for {brain_type}: {reason}")
        
        result = {
            "checked_at": datetime.now().isoformat(),
            "checks": checks,
            "training_triggered": brains_trained,
            "billionaire_mode": True,
        }
        
        logger.info(f"✅ Continuous check completed. Triggered: {brains_trained}")
        return result
        
    except Exception as e:
        logger.error(f"❌ Continuous check failed: {e}")
        return {"error": str(e), "checked_at": datetime.now().isoformat()}


@celery_app.task(
    bind=True,
    name="app.tasks.brain_training.vertex_train_brain",
    max_retries=3,
    default_retry_delay=120,
    autoretry_for=(Exception,),
    acks_late=True,
)
def vertex_train_brain(
    self,
    brain_type: str,
    priority: int = 3,
    trigger_reason: str = "scheduled",
) -> Dict[str, Any]:
    """
    PRODUCTION-READY: Train a specific brain with Vertex AI
    
    Args:
        brain_type: 'sub_agent', 'voice_agent', or 'production'
        priority: 1=CRITICAL, 2=HIGH, 3=NORMAL, 4=LOW, 5=MAINTENANCE
        trigger_reason: What triggered this training
    """
    logger.info(f"🧠 VERTEX: Training {brain_type} (priority: {priority}, reason: {trigger_reason})")
    
    try:
        from app.ml.vertex_continuous_trainer import (
            get_vertex_continuous_trainer,
            TrainingPriority,
        )
        trainer = get_vertex_continuous_trainer()
        
        # Map priority int to enum
        priority_map = {
            1: TrainingPriority.CRITICAL,
            2: TrainingPriority.HIGH,
            3: TrainingPriority.NORMAL,
            4: TrainingPriority.LOW,
            5: TrainingPriority.MAINTENANCE,
        }
        priority_enum = priority_map.get(priority, TrainingPriority.NORMAL)
        
        metrics = run_async(
            trainer.train_brain_with_vertex(brain_type, priority_enum, trigger_reason)
        )
        
        result = {
            "brain_type": brain_type,
            "status": "completed" if metrics.completed_at else "failed",
            "improvement_percent": metrics.improvement_percent,
            "training_duration_seconds": metrics.training_duration_seconds,
            "vertex_calls": metrics.vertex_calls,
            "behaviors_analyzed": metrics.behaviors_analyzed,
            "patterns_discovered": metrics.patterns_discovered,
            "improvements_generated": metrics.improvements_generated,
            "skills_enhanced": metrics.skills_enhanced,
            "revenue_impact_score": metrics.revenue_impact_score,
            "scale_readiness_score": metrics.scale_readiness_score,
            "automation_score": metrics.automation_score,
        }
        
        _save_training_report(f"vertex_{brain_type}", result)
        
        logger.info(
            f"✅ VERTEX: {brain_type} training done: "
            f"{metrics.improvement_percent:.1f}% improvement, "
            f"revenue impact: {metrics.revenue_impact_score:.2f}"
        )
        return result
        
    except Exception as e:
        logger.error(f"❌ Vertex brain training failed: {e}")
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    name="app.tasks.brain_training.vertex_knowledge_update",
    max_retries=2,
    default_retry_delay=600,
    acks_late=True,
)
def vertex_knowledge_update(self) -> Dict[str, Any]:
    """
    PRODUCTION-READY: Update all brains with latest knowledge via Vertex AI
    
    Uses Vertex AI to:
    - Search for latest best practices
    - Update brain knowledge bases
    - Apply billionaire mindset learnings
    
    Runs daily at 4 AM.
    """
    logger.info("🌐 VERTEX: Knowledge update for all brains...")
    
    try:
        from app.ml.vertex_continuous_trainer import get_vertex_continuous_trainer
        trainer = get_vertex_continuous_trainer()
        
        results = {}
        for brain_type in ["sub_agent", "voice_agent", "production"]:
            try:
                knowledge = run_async(trainer._update_knowledge_vertex(brain_type))
                results[brain_type] = {
                    "status": "success",
                    "knowledge_items": len(knowledge),
                    "topics_updated": [k.get("topic", "unknown") for k in knowledge],
                }
            except Exception as e:
                results[brain_type] = {"status": "failed", "error": str(e)}
        
        logger.info(f"✅ VERTEX: Knowledge update completed")
        return {
            "updated_at": datetime.now().isoformat(),
            "results": results,
            "billionaire_mode": True,
        }
        
    except Exception as e:
        logger.error(f"❌ Vertex knowledge update failed: {e}")
        raise self.retry(exc=e)


@celery_app.task(
    name="app.tasks.brain_training.get_vertex_status",
)
def get_vertex_status() -> Dict[str, Any]:
    """
    Get Vertex AI continuous training status
    
    Returns comprehensive status including:
    - Training configuration
    - Per-brain status
    - Recent training sessions
    - Billionaire metrics
    """
    try:
        from app.ml.vertex_continuous_trainer import get_vertex_continuous_trainer
        trainer = get_vertex_continuous_trainer()
        
        return run_async(trainer.get_training_status())
        
    except Exception as e:
        logger.error(f"Failed to get Vertex status: {e}")
        return {"error": str(e)}


@celery_app.task(
    name="app.tasks.brain_training.start_vertex_continuous",
)
def start_vertex_continuous() -> Dict[str, Any]:
    """
    Start Vertex AI continuous training loop
    
    This starts a background loop that continuously monitors
    brain health and triggers training as needed.
    """
    try:
        from app.ml.vertex_continuous_trainer import start_continuous_training
        return run_async(start_continuous_training())
    except Exception as e:
        logger.error(f"Failed to start continuous training: {e}")
        return {"error": str(e)}


@celery_app.task(
    name="app.tasks.brain_training.stop_vertex_continuous",
)
def stop_vertex_continuous() -> Dict[str, Any]:
    """Stop Vertex AI continuous training loop"""
    try:
        from app.ml.vertex_continuous_trainer import stop_continuous_training
        return run_async(stop_continuous_training())
    except Exception as e:
        logger.error(f"Failed to stop continuous training: {e}")
        return {"error": str(e)}


def _save_training_report(brain_type: str, results: Dict[str, Any]):
    """Save training report to disk"""
    try:
        report_file = TRAINING_DATA_DIR / f"training_report_{brain_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, "w") as f:
            json.dump(results, f, indent=2, default=str)
        
        # Also update latest report
        latest_file = TRAINING_DATA_DIR / f"latest_{brain_type}.json"
        with open(latest_file, "w") as f:
            json.dump(results, f, indent=2, default=str)
            
    except Exception as e:
        logger.error(f"Failed to save training report: {e}")


# Export task names for Celery beat schedule
BRAIN_TRAINING_TASKS = [
    # Original tasks
    "app.tasks.brain_training.train_all_brains",
    "app.tasks.brain_training.train_brain",
    "app.tasks.brain_training.continuous_training_check",
    "app.tasks.brain_training.web_knowledge_update",
    "app.tasks.brain_training.get_training_status",
    "app.tasks.brain_training.record_feedback",
    # Vertex AI production-ready tasks
    "app.tasks.brain_training.vertex_train_all",
    "app.tasks.brain_training.vertex_continuous_check",
    "app.tasks.brain_training.vertex_train_brain",
    "app.tasks.brain_training.vertex_knowledge_update",
    "app.tasks.brain_training.get_vertex_status",
    "app.tasks.brain_training.start_vertex_continuous",
    "app.tasks.brain_training.stop_vertex_continuous",
]
