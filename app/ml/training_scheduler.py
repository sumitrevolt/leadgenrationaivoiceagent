"""
ML Training Scheduler
Schedules and manages automatic training jobs
Runs nightly batch training to improve the AI brain
"""

import asyncio
from datetime import datetime, time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
import json
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.utils.logger import setup_logger
from app.ml.auto_trainer import AutoTrainer, TrainingJob, ModelType
from app.ml.data_pipeline import ConversationDataPipeline
from app.ml.feedback_loop import FeedbackLoop
from app.ml.vector_store import VectorStore

logger = setup_logger(__name__)


@dataclass
class TrainingScheduleConfig:
    """Configuration for training schedule"""
    # Nightly training time (IST)
    nightly_training_hour: int = 2  # 2 AM
    nightly_training_minute: int = 0
    
    # Weekly deep training (Sunday)
    weekly_training_enabled: bool = True
    weekly_training_day: str = "sun"
    weekly_training_hour: int = 3
    
    # Minimum data requirements
    min_conversations_for_training: int = 50
    min_positive_outcomes_for_training: int = 10
    
    # Training thresholds
    retrain_if_accuracy_below: float = 0.8
    skip_if_no_new_data: bool = True


@dataclass
class TrainingReport:
    """Report from a training run"""
    run_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str = "running"
    models_trained: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    improvements: Dict[str, float] = field(default_factory=dict)


