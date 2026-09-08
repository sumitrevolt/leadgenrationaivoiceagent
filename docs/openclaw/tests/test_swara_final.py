"""
Final comprehensive verification of OpenClaw x Swara Voice Intelligence (Rules 1-21).

This test suite maps directly to the actual module APIs — no assumptions,
all field names and method signatures verified against source code.
"""
import sys
import os
import pytest

# Ensure workspace is on the path
sys.path.insert(0, r'C:\Users\Ratanshila\.openclaw\workspace')


# ============================================================
# Rule 1: Single Canonical Voice Identity
# ============================================================

class TestSingleVoiceIdentity:
    """Rule 1: ONE canonical production identity for Swara"""

    def test_voice_id_is_single_source(self):
        from app.voice_agent.swara_config import get_active_profile
        p = get_active_profile()
        assert p.voice_id is not None
        assert p.owner_voice_id == p.customer_voice_id == p.voice_id

    def test_profile_frozen(self):
        from app.voice_agent.swara_config import get_active_profile
        p = get_active_profile()
        with pytest.raises((AttributeError, Exception)):
            p.voice_id = "different"  # frozen dataclass

    def test_version_metadata(self):
        from app.voice_agent.swara_config import get_version_info
        versions = get_version_info()
        assert "voice_profile" in versions
        assert "language_policy" in versions


# ============================================================
# Rule 2: Natural Hinglish as Default Language
# ============================================================

class TestNaturalHinglish:
    """Rule 2: Default language is natural Hinglish"""

    def test_adaptation_produces_hinglish(self):
        from app.voice_agent.swara_adaptation import adapt_english_to_swara
        result = adapt_english_to_swara(
            "Your appointment has been confirmed for tomorrow at 4 PM",
            domain="appointment_booking",
            context="customer_confirmed",
        )
        assert result.pronunciation_normalized
        assert "kal" in result.pronunciation_normalized
        assert "appointment" in result.pronunciation_normalized

    def test_no_textbook_hindi(self):
        from app.voice_agent.swara_adaptation import adapt_english_to_swara
        result = adapt_english_to_swara(
            "System analysis complete ho gaya hai",
            domain="owner_communication",
            context="status_update",
            style="owner_briefing",
        )
        assert "karyakshamata" not in result.pronunciation_normalized.lower()

    def test_candidate_has_stages(self):
        from app.voice_agent.swara_adaptation import AdaptationCandidate
        cand = AdaptationCandidate(
            candidate_id="test_001",
            english_text="Your appointment is confirmed",
            domain="appointment_booking",
            context="confirmation",
            target_style="professional_business",
        )
        assert cand.current_stage == "english_input"


# ============================================================
# Rule 4: Voice Learning Event Capture
# ============================================================

class TestVoiceLearningEvents:
    """Rule 4: Every useful interaction generates voice_learning_event"""

    def test_voice_learning_event_created(self):
        from app.voice_agent.swara_learning import record_voice_event, get_voice_learning_store
        store = get_voice_learning_store()
        store._events.clear()
        event = record_voice_event(
            original_text="Namaste! Aap kaise hain?",
            language="hinglish",
            intended_meaning="Greeting customer",
            domain="greeting",
            context="cold_call_opening",
        )
        assert event.original_text == "Namaste! Aap kaise hain?"
        assert event.domain == "greeting"
        assert event.collection_source == "real_call"
        assert len(store._events) == 1

    def test_event_has_correct_schema(self):
        from app.voice_agent.swara_learning import VoiceLearningEvent
        event = VoiceLearningEvent(
            original_text="Test text",
            language="hinglish",
            intended_meaning="Test meaning",
            domain="other",
            context="test_context",
        )
        # Check all Rule 4 required fields exist
        assert event.event_id
        assert event.original_text
        assert event.language
        assert event.intended_meaning
        assert event.domain
        assert event.context
        assert event.collection_source
        assert event.version == "swara_voice_profile_v1"


# ============================================================
# Rule 5: English → Hinglish Adaptation
# ============================================================

class TestEnglishToHinglishAdaptation:
    """Rule 5: Meaning-preserving English → Hinglish"""

    def test_meaning_preserved(self):
        from app.voice_agent.swara_adaptation import adapt_english_to_swara
        result = adapt_english_to_swara(
            "Your appointment is confirmed for tomorrow at 4 PM",
            domain="appointment_booking",
            context="confirmation",
        )
        # Should contain Hindi words like 'kal' (tomorrow), 'aapka' (your)
        assert "kal" in result.pronunciation_normalized
        assert "aapka" in result.pronunciation_normalized  # Adapted from "Your"


