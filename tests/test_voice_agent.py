"""
Tests for Voice Agent Components
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock

from app.voice_agent.intent_detector import IntentDetector, DetectedIntent
from app.voice_agent.conversation import ConversationManager, ConversationState


class TestIntentDetector:
    """Test intent detection"""
    
    @pytest.fixture
    def detector(self):
        return IntentDetector(use_llm_fallback=False)
    
    @pytest.mark.asyncio
    async def test_detect_greeting(self, detector):
        """Test greeting detection"""
        result = await detector.detect("Hello")
        assert result.intent_type == "greeting"
        assert result.confidence > 0.5
    
    @pytest.mark.asyncio
    async def test_detect_interested(self, detector):
        """Test interest detection"""
        result = await detector.detect("Yes, I'm interested in this, tell me more")
        assert result.intent_type == "interested"
    
    @pytest.mark.asyncio
    async def test_detect_not_interested(self, detector):
        """Test not interested detection"""
        result = await detector.detect("No thanks, not interested")
        assert result.intent_type == "not_interested"
    
    @pytest.mark.asyncio
    async def test_detect_busy(self, detector):
        """Test busy detection"""
        result = await detector.detect("I'm in a meeting")
        assert result.intent_type == "busy"
    
    @pytest.mark.asyncio
    async def test_detect_callback_request(self, detector):
        """Test callback request detection"""
        result = await detector.detect("Can you call me later tomorrow?")
        assert result.intent_type == "callback_request"
    
    @pytest.mark.asyncio
    async def test_detect_appointment(self, detector):
        """Test appointment intent detection"""
        result = await detector.detect("Let's schedule a meeting")
        assert result.intent_type == "appointment_interest"


class TestConversationManager:
    """Test conversation management"""
    
    @pytest.fixture
    def manager(self):
        return ConversationManager()
    
    @pytest.fixture
    def call_id(self):
        return "test-call-123"
    
    def test_start_conversation(self, manager, call_id):
        """Test starting a conversation"""
        context = manager.start_conversation(call_id)
        assert context.call_id == call_id
        assert context.state == ConversationState.OPENING
        assert len(context.turns) == 0
    
    def test_add_turn(self, manager, call_id):
        """Test adding conversation turn"""
        manager.start_conversation(call_id)
        context = manager.add_turn(call_id, "user", "Hello")
        assert len(context.turns) == 1
        assert context.turns[0].content == "Hello"
        assert context.turns[0].role == "user"
    
    def test_get_conversation(self, manager, call_id):
        """Test getting a conversation"""
        manager.start_conversation(call_id)
        context = manager.get_conversation(call_id)
        assert context is not None
        assert context.call_id == call_id
    
    def test_get_nonexistent_conversation(self, manager):
        """Test getting a conversation that doesn't exist"""
        context = manager.get_conversation("nonexistent-call")
        assert context is None
    
    def test_add_turn_to_nonexistent_conversation(self, manager):
        """Test adding turn to nonexistent conversation raises error"""
        with pytest.raises(ValueError):
            manager.add_turn("nonexistent-call", "user", "Hello")
    
    def test_multiple_turns(self, manager, call_id):
        """Test adding multiple turns"""
        manager.start_conversation(call_id)
        manager.add_turn(call_id, "assistant", "Good morning!")
        manager.add_turn(call_id, "user", "Hi, I'm interested")
        context = manager.add_turn(call_id, "assistant", "Great to hear!")
        
        assert len(context.turns) == 3


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
