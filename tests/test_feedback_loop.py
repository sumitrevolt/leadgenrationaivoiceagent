"""Tests for Self-Improving Agent Loops."""

import pytest

import app.feedback.loop
from app.feedback.loop import (
    AgentPerformance,
    FeedbackRecord,
    ImprovementProposal,
    SelfImprovingLoop,
)


@pytest.fixture(autouse=True)
def isolate_loop_state(tmp_path, monkeypatch):
    test_state_file = str(tmp_path / "self_improve_state.json")
    orig_init = app.feedback.loop.SelfImprovingLoop.__init__
    monkeypatch.setattr(
        app.feedback.loop.SelfImprovingLoop,
        "__init__",
        lambda self, state_path=test_state_file: orig_init(self, state_path=state_path),
    )


class TestSelfImprovingLoop:
    """Test self-improving agent loop."""

    def test_initialization(self):
        """Test loop initialization."""
        loop = SelfImprovingLoop()
        assert loop.loop_enabled is False
        assert loop.quality_threshold == 0.7

    def test_record_feedback(self):
        """Test recording feedback."""
        loop = SelfImprovingLoop()
        record = loop.record_feedback(
            task_id="task-1",
            agent_id="agent-1",
            skill_name="analyze_prospects",
            input_data={"dataset": ["lead1"]},
            success=True,
            quality_score=0.8,
            duration_seconds=5.5,
        )
        assert record.task_id == "task-1"
        assert record.success is True
        assert len(loop.feedback_records) == 1

    def test_performance_tracking(self):
        """Test performance metrics tracking."""
        loop = SelfImprovingLoop()

        # Record multiple feedbacks
        for i in range(5):
            loop.record_feedback(
                task_id=f"task-{i}",
                agent_id="agent-1",
                skill_name="analyze_prospects",
                input_data={},
                success=i < 4,  # 4 successful, 1 failed
                quality_score=0.8 + (i * 0.05),
                duration_seconds=5.0,
            )

        # Check performance
        perf = loop.get_performance("agent-1", "analyze_prospects")
        assert len(perf) == 1
        assert perf[0]["total_tasks"] == 5
        assert perf[0]["successful_tasks"] == 4
        assert perf[0]["success_rate"] == 0.8

    def test_improvement_proposal_generation(self):
        """Test proposal generation for low-quality tasks."""
        loop = SelfImprovingLoop()
        loop.loop_enabled = True
        loop.quality_threshold = 0.7

        # Record feedback below threshold
        loop.record_feedback(
            task_id="task-low",
            agent_id="agent-1",
            skill_name="test_skill",
            input_data={},
            success=True,
            quality_score=0.5,  # Below threshold
        )

        # Should generate proposal
        proposals = loop.get_proposals(agent_id="agent-1")
        assert len(proposals) >= 1
        assert proposals[0]["agent_id"] == "agent-1"

    def test_approve_proposal(self):
        """Test approving a proposal."""
        loop = SelfImprovingLoop()
        loop.loop_enabled = True
        loop.quality_threshold = 0.7

        # Generate proposal
        loop.record_feedback(
            task_id="task-approve",
            agent_id="agent-1",
            skill_name="test_skill",
            input_data={},
            success=True,
            quality_score=0.5,
        )

        proposals = loop.get_proposals(agent_id="agent-1")
        if proposals:
            proposal_id = proposals[0]["proposal_id"]
            result = loop.approve_proposal(proposal_id, "admin")
            assert result["success"] is True
            assert result["proposal"]["status"] == "approved"

    def test_reject_proposal(self):
        """Test rejecting a proposal."""
        loop = SelfImprovingLoop()
        loop.loop_enabled = True
        loop.quality_threshold = 0.7

        # Generate proposal
        loop.record_feedback(
            task_id="task-reject",
            agent_id="agent-1",
            skill_name="test_skill",
            input_data={},
            success=True,
            quality_score=0.5,
        )

        proposals = loop.get_proposals(agent_id="agent-1")
        if proposals:
            proposal_id = proposals[0]["proposal_id"]
            result = loop.reject_proposal(proposal_id)
            assert result["success"] is True
            assert result["proposal"]["status"] == "rejected"

    def test_toggle_loop(self):
        """Test enabling/disabling loop."""
        loop = SelfImprovingLoop()

        # Enable
        result = loop.toggle_loop(True)
        assert result["loop_enabled"] is True

        # Disable
        result = loop.toggle_loop(False)
        assert result["loop_enabled"] is False

    def test_loop_status(self):
        """Test getting loop status."""
        loop = SelfImprovingLoop()
        status = loop.get_loop_status()

        assert "loop_enabled" in status
        assert "total_feedback_records" in status
        assert "total_proposals" in status
        assert "quality_threshold" in status

    def test_daily_limits(self):
        """Test daily proposal limits."""
        loop = SelfImprovingLoop()
        loop.loop_enabled = True
        loop.quality_threshold = 0.7
        loop.max_proposals_per_day = 2

        # Record enough feedback to trigger proposals
        for i in range(5):
            loop.record_feedback(
                task_id=f"task-limit-{i}",
                agent_id="agent-1",
                skill_name="test_skill",
                input_data={},
                success=True,
                quality_score=0.5,
            )

        # Should not exceed daily limit
        proposals = loop.get_proposals(agent_id="agent-1")
        assert len(proposals) <= 2


class TestFeedbackRecord:
    """Test FeedbackRecord model."""

    def test_feedback_creation(self):
        """Test creating feedback record."""
        record = FeedbackRecord(
            task_id="task-1",
            agent_id="agent-1",
            skill_name="test",
            input_data={"key": "value"},
            success=True,
            quality_score=0.9,
        )
        assert record.task_id == "task-1"
        assert record.success is True

    def test_feedback_to_dict(self):
        """Test converting to dict."""
        record = FeedbackRecord(
            task_id="task-1",
            agent_id="agent-1",
            skill_name="test",
            input_data={},
            success=True,
        )
        data = record.to_dict()
        assert data["task_id"] == "task-1"
        assert data["success"] is True


class TestImprovementProposal:
    """Test ImprovementProposal model."""

    def test_proposal_creation(self):
        """Test creating improvement proposal."""
        proposal = ImprovementProposal(
            proposal_id="imp-1",
            agent_id="agent-1",
            skill_name="test_skill",
            current_performance={"quality": 0.5},
            proposed_change="Improve skill",
            expected_improvement="Quality to 0.8",
            confidence=0.8,
        )
        assert proposal.proposal_id == "imp-1"
        assert proposal.status == "pending"

    def test_proposal_to_dict(self):
        """Test converting to dict."""
        proposal = ImprovementProposal(
            proposal_id="imp-1",
            agent_id="agent-1",
            skill_name="test",
            current_performance={},
            proposed_change="test",
            expected_improvement="test",
            confidence=0.7,
        )
        data = proposal.to_dict()
        assert data["proposal_id"] == "imp-1"
        assert data["status"] == "pending"


class TestAgentPerformance:
    """Test AgentPerformance model."""

    def test_performance_creation(self):
        """Test creating performance record."""
        perf = AgentPerformance(
            agent_id="agent-1",
            skill_name="test",
            total_tasks=10,
            successful_tasks=8,
        )
        assert perf.total_tasks == 10
        assert perf.success_rate == 0.8

    def test_performance_to_dict(self):
        """Test converting to dict."""
        perf = AgentPerformance(
            agent_id="agent-1",
            skill_name="test",
        )
        data = perf.to_dict()
        assert data["agent_id"] == "agent-1"
        assert data["skill_name"] == "test"