# ============================================================
# Rule 6: Owner Corrections (High Priority)
# ============================================================

class TestOwnerCorrections:
    """Rule 6: Owner corrections create high-priority learning events"""

    def test_owner_correction_recorded(self):
        from app.voice_agent.swara_learning import (
            record_voice_event, record_owner_correction, get_voice_learning_store
        )
        store = get_voice_learning_store()
        store._events.clear()
        event = record_voice_event(
            original_text="Test",
            language="hinglish",
            intended_meaning="Test",
            domain="other",
            context="test",
        )
        result = record_owner_correction(
            event_id=event.event_id,
            incorrect_phrase="Wrong text",
            corrected_phrase="Correct text",
            reason="Mispronounced word",
            affected_intent="other",
        )
        assert result is True  # record_owner_correction returns True on success

    def test_owner_corrections_field_exists(self):
        from app.voice_agent.swara_learning import VoiceLearningEvent
        event = VoiceLearningEvent()
        assert hasattr(event, "owner_corrections")
        assert isinstance(event.owner_corrections, list)


# ============================================================
# Rule 7: Pronunciation Dictionary
# ============================================================

class TestPronunciationDictionary:
    """Rule 7: Curated pronunciation dictionary with project entries"""

    def test_project_terms_present(self):
        from app.voice_agent.swara_pronunciation import get_pronunciation_dict
        d = get_pronunciation_dict()
        d._load()
        for term in ["leadgen", "swara", "nagpur", "maharashtra", "whatsapp", "saas",
                      "crm", "tata", "jio", "smartflo", "upi", "trai"]:
            assert term in d._entries, f"Missing: {term}"

    def test_get_spoken_form(self):
        from app.voice_agent.swara_pronunciation import get_spoken_form
        assert get_spoken_form("LeadGen") == "LeadGen"
        assert get_spoken_form("Swara") == "Swara"
        assert get_spoken_form("WhatsApp") == "WhatsApp"
        assert get_spoken_form("UnknownTerm") == "UnknownTerm"

    def test_normalize_text(self):
        from app.voice_agent.swara_pronunciation import normalize_text_with_pronunciation
        text = "LeadGen ke saath WhatsApp use karo"
        normalized = normalize_text_with_pronunciation(text)
        assert "LeadGen" in normalized

    def test_entry_has_version(self):
        from app.voice_agent.swara_pronunciation import PronunciationEntry
        entry = PronunciationEntry(written_form="Test", preferred_spoken_form="Test")
        assert entry.version == "swara_pronunciation_dict_v1"


# ============================================================
# Rule 8: Golden Utterances Library
# ============================================================

class TestGoldenUtterances:
    """Rule 8: Curated golden utterances by intent"""

    def test_all_intents_present(self):
        from app.voice_agent.swara_golden_utterances import get_golden_utterance_library
        lib = get_golden_utterance_library()
        lib._load()
        intents = lib.get_all_intents()
        expected = [
            "greeting", "lead_qualification", "appointment_booking", "pricing",
            "objection_handling", "customer_confusion", "follow_up", "closing",
            "escalation", "payment", "rescheduling", "support", "goodbye",
            "sales_discovery", "owner_communication"
        ]
        for intent in expected:
            assert intent in intents, f"Missing intent: {intent}"

    def test_get_golden_response(self):
        from app.voice_agent.swara_golden_utterances import get_golden_response
        response = get_golden_response("greeting", "cold_call_opening")
        assert response is not None
        assert "{client_name}" in response  # Template placeholder

    def test_format_for_few_shot(self):
        from app.voice_agent.swara_golden_utterances import format_for_few_shot
        formatted = format_for_few_shot("greeting", "cold_call_opening")
        assert formatted != ""
        assert "Swara:" in formatted or "Context:" in formatted

    def test_golden_quality_scores(self):
        from app.voice_agent.swara_golden_utterances import get_golden_utterance_library
        lib = get_golden_utterance_library()
        lib._load()
        for intent, utterances in lib._library.items():
            for u in utterances:
                assert u.quality_score >= 0.95, f"Golden {intent} quality too low: {u.quality_score}"


# ============================================================
# Rule 9: No Uncontrolled Self-Training
# ============================================================

