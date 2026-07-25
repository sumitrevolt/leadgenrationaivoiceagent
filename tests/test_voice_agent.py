"""
Tests for Voice Agent Components
"""

import pytest

from app.voice_agent.intent_detector import IntentDetector
from app.voice_agent.telecaller_brain import TelecallerBrain


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


class TestPhoneValidator:
    """Test phone validation"""

    def test_valid_indian_mobile(self):
        from app.utils.phone_validator import PhoneValidator

        result = PhoneValidator.validate("+919876543210")
        assert result.is_valid
        assert result.is_mobile
        assert result.country_code == "91"

    def test_valid_indian_mobile_without_code(self):
        from app.utils.phone_validator import PhoneValidator

        result = PhoneValidator.validate("9876543210")
        assert result.is_valid
        assert result.country_code == "91"

    def test_invalid_phone(self):
        from app.utils.phone_validator import PhoneValidator

        result = PhoneValidator.validate("123")
        assert not result.is_valid

    def test_format_for_display(self):
        from app.utils.phone_validator import PhoneValidator

        formatted = PhoneValidator.format_for_display("9876543210")
        assert "+91" in formatted

    def test_mask_phone(self):
        from app.utils.phone_validator import PhoneValidator

        masked = PhoneValidator.mask_phone("9876543210")
        assert "****" in masked
        assert "9876543210" not in masked


class TestTelecallerBrainProfessionalism:
    """Test professionalism guidelines in telecalling prompts and scripts"""

    def test_telecaller_brain_system_prompt_contains_professionalism_rule(self):
        brain = TelecallerBrain(niche="solar_residential", client_name="Sharma Solar")
        prompt = brain.system_prompt.lower()
        assert "professional" in prompt
        assert "customer ko respectfully 'aap'" in prompt
        assert "habitual fillers banned" in prompt
        assert "kabhi 'tum', 'tu', 'yaar', 'bhai' mat karo" in prompt

    def test_niche_script_objections_are_polite(self):
        from app.voice_agent.niche_scripts import get_script

        coaching = get_script("coaching")
        assert "kar lena" not in coaching["objections"]["soch_ke"]
        assert "kar lijiye" in coaching["objections"]["soch_ke"]

        ai_marketing = get_script("ai_marketing")
        assert "paisa vasool" not in ai_marketing["objections"]["mehenga"]
        assert "aage badhna" not in ai_marketing["objections"]["bharosa"]
        assert "aage badhiye" in ai_marketing["objections"]["bharosa"]
        assert ai_marketing.get("pitch_short")
        assert (
            "LeadGen AI" in ai_marketing["opening"]
            or "Leads Generation AI" in ai_marketing["opening"]
        )

    def test_telecaller_confirm_interest_appends_note(self):
        brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
        assert "PLATFORM NOTE" not in brain.system_prompt
        brain.confirm_interest()
        assert "PLATFORM NOTE" in brain.system_prompt
        brain.confirm_interest()  # idempotent
        assert brain.system_prompt.count("PLATFORM NOTE") == 1


class TestNaturalDialogManagerProfessionalism:
    """Test professionalism in natural dialog manager prompts"""

    def test_voice_system_prompt_contains_professionalism_rule(self):
        # VOICE_SYSTEM_PROMPT is exported by the module
        from app.voice_agent.natural_dialog import VOICE_SYSTEM_PROMPT

        assert "aap" in VOICE_SYSTEM_PROMPT.lower()
        assert "sir/madam" in VOICE_SYSTEM_PROMPT.lower()
        assert "professional" in VOICE_SYSTEM_PROMPT.lower()
        assert "slang" in VOICE_SYSTEM_PROMPT.lower()

    def test_explicit_brain_none_is_rule_based(self, monkeypatch):
        from app.voice_agent.natural_dialog import NaturalDialogManager

        def fail_build(_self):
            raise AssertionError("brain=None must not build LLMBrain")

        monkeypatch.setattr(NaturalDialogManager, "_build_brain", fail_build)
        mgr = NaturalDialogManager(niche="solar", brain=None)
        assert mgr.brain is None
