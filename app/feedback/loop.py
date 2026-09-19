"""Self-Improving Agent Loops with Feedback Tracking.

Implements a continuous improvement cycle where agents:
1. Execute tasks
2. Record outcomes
3. Analyze performance
4. Generate improvement proposals
5. Apply improvements (gated)
6. Track feedback scores
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


_IST = timezone(timedelta(hours=5, minutes=30))


class FeedbackRecord(BaseModel):
    """Record of task feedback for self-improvement."""
    task_id: str
    agent_id: str
    skill_name: str
    input_data: dict[str, Any]
    output_data: Optional[dict[str, Any]] = None
    success: bool
    quality_score: Optional[float] = None  # 0.0 to 1.0
    duration_seconds: Optional[float] = None
    feedback_text: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(_IST).isoformat())
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "skill_name": self.skill_name,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "success": self.success,
            "quality_score": self.quality_score,
            "duration_seconds": self.duration_seconds,
            "feedback_text": self.feedback_text,
            "timestamp": self.timestamp,
        }


class ImprovementProposal(BaseModel):
    """Proposal for agent improvement."""
    proposal_id: str
    agent_id: str
    skill_name: str
    current_performance: dict[str, Any]
    proposed_change: str
    expected_improvement: str
    confidence: float  # 0.0 to 1.0
    status: str = "pending"  # pending, approved, rejected, applied
    created_at: str = Field(default_factory=lambda: datetime.now(_IST).isoformat())
    approved_by: Optional[str] = None
    applied_at: Optional[str] = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "agent_id": self.agent_id,
            "skill_name": self.skill_name,
            "current_performance": self.current_performance,
            "proposed_change": self.proposed_change,
            "expected_improvement": self.expected_improvement,
            "confidence": self.confidence,
            "status": self.status,
            "created_at": self.created_at,
            "approved_by": self.approved_by,
            "applied_at": self.applied_at,
        }


class AgentPerformance(BaseModel):
    """Performance metrics for an agent."""
    agent_id: str
    skill_name: str
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    avg_quality_score: float = 0.0
    avg_duration_seconds: float = 0.0
    tasks_today: int = 0
    last_task_at: Optional[str] = None
    improvement_count: int = 0

    @property
    def success_rate(self) -> float:
        return self.successful_tasks / self.total_tasks if self.total_tasks > 0 else 0.0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "skill_name": self.skill_name,
            "total_tasks": self.total_tasks,
            "successful_tasks": self.successful_tasks,
            "failed_tasks": self.failed_tasks,
            "success_rate": self.successful_tasks / self.total_tasks if self.total_tasks > 0 else 0,
            "avg_quality_score": self.avg_quality_score,
            "avg_duration_seconds": self.avg_duration_seconds,
            "tasks_today": self.tasks_today,
            "last_task_at": self.last_task_at,
            "improvement_count": self.improvement_count,
        }


class SelfImprovingLoop:
    """Self-improving agent loop with feedback tracking."""
    
    def __init__(self, state_path: str = "data/self_improve_state.json"):
        self.state_path = state_path
        self.feedback_records: list[FeedbackRecord] = []
        self.proposals: list[ImprovementProposal] = []
        self.performance: dict[str, dict[str, AgentPerformance]] = {}
        self.loop_enabled: bool = False
        self.quality_threshold: float = 0.7
        self.max_proposals_per_day: int = 10
        self.auto_approve_threshold: float = 0.9
        self._load_state()
    
    def _load_state(self):
        """Load state from disk."""
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, "r") as f:
                    data = json.load(f)
                self.loop_enabled = data.get("loop_enabled", False)
                self.quality_threshold = data.get("quality_threshold", 0.7)
                self.max_proposals_per_day = data.get("max_proposals_per_day", 10)
                self.auto_approve_threshold = data.get("auto_approve_threshold", 0.9)
                
                # Load feedback records
                for rec_data in data.get("feedback_records", []):
                    try:
                        self.feedback_records.append(FeedbackRecord(**rec_data))
                    except Exception:
                        pass
                
                # Load proposals
                for prop_data in data.get("proposals", []):
                    try:
                        self.proposals.append(ImprovementProposal(**prop_data))
                    except Exception:
                        pass
                
                # Load performance
                for agent_id, skills in data.get("performance", {}).items():
                    self.performance[agent_id] = {}
                    for skill_name, perf_data in skills.items():
                        try:
                            self.performance[agent_id][skill_name] = AgentPerformance(**perf_data)
                        except Exception:
                            pass
            except Exception as e:
                print(f"[self_improve] Failed to load state: {e}")
    
    def _save_state(self):
        """Save state to disk."""
        try:
            data = {
                "loop_enabled": self.loop_enabled,
                "quality_threshold": self.quality_threshold,
                "max_proposals_per_day": self.max_proposals_per_day,
                "auto_approve_threshold": self.auto_approve_threshold,
                "feedback_records": [r.to_dict() for r in self.feedback_records[-500:]],
                "proposals": [p.to_dict() for p in self.proposals],
                "performance": {
                    agent_id: {
                        skill_name: perf.to_dict()
                        for skill_name, perf in skills.items()
                    }
                    for agent_id, skills in self.performance.items()
                },
                "updated_at": datetime.now(_IST).isoformat(),
            }
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            with open(self.state_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[self_improve] Failed to save state: {e}")
    
    def record_feedback(
        self,
        task_id: str,
        agent_id: str,
        skill_name: str,
        input_data: dict[str, Any],
        output_data: Optional[dict[str, Any]] = None,
        success: bool = True,
        quality_score: Optional[float] = None,
        duration_seconds: Optional[float] = None,
        feedback_text: Optional[str] = None,
    ) -> FeedbackRecord:
        """Record feedback for a task execution."""
        record = FeedbackRecord(
            task_id=task_id,
            agent_id=agent_id,
            skill_name=skill_name,
            input_data=input_data,
            output_data=output_data,
            success=success,
            quality_score=quality_score,
            duration_seconds=duration_seconds,
            feedback_text=feedback_text,
        )
        self.feedback_records.append(record)
        
        # Update performance metrics
        self._update_performance(agent_id, skill_name, record)
        
        # Check if improvement proposal needed
        if self.loop_enabled and success and quality_score is not None:
            if quality_score < self.quality_threshold:
                self._generate_improvement_proposal(agent_id, skill_name, record)
        
        self._save_state()
        return record
    
    def _update_performance(
        self,
        agent_id: str,
        skill_name: str,
        record: FeedbackRecord,
    ):
        """Update performance metrics after task execution."""
        if agent_id not in self.performance:
            self.performance[agent_id] = {}
        if skill_name not in self.performance[agent_id]:
            self.performance[agent_id][skill_name] = AgentPerformance(
                agent_id=agent_id,
                skill_name=skill_name,
            )
        
        perf = self.performance[agent_id][skill_name]
        perf.total_tasks += 1
        if record.success:
            perf.successful_tasks += 1
        else:
            perf.failed_tasks += 1
        
        # Update averages
        if perf.total_tasks > 0:
            # Recalculate avg quality score
            recent_records = [
                r for r in self.feedback_records
                if r.agent_id == agent_id and r.skill_name == skill_name
            ]
            scores = [r.quality_score for r in recent_records if r.quality_score is not None]
            perf.avg_quality_score = sum(scores) / len(scores) if scores else 0.0
            
            durations = [r.duration_seconds for r in recent_records if r.duration_seconds is not None]
            perf.avg_duration_seconds = sum(durations) / len(durations) if durations else 0.0
        
        perf.last_task_at = record.timestamp
        
        # Count tasks today
        today = datetime.now(_IST).date()
        today_records = [
            r for r in self.feedback_records
            if r.agent_id == agent_id
            and r.skill_name == skill_name
            and datetime.fromisoformat(r.timestamp).date() == today
        ]
        perf.tasks_today = len(today_records)
    
    def _generate_improvement_proposal(
        self,
        agent_id: str,
        skill_name: str,
        record: FeedbackRecord,
    ):
        """Generate improvement proposal based on feedback."""
        # Check daily limit
        today = datetime.now(_IST).date()
        today_proposals = [
            p for p in self.proposals
            if datetime.fromisoformat(p.created_at).date() == today
            and p.agent_id == agent_id
            and p.skill_name == skill_name
        ]
        if len(today_proposals) >= self.max_proposals_per_day:
            return
        
        # Create proposal
        proposal = ImprovementProposal(
            proposal_id=f"imp-{agent_id}-{skill_name}-{datetime.now(_IST).timestamp()}",
            agent_id=agent_id,
            skill_name=skill_name,
            current_performance={
                "quality_score": record.quality_score,
                "duration": record.duration_seconds,
                "success": record.success,
            },
            proposed_change=f"Optimize {skill_name} for agent {agent_id} based on quality feedback",
            expected_improvement="Increase quality score by 0.1-0.2",
            confidence=0.7,
        )
        self.proposals.append(proposal)
        
        # Auto-approve if confidence is high
        if proposal.confidence >= self.auto_approve_threshold:
            proposal.status = "approved"
            proposal.approved_by = "auto"
            proposal.applied_at = datetime.now(_IST).isoformat()
            
            # Update performance improvement count
            if agent_id in self.performance and skill_name in self.performance[agent_id]:
                self.performance[agent_id][skill_name].improvement_count += 1
        
        self._save_state()
    
    def approve_proposal(
        self,
        proposal_id: str,
        approved_by: str,
    ) -> dict[str, Any]:
        """Approve an improvement proposal."""
        for proposal in self.proposals:
            if proposal.proposal_id == proposal_id:
                proposal.status = "approved"
                proposal.approved_by = approved_by
                proposal.applied_at = datetime.now(_IST).isoformat()
                
                # Update improvement count
                if proposal.agent_id in self.performance:
                    if proposal.skill_name in self.performance[proposal.agent_id]:
                        self.performance[proposal.agent_id][proposal.skill_name].improvement_count += 1
                
                self._save_state()
                return {"success": True, "proposal": proposal.to_dict()}
        
        return {"error": f"Proposal {proposal_id} not found"}
    
    def reject_proposal(self, proposal_id: str) -> dict[str, Any]:
        """Reject an improvement proposal."""
        for proposal in self.proposals:
            if proposal.proposal_id == proposal_id:
                proposal.status = "rejected"
                self._save_state()
                return {"success": True, "proposal": proposal.to_dict()}
        
        return {"error": f"Proposal {proposal_id} not found"}
    
    def get_performance(
        self,
        agent_id: str,
        skill_name: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Get performance metrics for an agent."""
        if agent_id not in self.performance:
            return []
        
        skills = self.performance[agent_id]
        if skill_name:
            perf = skills.get(skill_name)
            return [perf.to_dict()] if perf else []
        
        return [p.to_dict() for p in skills.values()]
    
    def get_all_performance(self) -> list[dict[str, Any]]:
        """Get all agent performance metrics."""
        result = []
        for agent_id, skills in self.performance.items():
            for skill_name, perf in skills.items():
                result.append(perf.to_dict())
        return result
    
    def get_proposals(
        self,
        agent_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get improvement proposals."""
        result = []
        for proposal in reversed(self.proposals):
            if agent_id and proposal.agent_id != agent_id:
                continue
            if status and proposal.status != status:
                continue
            result.append(proposal.to_dict())
            if len(result) >= limit:
                break
        return result
    
    def get_loop_status(self) -> dict[str, Any]:
        """Get current loop status."""
        today = datetime.now(_IST).date()
        today_feedback = [
            r for r in self.feedback_records
            if datetime.fromisoformat(r.timestamp).date() == today
        ]
        today_proposals = [
            p for p in self.proposals
            if datetime.fromisoformat(p.created_at).date() == today
        ]
        
        return {
            "loop_enabled": self.loop_enabled,
            "total_feedback_records": len(self.feedback_records),
            "today_feedback": len(today_feedback),
            "total_proposals": len(self.proposals),
            "today_proposals": len(today_proposals),
            "pending_proposals": len([p for p in self.proposals if p.status == "pending"]),
            "approved_proposals": len([p for p in self.proposals if p.status == "approved"]),
            "quality_threshold": self.quality_threshold,
            "auto_approve_threshold": self.auto_approve_threshold,
        }
    
    def toggle_loop(self, enabled: bool) -> dict[str, Any]:
        """Enable or disable the self-improvement loop."""
        self.loop_enabled = enabled
        self._save_state()
        return {"success": True, "loop_enabled": self.loop_enabled}


# Module-level singleton
_loop: Optional[SelfImprovingLoop] = None


def get_loop() -> SelfImprovingLoop:
    """Get or create singleton SelfImprovingLoop."""
    global _loop
    if _loop is None:
        _loop = SelfImprovingLoop()
    return _loop


def record_feedback(
    task_id: str,
    agent_id: str,
    skill_name: str,
    input_data: dict[str, Any],
    output_data: Optional[dict[str, Any]] = None,
    success: bool = True,
    quality_score: Optional[float] = None,
    duration_seconds: Optional[float] = None,
    feedback_text: Optional[str] = None,
) -> FeedbackRecord:
    """Convenience function to record feedback."""
    return get_loop().record_feedback(
        task_id, agent_id, skill_name, input_data, output_data,
        success, quality_score, duration_seconds, feedback_text
    )


def get_performance(
    agent_id: str,
    skill_name: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Convenience function to get performance."""
    return get_loop().get_performance(agent_id, skill_name)


def get_loop_status() -> dict[str, Any]:
    """Convenience function to get loop status."""
    return get_loop().get_loop_status()


def toggle_loop(enabled: bool) -> dict[str, Any]:
    """Convenience function to toggle loop."""
    return get_loop().toggle_loop(enabled)