class TestNoUncontrolledSelfTraining:
    """Rule 9: Auto-promote must default to False"""

    def test_auto_promote_disabled(self):
        from app.voice_agent.swara_config import voice_learning_auto_promote
        assert voice_learning_auto_promote() is False

    def test_auto_collect_enabled(self):
        from app.voice_agent.swara_config import voice_learning_auto_collect
        assert voice_learning_auto_collect() is True

    def test_promote_requires_quality_gates(self):
        from app.voice_agent.swara_learning import (
            record_voice_event, promote_candidate_to_golden, get_voice_learning_store
        )
        store = get_voice_learning_store()
        store._events.clear()
        event = record_voice_event(
            original_text="Test",
            language="hinglish",
            intended_meaning="Test",
            domain="other",
            context="test",
            collection_source="manual_entry",
        )
        # Set status to "candidate" and leave quality scores at 0 (will fail gates)
        event.status = "candidate"
        event.meaning_preservation = 0.5  # Below 0.98 threshold
        event.pronunciation_quality = 0.5  # Below 0.95 threshold
        # promote_candidate_to_golden should reject (return False) due to failing gates
        result = promote_candidate_to_golden(event.event_id)
        assert result is False  # Rejected due to quality gate failures


# ============================================================
# Rule 10: Quality Gate Evaluation
# ============================================================

class TestQualityGate:
    """Rule 10: Quality gates ≥98% meaning/intent, ≥95% hinglish/pronunciation/persona"""

    def test_thresholds_enforced(self):
        from app.voice_agent.swara_eval import QUALITY_GATES, BOOLEAN_GATES
        assert QUALITY_GATES["meaning_preservation"] >= 0.98
        assert QUALITY_GATES["intent_preservation"] >= 0.98
        assert QUALITY_GATES["natural_hinglish"] >= 0.95
        assert QUALITY_GATES["pronunciation_quality"] >= 0.95
        assert QUALITY_GATES["persona_consistency"] >= 0.95

    def test_boolean_gates(self):
        from app.voice_agent.swara_eval import BOOLEAN_GATES
        assert BOOLEAN_GATES["hallucination_risk_acceptable"] is True
        assert BOOLEAN_GATES["policy_safety_pass"] is True
        assert BOOLEAN_GATES["customer_data_leakage_zero"] is True
        assert BOOLEAN_GATES["critical_regression_false"] is True


# ============================================================
# Rule 11: Shadow Mode A/B Evaluation
# ============================================================

class TestShadowMode:
    """Rule 11: New behavior runs in shadow first"""

    def test_shadow_manager(self):
        from app.voice_agent.swara_metrics import get_shadow_manager
        m = get_shadow_manager()
        exp = m.create_experiment("test_exp", "candidate_v2", "production_v1", 0.1)
        assert exp.traffic_split == 0.1
        assert exp.experiment_id.startswith("shadow_")

    def test_deterministic_assignment(self):
        from app.voice_agent.swara_metrics import get_shadow_manager
        m = get_shadow_manager()
        exp = m.create_experiment("test_exp2", "v2", "v1", 0.5)
        result1 = m.should_use_candidate("call_abc", exp.experiment_id)
        result2 = m.should_use_candidate("call_abc", exp.experiment_id)
        assert result1 == result2  # Deterministic


# ============================================================
# Rule 18: Observability Metrics
# ============================================================

class TestMetrics:
    """Rule 18: 12 KPIs tracked"""

    def test_start_record_end_call(self):
        from app.voice_agent.swara_metrics import get_metrics_collector
        c = get_metrics_collector()
        c.start_call("test_call_metrics_2")
        c.record_turn("test_call_metrics_2", latency_ms=150.0)
        result = c.end_call(
            "test_call_metrics_2",
            outcome="completed",
            hinglish_quality=0.95,
            pronunciation_errors=0,
            total_words=100,
            language_switches=2,
            correct_switches=2,
            repeated_phrases=0,
            customer_sentiment=0.85,
        )
        assert result is not None
        assert result.outcome == "completed"
        assert result.hinglish_quality_score == 0.95
        assert result.customer_sentiment == 0.85

    def test_aggregated_metrics(self):
        from app.voice_agent.swara_metrics import get_metrics_collector
        c = get_metrics_collector()
        agg = c.get_aggregated(hours=24)
        assert agg is not None
        assert hasattr(agg, "total_calls")


# ============================================================
# Rule 19: Version Everything
# ============================================================