class MLTrainingScheduler:
    """
    Manages scheduled ML training jobs
    
    Responsibilities:
    - Schedule nightly batch training
    - Run weekly deep learning cycles
    - Monitor training health
    - Generate training reports
    """
    
    def __init__(
        self,
        config: Optional[TrainingScheduleConfig] = None,
        tenant_id: str = "default"
    ):
        self.config = config or TrainingScheduleConfig()
        self.tenant_id = tenant_id
        self.scheduler = AsyncIOScheduler()
        
        # Initialize ML components
        self.auto_trainer = AutoTrainer(tenant_id=tenant_id)
        self.data_pipeline = ConversationDataPipeline(tenant_id=tenant_id)
        self.feedback_loop = FeedbackLoop(tenant_id=tenant_id)
        self.vector_store = VectorStore(tenant_id=tenant_id)
        
        # Training state
        self.is_running = False
        self.current_job: Optional[TrainingJob] = None
        self.training_history: List[TrainingReport] = []
        
        # Reports directory
        self.reports_dir = Path(f"data/training_reports/{tenant_id}")
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"🎯 ML Training Scheduler initialized for tenant: {tenant_id}")
    
    async def start(self) -> None:
        """Start the training scheduler"""
        
        # Schedule nightly training
        self.scheduler.add_job(
            self._run_nightly_training,
            CronTrigger(
                hour=self.config.nightly_training_hour,
                minute=self.config.nightly_training_minute
            ),
            id="nightly_training",
            name="Nightly ML Training",
            replace_existing=True
        )
        
        # Schedule weekly deep training
        if self.config.weekly_training_enabled:
            self.scheduler.add_job(
                self._run_weekly_training,
                CronTrigger(
                    day_of_week=self.config.weekly_training_day,
                    hour=self.config.weekly_training_hour
                ),
                id="weekly_training",
                name="Weekly Deep Training",
                replace_existing=True
            )
        
        self.scheduler.start()
        self.is_running = True
        
        logger.info(f"✅ ML Training Scheduler started")
        logger.info(f"   📅 Nightly training: {self.config.nightly_training_hour}:{self.config.nightly_training_minute:02d}")
        if self.config.weekly_training_enabled:
            logger.info(f"   📅 Weekly training: {self.config.weekly_training_day} at {self.config.weekly_training_hour}:00")
    
    async def stop(self) -> None:
        """Stop the training scheduler"""
        self.scheduler.shutdown(wait=False)
        self.is_running = False
        logger.info("🛑 ML Training Scheduler stopped")
    
    async def _run_nightly_training(self) -> TrainingReport:
        """Execute nightly training job"""
        
        report = TrainingReport(
            run_id=f"nightly_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            started_at=datetime.now()
        )
        
        logger.info(f"🌙 Starting nightly training run: {report.run_id}")
        
        try:
            # Check if we have enough data
            data_stats = await self._get_training_data_stats()
            
            if data_stats["total_conversations"] < self.config.min_conversations_for_training:
                report.status = "skipped"
                report.errors.append(
                    f"Insufficient data: {data_stats['total_conversations']} conversations "
                    f"(need {self.config.min_conversations_for_training})"
                )
                logger.warning(f"⚠️ Skipping training: insufficient data")
                return report
            
            if self.config.skip_if_no_new_data and data_stats["new_since_last_training"] == 0:
                report.status = "skipped"
                report.errors.append("No new data since last training")
                logger.info("⏭️ Skipping training: no new data")
                return report
            
            # Run training via auto_trainer
            training_result = await self.auto_trainer.run_nightly_training()
            
            # Update report
            report.models_trained = training_result.get("models_trained", [])
            report.metrics = training_result.get("metrics", {})
            report.improvements = training_result.get("improvements", {})
            report.status = "completed"
            report.completed_at = datetime.now()
            
            logger.info(f"✅ Nightly training completed")
            logger.info(f"   Models trained: {report.models_trained}")
            logger.info(f"   Improvements: {report.improvements}")
            
        except Exception as e:
            report.status = "failed"
            report.errors.append(str(e))
            report.completed_at = datetime.now()
            logger.error(f"❌ Nightly training failed: {e}")
        
        # Save report
        await self._save_report(report)
        self.training_history.append(report)
        
        return report
    
    async def _run_weekly_training(self) -> TrainingReport:
        """Execute weekly deep training job"""
        
        report = TrainingReport(
            run_id=f"weekly_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            started_at=datetime.now()
        )
        
        logger.info(f"📅 Starting weekly deep training: {report.run_id}")
        
        try:
            # Weekly training includes:
            # 1. Full model retraining
            # 2. Vector store optimization
            # 3. A/B test analysis
            # 4. Prompt optimization
            
            # Full intent classifier training
            intent_result = await self.auto_trainer.train_intent_classifier(force=True)
            report.models_trained.append("intent_classifier")
            report.metrics["intent_classifier"] = intent_result
            
            # Full lead scorer training
            scorer_result = await self.auto_trainer.train_lead_scorer(force=True)
            report.models_trained.append("lead_scorer")
            report.metrics["lead_scorer"] = scorer_result
            
            # Optimize prompts based on weekly data
            prompt_result = await self.auto_trainer.optimize_prompts()
            report.metrics["prompt_optimization"] = prompt_result
            
            # Analyze A/B test results
            ab_results = await self._analyze_ab_tests()
            report.metrics["ab_tests"] = ab_results
            
            # Cleanup old vector entries
            await self._cleanup_vector_store()
            
            report.status = "completed"
            report.completed_at = datetime.now()
            
            logger.info(f"✅ Weekly training completed")
            
        except Exception as e:
            report.status = "failed"
            report.errors.append(str(e))
            report.completed_at = datetime.now()
            logger.error(f"❌ Weekly training failed: {e}")
        
        await self._save_report(report)
        self.training_history.append(report)
        
        return report
    
    async def run_training_now(self, training_type: str = "nightly") -> TrainingReport:
        """Manually trigger training run"""
        
        if self.current_job:
            raise RuntimeError("Training already in progress")
        
        if training_type == "nightly":
            return await self._run_nightly_training()
        elif training_type == "weekly":
            return await self._run_weekly_training()
        else:
            raise ValueError(f"Unknown training type: {training_type}")
    
    async def _get_training_data_stats(self) -> Dict[str, Any]:
        """Get statistics about available training data"""
        
        try:
            # Get data from pipeline
            stats = await self.data_pipeline.get_stats()
            
            return {
                "total_conversations": stats.get("total_conversations", 0),
                "positive_outcomes": stats.get("positive_outcomes", 0),
                "new_since_last_training": stats.get("new_since_last_training", 0),
                "industries": stats.get("industries", []),
                "date_range": stats.get("date_range", {})
            }
        except Exception as e:
            logger.warning(f"Failed to get training stats: {e}")
            return {
                "total_conversations": 0,
                "positive_outcomes": 0,
                "new_since_last_training": 0
            }
    
    async def _analyze_ab_tests(self) -> Dict[str, Any]:
        """Analyze A/B test results from the week"""
        
        try:
            # Get A/B test data from feedback loop
            ab_data = await self.feedback_loop.get_ab_test_results()
            
            results = {}
            for test_id, test_data in ab_data.items():
                if test_data.get("sample_size", 0) >= 30:  # Statistical significance
                    winner = max(
                        test_data.get("variants", {}),
                        key=lambda v: test_data["variants"][v].get("success_rate", 0)
                    )
                    results[test_id] = {
                        "winner": winner,
                        "improvement": test_data["variants"][winner].get("success_rate", 0) - 
                                     test_data.get("baseline_rate", 0),
                        "sample_size": test_data.get("sample_size", 0)
                    }
            
            return results
            
        except Exception as e:
            logger.warning(f"A/B test analysis failed: {e}")
            return {}
    
    async def _cleanup_vector_store(self) -> None:
        """Clean up old/low-quality entries from vector store"""
        
        try:
            # Remove conversations older than 90 days with low success scores
            cutoff_days = 90
            min_score = 0.3
            
            removed = await self.vector_store.cleanup(
                max_age_days=cutoff_days,
                min_success_score=min_score
            )
            
            logger.info(f"🧹 Cleaned up {removed} old vector entries")
            
        except Exception as e:
            logger.warning(f"Vector store cleanup failed: {e}")
    
    async def _save_report(self, report: TrainingReport) -> None:
        """Save training report to file"""
        
        report_path = self.reports_dir / f"{report.run_id}.json"
        
        report_data = {
            "run_id": report.run_id,
            "started_at": report.started_at.isoformat(),
            "completed_at": report.completed_at.isoformat() if report.completed_at else None,
            "status": report.status,
            "models_trained": report.models_trained,
            "metrics": report.metrics,
            "errors": report.errors,
            "improvements": report.improvements
        }
        
        with open(report_path, "w") as f:
            json.dump(report_data, f, indent=2)
    
    async def get_training_status(self) -> Dict[str, Any]:
        """Get current training status"""
        
        return {
            "scheduler_running": self.is_running,
            "current_job": self.current_job.__dict__ if self.current_job else None,
            "next_nightly": str(self.scheduler.get_job("nightly_training").next_run_time) if self.is_running else None,
            "next_weekly": str(self.scheduler.get_job("weekly_training").next_run_time) if self.is_running and self.config.weekly_training_enabled else None,
            "recent_runs": [
                {
                    "run_id": r.run_id,
                    "status": r.status,
                    "completed_at": r.completed_at.isoformat() if r.completed_at else None
                }
                for r in self.training_history[-10:]
            ]
        }
    
    async def get_training_metrics(self) -> Dict[str, Any]:
        """Get aggregated training metrics"""
        
        if not self.training_history:
            return {"message": "No training history available"}
        
        successful_runs = [r for r in self.training_history if r.status == "completed"]
        
        if not successful_runs:
            return {"message": "No successful training runs yet"}
        
        latest = successful_runs[-1]
        
        # Calculate trends
        all_improvements = {}
        for run in successful_runs[-5:]:
            for model, improvement in run.improvements.items():
                if model not in all_improvements:
                    all_improvements[model] = []
                all_improvements[model].append(improvement)
        
        avg_improvements = {
            model: sum(vals) / len(vals)
            for model, vals in all_improvements.items()
        }
        
        return {
            "total_runs": len(self.training_history),
            "successful_runs": len(successful_runs),
            "failed_runs": len([r for r in self.training_history if r.status == "failed"]),
            "latest_run": {
                "run_id": latest.run_id,
                "completed_at": latest.completed_at.isoformat() if latest.completed_at else None,
                "models_trained": latest.models_trained,
                "improvements": latest.improvements
            },
            "average_improvements": avg_improvements
        }


# Singleton scheduler instance
_scheduler_instance: Optional[MLTrainingScheduler] = None


async def get_training_scheduler(tenant_id: str = "default") -> MLTrainingScheduler:
    """Get or create training scheduler instance"""
    global _scheduler_instance
    
    if _scheduler_instance is None:
        _scheduler_instance = MLTrainingScheduler(tenant_id=tenant_id)
        await _scheduler_instance.start()
    
    return _scheduler_instance


async def stop_training_scheduler() -> None:
    """Stop the training scheduler"""
    global _scheduler_instance
    
    if _scheduler_instance:
        await _scheduler_instance.stop()
        _scheduler_instance = None
