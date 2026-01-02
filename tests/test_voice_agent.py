"""
Tests for Voice Agent Components
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock

from app.voice_agent.intent_detector import IntentDetector, IntentResult
from app.voice_agent.conversation import ConversationManager, ConversationState


class TestIntentDetector:
    """Test intent detection"""
    
    @pytest.fixture
    def detector(self):
        return IntentDetector()
    
    def test_detect_greeting(self, detector):
        """Test greeting detection"""
        result = detector.detect_from_patterns("Hello, good morning")
        assert result.intent == "greeting"
        assert result.confidence > 0.5
    
    def test_detect_interested(self, detector):
        """Test interest detection"""
        result = detector.detect_from_patterns("Yes, I'm interested in this")
        assert result.intent == "interested"
    
    def test_detect_not_interested(self, detector):
        """Test not interested detection"""
        result = detector.detect_from_patterns("No thanks, not interested")
        assert result.intent == "not_interested"
    
    def test_detect_busy(self, detector):
        """Test busy detection"""
        result = detector.detect_from_patterns("I'm busy right now, in a meeting")
        assert result.intent == "busy"
    
    def test_detect_callback_request(self, detector):
        """Test callback request detection"""
        result = detector.detect_from_patterns("Can you call me later tomorrow?")
        assert result.intent == "callback_request"
    
    def test_detect_appointment(self, detector):
        """Test appointment intent detection"""
        result = detector.detect_from_patterns("Sure, let's schedule a meeting")
        assert result.intent == "appointment"


class TestConversationManager:
    """Test conversation management"""
    
    @pytest.fixture
    def manager(self):
        return ConversationManager(
            lead_id="test-lead",
            niche="real_estate",
            client_name="Test Client",
            client_service="Property Sales"
        )
    
    def test_initial_state(self, manager):
        """Test initial conversation state"""
        assert manager.state == ConversationState.GREETING
        assert manager.turn_count == 0
    
    def test_add_turn(self, manager):
        """Test adding conversation turn"""
        manager.add_turn("user", "Hello")
        assert manager.turn_count == 1
        assert len(manager.history) == 1
    
    def test_state_transition_to_introduction(self, manager):
        """Test state transition to introduction"""
        manager.transition_state(ConversationState.INTRODUCTION)
        assert manager.state == ConversationState.INTRODUCTION
    
    def test_update_qualification(self, manager):
        """Test qualification data update"""
        manager.update_qualification(
            is_decision_maker=True,
            budget="50 lakhs",
            timeline="3 months"
        )
        
        assert manager.qualification_data["is_decision_maker"] == True
        assert manager.qualification_data["budget"] == "50 lakhs"
    
    def test_calculate_lead_score(self, manager):
        """Test lead score calculation"""
        manager.update_qualification(
            is_decision_maker=True,
            budget="50 lakhs",
            timeline="3 months",
            interest_level="high"
        )
        
        score = manager.calculate_lead_score()
        assert score > 50  # Should be high score with good qualification
    
    def test_should_ask_more_questions(self, manager):
        """Test question asking logic"""
        assert manager.should_ask_more_questions() == True
        
        # Answer all questions
        manager.update_qualification(
            is_decision_maker=True,
            budget="50 lakhs",
            timeline="3 months",
            pain_points="High costs"
        )
        
        # Should have fewer questions to ask
    
    def test_get_summary(self, manager):
        """Test getting conversation summary"""
        manager.add_turn("user", "Hello")
        manager.add_turn("agent", "Good morning!")
        
        summary = manager.get_summary()
        
        assert summary["lead_id"] == "test-lead"
        assert summary["turn_count"] == 2
        assert summary["state"] == "greeting"


class TestPhoneValidator:
    """Test phone validation"""
    
    def test_valid_indian_mobile(self):
        from app.utils.phone_validator import PhoneValidator
        
        result = PhoneValidator.validate("+919876543210")
        assert result.is_valid == True
        assert result.is_mobile == True
        assert result.country_code == "91"
    
    def test_valid_indian_mobile_without_code(self):
        from app.utils.phone_validator import PhoneValidator
        
        result = PhoneValidator.validate("9876543210")
        assert result.is_valid == True
        assert result.country_code == "91"
    
    def test_invalid_phone(self):
        from app.utils.phone_validator import PhoneValidator
        
        result = PhoneValidator.validate("123")
        assert result.is_valid == False
    
    def test_format_for_display(self):
        from app.utils.phone_validator import PhoneValidator
        
        formatted = PhoneValidator.format_for_display("9876543210")
        assert "+91" in formatted
    
    def test_mask_phone(self):
        from app.utils.phone_validator import PhoneValidator
        
        masked = PhoneValidator.mask_phone("9876543210")
        assert "****" in masked
        assert "9876543210" not in masked