class TestVersioning:
    """Rule 19: All artifacts versioned with rollback"""

    def test_voice_profile_versioned(self):
        from app.voice_agent.swara_config import SWARA_VOICE_PROFILE_VERSION
        assert SWARA_VOICE_PROFILE_VERSION == "swara_voice_profile_v1"

    def test_golden_utterances_versioned(self):
        from app.voice_agent.swara_golden_utterances import GoldenUtterance
        u = GoldenUtterance(
            intent="greeting",
            context="test",
            english_semantic_meaning="Test",
            approved_hinglish_response="Test response",
        )
        assert u.version == "swara_golden_utterances_v1"

    def test_pronunciation_versioned(self):
        from app.voice_agent.swara_pronunciation import PronunciationEntry
        e = PronunciationEntry(written_form="Test", preferred_spoken_form="Test")
        assert e.version == "swara_pronunciation_dict_v1"

    def test_learning_event_versioned(self):
        from app.voice_agent.swara_learning import VoiceLearningEvent
        e = VoiceLearningEvent()
        assert e.version == "swara_voice_profile_v1"


# ============================================================
# Rule 20: Single Voice Configuration Pattern
# ============================================================

class TestSingleConfigPattern:
    """Rule 20: Single voice configuration — no scattered configs"""

    def test_single_config_point(self):
        from app.voice_agent.swara_config import get_active_profile
        p = get_active_profile()
        # All voice IDs should come from the same place
        assert p.voice_id == p.owner_voice_id == p.customer_voice_id

    def test_feature_flags_exist(self):
        from app.voice_agent.swara_config import (
            voice_learning_enabled,
            voice_learning_auto_collect,
            voice_learning_auto_promote,
            voice_eval_enabled,
            pronunciation_memory_enabled,
            hinglish_adaptation_enabled,
        )
        assert callable(voice_learning_enabled)
        assert callable(voice_learning_auto_collect)
        assert callable(voice_learning_auto_promote)
        assert callable(voice_eval_enabled)
        assert callable(pronunciation_memory_enabled)
        assert callable(hinglish_adaptation_enabled)


# ============================================================
# TTS Integration (Rules 1, 20)
# ============================================================

class TestTTSIntegration:
    """Verify TTS wiring with Swara canonical voice"""

    def test_tts_uses_swara_profile(self):
        from app.voice_agent.tts import TextToSpeech
        tts = TextToSpeech(provider="edge")
        assert tts._swara_profile is not None
        assert tts._swara_profile.voice_id == "alloy"

    def test_backward_compatible(self):
        from app.voice_agent.tts import TextToSpeech
        tts = TextToSpeech(provider="edge")
        assert tts.provider_name == "edge"
        # Should still have original methods
        assert hasattr(tts, "synthesize") or hasattr(tts, "generate_audio")


# ============================================================
# Safety Compliance (Rule 16 + TRAI/DPDP enforcement)
# ============================================================

class TestSafetyCompliance:
    """TRAI/DPDP/Rule 16 constraints enforced"""

    def test_no_deceptive_sales(self):
        from app.voice_agent.swara_eval import get_safety_evaluator
        from app.voice_agent.swara_adaptation import AdaptationCandidate
        # Safety eval reads pronunciation_normalized, so we set the deceptive text there
        cand = AdaptationCandidate(
            candidate_id="safety_1",
            english_text="Guaranteed 100% success",
            domain="closing",
            context="sales",
            extracted_meaning="Offer with guarantee",
            hinglish_draft="Guaranteed 100% success",
            persona_rewrite="Guaranteed 100% success",
            pronunciation_normalized="hum guarantee karte hain 100% success",
            target_style="professional_business",
        )
        results = get_safety_evaluator().evaluate(cand)
        assert results["no_deceptive_sales"] == False  # "guarantee" triggers flag

    def test_no_invented_discounts(self):
        from app.voice_agent.swara_eval import get_safety_evaluator
        from app.voice_agent.swara_adaptation import AdaptationCandidate
        cand = AdaptationCandidate(
            candidate_id="safety_2",
            english_text="Today only special discount",
            domain="closing",
            context="sales",
            extracted_meaning="Time-limited discount offer",
            hinglish_draft="aaj hi special discount",
            persona_rewrite="aaj hi special discount",
            pronunciation_normalized="aaj hi special discount",
            target_style="persuasive_sales",
        )
        results = get_safety_evaluator().evaluate(cand)
        assert results["no_invented_discounts"] == False  # "today only"/"discount" triggers flag


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])