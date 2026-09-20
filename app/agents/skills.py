"""TypeSafe Skills Registry for Worker and Agent Bots.

Provides a centralized registry for all skills with type validation,
dependency tracking, and performance monitoring.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, validator


class SkillCategory(str, Enum):
    """Categories for skills."""

    DATA = "data"
    CONTENT = "content"
    COMMUNICATION = "communication"
    VOICE = "voice"
    ANALYTICS = "analytics"
    AUTOMATION = "automation"
    COMPLIANCE = "compliance"
    OPERATIONS = "operations"


class SkillDependency(BaseModel):
    """Skill dependency definition."""

    skill_name: str
    required: bool = True
    reason: str = ""


class SkillTypeDef(BaseModel):
    """Type-safe skill definition with validation."""

    name: str
    description: str
    category: SkillCategory
    parameters: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[SkillDependency] = Field(default_factory=list)
    timeout_seconds: int = 300
    retry_count: int = 3
    is_active: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: str = "1.0.0"

    @validator("timeout_seconds")
    def timeout_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("timeout_seconds must be positive")
        return v

    @validator("retry_count")
    def retry_must_be_non_negative(cls, v):
        if v < 0:
            raise ValueError("retry_count must be non-negative")
        return v

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "parameters": self.parameters,
            "output_schema": self.output_schema,
            "dependencies": [d.dict() for d in self.dependencies],
            "timeout_seconds": self.timeout_seconds,
            "retry_count": self.retry_count,
            "is_active": self.is_active,
            "version": self.version,
            "created_at": self.created_at,
        }


class SkillExecution(BaseModel):
    """Record of a skill execution."""

    skill_name: str
    executor_id: str
    input_data: dict[str, Any]
    output_data: dict[str, Any] | None = None
    status: str = "pending"  # pending, running, completed, failed
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None
    error: str | None = None
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "executor_id": self.executor_id,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "retry_count": self.retry_count,
        }


class SkillRegistry:
    """Centralized TypeSafe skill registry."""

    def __init__(self, registry_path: str = "data/skill_registry.json"):
        self.registry_path = registry_path
        self.skills: dict[str, SkillTypeDef] = {}
        self.executions: list[SkillExecution] = []
        self._load_registry()
        self._register_default_skills()

    def _load_registry(self):
        """Load skill registry from disk."""
        if os.path.exists(self.registry_path):
            try:
                with open(self.registry_path) as f:
                    data = json.load(f)
                for skill_data in data.get("skills", []):
                    try:
                        skill = SkillTypeDef(**skill_data)
                        self.skills[skill.name] = skill
                    except Exception as e:
                        print(
                            f"[skill_registry] Failed to load skill {skill_data.get('name')}: {e}"
                        )
            except Exception as e:
                print(f"[skill_registry] Failed to load registry: {e}")

    def _save_registry(self):
        """Save skill registry to disk."""
        try:
            data = {
                "skills": [s.to_dict() for s in self.skills.values()],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
            with open(self.registry_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[skill_registry] Failed to save registry: {e}")

    def _register_default_skills(self):
        """Register default skills if registry is empty."""
        if self.skills:
            return

        default_skills = [
            # Data skills
            SkillTypeDef(
                name="analyze_prospects",
                description="Analyze prospect data for insights",
                category=SkillCategory.DATA,
                parameters={"dataset": "list", "filters": "dict"},
                output_schema={"insights": "list", "summary": "dict"},
            ),
            SkillTypeDef(
                name="score_leads",
                description="Score leads based on criteria",
                category=SkillCategory.DATA,
                parameters={"leads": "list", "criteria": "dict"},
                output_schema={"scored_leads": "list"},
            ),
            # Content skills
            SkillTypeDef(
                name="create_social_post",
                description="Create social media post",
                category=SkillCategory.CONTENT,
                parameters={"niche": "str", "topic": "str"},
                output_schema={"caption": "str", "hashtags": "list"},
            ),
            SkillTypeDef(
                name="generate_email",
                description="Generate email content",
                category=SkillCategory.CONTENT,
                parameters={"subject": "str", "context": "str"},
                output_schema={"body": "str", "subject": "str"},
            ),
            # Voice skills
            SkillTypeDef(
                name="make_call",
                description="Make AI voice call",
                category=SkillCategory.VOICE,
                parameters={"phone": "str", "script": "str"},
                output_schema={"call_id": "str", "duration": "int"},
            ),
            SkillTypeDef(
                name="process_recording",
                description="Process call recording",
                category=SkillCategory.VOICE,
                parameters={"recording_id": "str"},
                output_schema={"transcript": "str", "sentiment": "str"},
            ),
            # Analytics skills
            SkillTypeDef(
                name="generate_report",
                description="Generate analytics report",
                category=SkillCategory.ANALYTICS,
                parameters={"report_type": "str", "data": "dict"},
                output_schema={"report": "dict", "charts": "list"},
            ),
            SkillTypeDef(
                name="track_metrics",
                description="Track KPI metrics",
                category=SkillCategory.ANALYTICS,
                parameters={"metrics": "list", "period": "str"},
                output_schema={"metrics": "dict", "trend": "str"},
            ),
            # Automation skills
            SkillTypeDef(
                name="schedule_task",
                description="Schedule automated task",
                category=SkillCategory.AUTOMATION,
                parameters={"task": "str", "schedule": "str"},
                output_schema={"task_id": "str", "scheduled_at": "str"},
            ),
            SkillTypeDef(
                name="trigger_workflow",
                description="Trigger automation workflow",
                category=SkillCategory.AUTOMATION,
                parameters={"workflow": "str", "inputs": "dict"},
                output_schema={"workflow_id": "str", "status": "str"},
            ),
            # Compliance skills
            SkillTypeDef(
                name="check_compliance",
                description="Check TRAI/DLP compliance",
                category=SkillCategory.COMPLIANCE,
                parameters={"campaign": "dict"},
                output_schema={"compliant": "bool", "violations": "list"},
            ),
            SkillTypeDef(
                name="scrub_dnd",
                description="Scrub DND numbers",
                category=SkillCategory.COMPLIANCE,
                parameters={"numbers": "list"},
                output_schema={"cleaned": "list", "blocked": "list"},
            ),
            # Operations skills
            SkillTypeDef(
                name="monitor_health",
                description="Monitor system health",
                category=SkillCategory.OPERATIONS,
                parameters={"components": "list"},
                output_schema={"health": "dict", "issues": "list"},
            ),
            SkillTypeDef(
                name="send_notification",
                description="Send notification",
                category=SkillCategory.OPERATIONS,
                parameters={"channel": "str", "message": "str"},
                output_schema={"sent": "bool", "message_id": "str"},
            ),
        ]

        for skill in default_skills:
            self.skills[skill.name] = skill

        self._save_registry()

    def register_skill(self, skill: SkillTypeDef) -> bool:
        """Register a new skill."""
        if skill.name in self.skills:
            # Update existing skill
            self.skills[skill.name] = skill
            self._save_registry()
            return True
        self.skills[skill.name] = skill
        self._save_registry()
        return True

    def unregister_skill(self, skill_name: str) -> bool:
        """Unregister a skill."""
        if skill_name in self.skills:
            del self.skills[skill_name]
            self._save_registry()
            return True
        return False

    def get_skill(self, skill_name: str) -> SkillTypeDef | None:
        """Get skill by name."""
        return self.skills.get(skill_name)

    def list_skills(self, category: SkillCategory | None = None) -> list[dict[str, Any]]:
        """List all skills, optionally filtered by category."""
        result = []
        for skill in self.skills.values():
            if category and skill.category != category:
                continue
            result.append(skill.to_dict())
        return result

    def execute_skill(
        self,
        skill_name: str,
        executor_id: str,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a skill and record the execution."""
        skill = self.get_skill(skill_name)
        if not skill:
            return {"error": f"Skill '{skill_name}' not found"}

        if not skill.is_active:
            return {"error": f"Skill '{skill_name}' is not active"}

        # Check dependencies
        for dep in skill.dependencies:
            if dep.required and dep.skill_name not in self.skills:
                return {"error": f"Required dependency '{dep.skill_name}' not available"}

        # Create execution record
        execution = SkillExecution(
            skill_name=skill_name,
            executor_id=executor_id,
            input_data=input_data,
            status="running",
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self.executions.append(execution)

        # Simulate execution (in real implementation, this would call the actual skill)
        try:
            # TODO: Replace with actual skill execution logic
            output_data = {
                "status": "success",
                "skill": skill_name,
                "executor": executor_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            execution.status = "completed"
            execution.output_data = output_data
            execution.completed_at = datetime.now(timezone.utc).isoformat()

            # Calculate duration
            if execution.started_at:
                start = datetime.fromisoformat(execution.started_at)
                end = datetime.fromisoformat(execution.completed_at)
                execution.duration_seconds = (end - start).total_seconds()

            return {
                "success": True,
                "execution": execution.to_dict(),
                "output": output_data,
            }
        except Exception as e:
            execution.status = "failed"
            execution.error = str(e)
            execution.completed_at = datetime.now(timezone.utc).isoformat()

            return {
                "success": False,
                "error": str(e),
                "execution": execution.to_dict(),
            }

    def get_execution_history(
        self,
        skill_name: str | None = None,
        executor_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get execution history."""
        result = []
        for exec_record in reversed(self.executions):
            if skill_name and exec_record.skill_name != skill_name:
                continue
            if executor_id and exec_record.executor_id != executor_id:
                continue
            result.append(exec_record.to_dict())
            if len(result) >= limit:
                break
        return result

    def get_skill_stats(self, skill_name: str) -> dict[str, Any]:
        """Get statistics for a skill."""
        skill_executions = [e for e in self.executions if e.skill_name == skill_name]

        if not skill_executions:
            return {
                "skill_name": skill_name,
                "total_executions": 0,
                "success_count": 0,
                "failure_count": 0,
                "avg_duration": 0,
            }

        completed = [e for e in skill_executions if e.status == "completed"]
        failed = [e for e in skill_executions if e.status == "failed"]

        avg_duration = 0
        if completed:
            durations = [e.duration_seconds for e in completed if e.duration_seconds]
            avg_duration = sum(durations) / len(durations) if durations else 0

        return {
            "skill_name": skill_name,
            "total_executions": len(skill_executions),
            "success_count": len(completed),
            "failure_count": len(failed),
            "success_rate": len(completed) / len(skill_executions) if skill_executions else 0,
            "avg_duration": avg_duration,
        }

    def get_registry_summary(self) -> dict[str, Any]:
        """Get overall registry summary."""
        return {
            "total_skills": len(self.skills),
            "active_skills": len([s for s in self.skills.values() if s.is_active]),
            "total_executions": len(self.executions),
            "categories": list({s.category.value for s in self.skills.values()}),
        }


# Module-level singleton
_skill_registry: SkillRegistry | None = None


def get_skill_registry() -> SkillRegistry:
    """Get or create singleton SkillRegistry."""
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillRegistry()
    return _skill_registry


def list_skills(category: SkillCategory | None = None) -> list[dict[str, Any]]:
    """Convenience function to list skills."""
    return get_skill_registry().list_skills(category)


def execute_skill(
    skill_name: str,
    executor_id: str,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    """Convenience function to execute a skill."""
    return get_skill_registry().execute_skill(skill_name, executor_id, input_data)


def get_skill_stats(skill_name: str) -> dict[str, Any]:
    """Convenience function to get skill stats."""
    return get_skill_registry().get_skill_stats(skill_name)
