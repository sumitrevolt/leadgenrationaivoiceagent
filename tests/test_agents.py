"""Tests for Worker Bots, Agent Bots, and Skill Registry."""

import pytest
from app.agents.workers import (
    WorkerManager,
    WorkerRole,
    DataAnalystWorker,
    ContentCreatorWorker,
    LeadGeneratorWorker,
    QualityAssuranceWorker,
    EmailSpecialistWorker,
    SocialMediaWorker,
    VoiceAgentWorker,
    CRMManagerWorker,
    ReportingWorker,
)
from app.agents.agents import AgentManager, AgentProfile
from app.agents.skills import SkillRegistry, SkillCategory, SkillTypeDef


class TestWorkerBots:
    """Test 9 worker bots."""
    
    def test_worker_manager_initialization(self):
        """Test that all 9 workers are created."""
        manager = WorkerManager()
        workers = manager.list_workers()
        assert len(workers) == 9
    
    def test_worker_roles(self):
        """Test all worker roles are present."""
        manager = WorkerManager()
        workers = manager.list_workers()
        roles = [w["role"] for w in workers]
        
        expected_roles = [
            "data_analyst",
            "content_creator",
            "lead_generator",
            "quality_assurance",
            "email_specialist",
            "social_media",
            "voice_agent",
            "crm_manager",
            "reporting",
        ]
        for role in expected_roles:
            assert role in roles
    
    def test_data_analyst_skills(self):
        """Test DataAnalystWorker has expected skills."""
        worker = DataAnalystWorker()
        skills = list(worker.skills.keys())
        assert "analyze_prospects" in skills
        assert "score_leads" in skills
        assert "generate_report" in skills
    
    def test_content_creator_skills(self):
        """Test ContentCreatorWorker has expected skills."""
        worker = ContentCreatorWorker()
        skills = list(worker.skills.keys())
        assert "create_social_post" in skills
        assert "generate_email" in skills
    
    def test_execute_task(self):
        """Test task execution on worker."""
        manager = WorkerManager()
        result = manager.execute_task(
            "worker_data_analyst",
            "analyze_prospects",
            {"dataset": ["lead1", "lead2"]}
        )
        assert result["success"] is True
        assert "task_id" in result
    
    def test_unknown_worker(self):
        """Test execution on non-existent worker."""
        manager = WorkerManager()
        result = manager.execute_task(
            "nonexistent",
            "some_skill",
            {}
        )
        assert "error" in result


class TestAgentBots:
    """Test 31 agent bots."""
    
    def test_agent_manager_initialization(self):
        """Test that all 31 agents are created."""
        manager = AgentManager()
        agents = manager.list_agents()
        assert len(agents) == 31
    
    def test_agent_products(self):
        """Test agents are distributed across products."""
        manager = AgentManager()
        marketing = len([a for a in manager.list_agents() if a["product"] == "marketing"])
        voice = len([a for a in manager.list_agents() if a["product"] == "voice"])
        platform = len([a for a in manager.list_agents() if a["product"] == "platform"])
        
        assert marketing > 0
        assert voice > 0
        assert platform > 0
    
    def test_get_agent_stats(self):
        """Test getting agent stats."""
        manager = AgentManager()
        stats = manager.get_agent_stats("manager")
        assert stats["agent_id"] == "manager"
        assert stats["name"] == "Boss"
    
    def test_activate_pause_agent(self):
        """Test activating and pausing agents."""
        manager = AgentManager()
        
        # Activate
        result = manager.activate_agent("dev")
        assert result["success"] is True
        
        # Pause
        result = manager.pause_agent("dev")
        assert result["success"] is True
    
    def test_daily_summary(self):
        """Test daily summary generation."""
        manager = AgentManager()
        summary = manager.get_daily_summary()
        assert summary["total_agents"] == 31
        assert "breakdown" in summary


class TestSkillRegistry:
    """Test TypeSafe skill registry."""
    
    def test_default_skills_registered(self):
        """Test default skills are registered."""
        registry = SkillRegistry()
        skills = registry.list_skills()
        assert len(skills) > 0
    
    def test_skill_categories(self):
        """Test skills have correct categories."""
        registry = SkillRegistry()
        skills = registry.list_skills()
        categories = set(s["category"] for s in skills)
        assert "data" in categories
        assert "content" in categories
        assert "voice" in categories
    
    def test_execute_skill(self):
        """Test skill execution."""
        registry = SkillRegistry()
        result = registry.execute_skill(
            "analyze_prospects",
            "test_executor",
            {"dataset": ["lead1"]}
        )
        assert result["success"] is True
    
    def test_skill_stats(self):
        """Test skill statistics."""
        registry = SkillRegistry()
        stats = registry.get_skill_stats("analyze_prospects")
        assert "total_executions" in stats
    
    def test_registry_summary(self):
        """Test registry summary."""
        registry = SkillRegistry()
        summary = registry.get_registry_summary()
        assert summary["total_skills"] > 0
        assert "categories" in summary


class TestIntegration:
    """Integration tests."""
    
    def test_worker_to_skill_flow(self):
        """Test worker using skill from registry."""
        from app.agents.workers import get_workers_manager
        from app.agents.skills import get_skill_registry
        
        manager = get_workers_manager()
        registry = get_skill_registry()
        
        # Execute skill through worker
        result = manager.execute_task(
            "worker_data_analyst",
            "analyze_prospects",
            {"dataset": ["test_lead"]}
        )
        assert result["success"] is True
