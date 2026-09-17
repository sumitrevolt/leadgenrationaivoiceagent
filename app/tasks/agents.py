"""Celery Tasks for Agent Management.

Background tasks for worker/agent operations:
- Task queue processing
- Performance tracking
- Improvement proposal generation
- Agent status updates
"""

from __future__ import annotations

import os
from typing import Any

from app.worker import celery_app


@celery_app.task(bind=True, max_retries=3, name="app.tasks.agents.process_task_queue")
def process_task_queue(self) -> dict[str, Any]:
    """Process pending task queue for all workers.
    
    Delegates to app.agents.workers module.
    """
    try:
        from app.agents.workers import get_workers_manager
        from app.agents.skills import get_skill_registry
        
        manager = get_workers_manager()
        registry = get_skill_registry()
        
        # Get all workers
        workers = manager.list_workers()
        result = {
            "processed_workers": 0,
            "total_tasks": 0,
            "completed_tasks": 0,
        }
        
        for worker_info in workers:
            worker = manager.get_worker(worker_info["worker_id"])
            if not worker:
                continue
            
            # Process pending tasks
            pending_tasks = [t for t in worker.tasks if t.status == "pending"]
            result["total_tasks"] += len(pending_tasks)
            
            for task in pending_tasks[:5]:  # Process max 5 per worker per tick
                try:
                    # Execute skill
                    skill = worker.skills.get(task.skill_name)
                    if not skill:
                        task.status = "failed"
                        task.error = f"Skill {task.skill_name} not found"
                        continue
                    
                    # Simulate execution (in real impl, call actual skill)
                    task.status = "completed"
                    task.completed_at = task.completed_at or ""
                    result["completed_tasks"] += 1
                    
                except Exception as e:
                    task.status = "failed"
                    task.error = str(e)
                    self.retry(exc=e, countdown=60)
            
            result["processed_workers"] += 1
        
        return result
        
    except Exception as e:
        self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=3, name="app.tasks.agents.update_agent_status")
def update_agent_status(
    self,
    agent_id: str,
    status: str,
) -> dict[str, Any]:
    """Update agent status (idle/working/offline)."""
    try:
        from app.agents.agents import get_agent_manager
        
        manager = get_agent_manager()
        
        if status == "activate":
            result = manager.activate_agent(agent_id)
        elif status == "pause":
            result = manager.pause_agent(agent_id)
        else:
            return {"error": f"Invalid status: {status}"}
        
        return result
        
    except Exception as e:
        self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=3, name="app.tasks.agents.track_performance")
def track_performance(
    self,
    agent_id: str,
    skill_name: str,
    success: bool,
    quality_score: float,
    duration_seconds: float,
) -> dict[str, Any]:
    """Track agent performance for self-improvement."""
    try:
        from app.feedback.loop import get_loop
        
        loop = get_loop()
        
        # Record feedback
        loop.record_feedback(
            task_id=f"celery-{self.request.id}",
            agent_id=agent_id,
            skill_name=skill_name,
            input_data={"tracked": True},
            output_data={"success": success},
            success=success,
            quality_score=quality_score,
            duration_seconds=duration_seconds,
        )
        
        # Update agent task count
        from app.agents.agents import get_agent_manager
        manager = get_agent_manager()
        manager.increment_task_count(agent_id)
        
        return {"success": True}
        
    except Exception as e:
        self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=3, name="app.tasks.agents.generate_improvement_proposals")
def generate_improvement_proposals(self) -> dict[str, Any]:
    """Generate improvement proposals for underperforming agents."""
    try:
        from app.feedback.loop import get_loop
        
        loop = get_loop()
        status = loop.get_loop_status()
        
        if not status["loop_enabled"]:
            return {"skipped": "loop not enabled"}
        
        # Get all performance data
        all_perf = loop.get_all_performance()
        proposals_generated = 0
        
        for perf in all_perf:
            if perf["avg_quality_score"] < loop.quality_threshold:
                # Generate proposal
                proposal = loop.proposals.append({
                    "proposal_id": f"auto-{perf['agent_id']}-{perf['skill_name']}",
                    "agent_id": perf["agent_id"],
                    "skill_name": perf["skill_name"],
                    "current_performance": {
                        "quality_score": perf["avg_quality_score"],
                        "success_rate": perf["success_rate"],
                    },
                    "proposed_change": f"Improve {perf['skill_name']} for {perf['agent_id']}",
                    "expected_improvement": "Increase quality score above threshold",
                    "confidence": 0.75,
                    "status": "pending",
                })
                proposals_generated += 1
        
        return {
            "proposals_generated": proposals_generated,
            "total_proposals": len(loop.proposals),
        }
        
    except Exception as e:
        self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=3, name="app.tasks.agents.daily_agent_summary")
def daily_agent_summary(self) -> dict[str, Any]:
    """Generate daily summary of agent activity."""
    try:
        from app.agents.agents import get_agent_manager
        from app.feedback.loop import get_loop
        
        manager = get_agent_manager()
        loop = get_loop()
        
        summary = manager.get_daily_summary()
        loop_status = loop.get_loop_status()
        
        return {
            "agent_summary": summary,
            "loop_status": loop_status,
            "generated_at": loop_status.get("updated_at"),
        }
        
    except Exception as e:
        self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=3, name="app.tasks.agents.sync_agent_memory")
def sync_agent_memory(self) -> dict[str, Any]:
    """Sync agent memory to disk."""
    try:
        from app.agents.agents import get_agent_manager
        
        manager = get_agent_manager()
        manager._save_memory()
        
        return {"success": True, "synced": len(manager.agents)}
        
    except Exception as e:
        self.retry(exc=e, countdown=60)
