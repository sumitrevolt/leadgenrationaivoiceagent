"""Final verification test for Swara Voice Intelligence modules."""
import sys
import pytest

sys.path.insert(0, r'C:\Users\Ratanshila\.openclaw\workspace')


class TestSwaraConfig:
    """Rule 1: Single canonical voice; Rule 20: Single configuration"""

    def test_profile_voice_id_single_source(self):
        from app.voice_agent.swara_config import get_active_profile
        p = get_active_profile()
        assert p.voice_id == p.owner_voice_id == p.customer_voice_id

    def test_auto_promote_disabled(self):
        """Rule 9: auto-promote must stay False"""
        from app.voice_agent.swara_config import voice_learning_auto_promote
        assert voice_learning_auto_promote() is False

    def test_versions_present(self):
        from app.voice_agent.swara_config import get_version_info
        versions = get_version_info()
        assert "voice_profile" in versions
        assert "language_policy" in versions


class TestPronunciationDict:
    """Rule 7: Pronunciation dictionary"""

    def test_project_terms(self):
        from app.voice_agent.swara_pronunciation import get_pronunciation_dict, get_spoken_form
        d = get_pronunciation_dict()
        d._load()
        assert "leadgen" in d._entries
        assert "swara" in d._entries
        assert "nagpur" in d._entries

    def test_spoken_forms(self):
        from app.voice_agent.swara_pronunciation import get_spoken_form
        assert get_spoken_form("LeadGen") == "LeadGen"
        assert get_spoken_form("Swara") == "Swara"
        assert get_spoken_form("Unknown") == "Unknown"

    def test_normalize(self):
        from app.voice_agent.swara_pronunciation import normalize_text_with_pronunciation
        result = normalize_text_with_pronunciation("LeadGen WhatsApp use karo")
        assert "LeadGen" in result and "WhatsApp" in result


class TestGoldenUtterances:
    """Rule 8: Golden utterances library"""

    def test_all_intents(self):
        from app.voice_agent.swara_golden_utterances import get_golden_utterance_library
        lib = get_golden_utterance_library()
        lib._load()
        intents = lib.get_all_intents()
        for expected in ["greeting", "lead_qualification", "appointment_booking",
                          "pricing", "objection_handling", "closing"]:
            assert expected in intents

    def test_golden_response(self):
        from app.voice_agent.swara_golden_utterances import get_golden_response
        response = get_golden_response("greeting", "cold_call_opening")
        assert response is not None
        assert "{client_name}" in response


class TestAdaptation:
    """Rule 5: English → Hinglish pipeline"""

    def test_produce_hinglish(self):
        from app.voice_agent.swara_adaptation import adapt_english_to_swara
        result = adapt_english_to_swara(
            "Your appointment is confirmed for tomorrow at 4 PM",
            domain="appointment_booking", context="confirm"
        )
        assert "kal" in result.pronunciation_normalized

    def test_owner_briefing_style(self):
        from app.voice_agent.swara_adaptation import adapt_english_to_swara
        result = adapt_english_to_swara(
            "System status update", domain="owner_communication",
            context="status", style="owner_briefing"
        )
        assert result is not None


class TestLearning:
    """Rules 4, 6: Learning events"""

    def test_record_event(self):
        from app.voice_agent.swara_learning import record_voice_event, get_voice_learning_store
        store = get_voice_learning_store()
        store._events.clear()
        event = record_voice_event(
            original_text="Namaste", language="hinglish",
            intended_meaning="Greeting", domain="greeting",
            context="opening"
        )
        assert len(store._events) == 1
        assert event.domain == "greeting"

    def test_owner_correction(self):
        from app.voice_agent.swara_learning import record_voice_event, record_owner_correction, get_voice_learning_store
        store = get_voice_learning_store()
        store._events.clear()
        event = record_voice_event(
            original_text="Test", language="hinglish",
            intended_meaning="Test", domain="other", context="test"
        )
        result = record_owner_correction(event.event_id, "wrong", "correct", "reason", "intent")
        assert result is True


class TestQualityGate:
    """Rules 9-10: Quality gates"""

    def test_thresholds(self):
        from app.voice_agent.swara_eval import QUALITY_GATES, BOOLEAN_GATES
        assert QUALITY_GATES["meaning_preservation"] >= 0.98
        assert QUALITY_GATES["intent_preservation"] >= 0.98
        assert QUALITY_GATES["natural_hinglish"] >= 0.95

    def test_high_quality_passes(self):
        from app.voice_agent.swara_eval import get_quality_evaluator
        from app.voice_agent.swara_adaptation import AdaptationCandidate
        cand = AdaptationCandidate(
            candidate_id="t1", english_text="Confirmed", domain="appointment", context="confirm",
            extracted_meaning="Appointment confirmed", hinglish_draft="appointment confirm ho gayi",
            persona_rewrite="appointment confirm ho gayi", pronunciation_normalized="appointment confirm ho gayi"
        )
        result = get_quality_evaluator().evaluate_candidate(cand)
        assert result is not None

    def test_safety_no_deception(self):
        from app.voice_agent.swara_eval import get_safety_evaluator
        from app.voice_agent.swara_adaptation import AdaptationCandidate
        cand = AdaptationCandidate(
            candidate_id="t2", english_text="Guaranteed 100% success today only",
            domain="closing", context="sales",
            extracted_meaning="Offer with guarantee", hinglish_draft="guarantee",
            persona_rewrite="guarantee", pronunciation_normalized="guarantee"
        )
        results = get_safety_evaluator().evaluate(cand)
        assert results["no_deceptive_sales"] == False


class TestShadowMode:
    """Rule 11: Shadow mode"""

    def test_experiment(self):
        from app.voice_agent.swara_metrics import get_shadow_manager
        m = get_shadow_manager()
        exp = m.create_experiment("e1", "v2", "v1", 0.1)
        assert exp.traffic_split == 0.1

    def test_assignment(self):
        from app.voice_agent.swara_metrics import get_shadow_manager
        m = get_shadow_manager()
        exp = m.create_experiment("e2", "v2", "v1", 0.5)
        a = m.should_use_candidate("call_1", exp.experiment_id)
        assert isinstance(a, bool)


class TestMetrics:
    """Rule 18: Observability"""

    def test_call_metrics(self):
        from app.voice_agent.swara_metrics import get_metrics_collector
        c = get_metrics_collector()
        c.start_call("m1")
        c.record_turn("m1", latency_ms=100)
        result = c.end_call("m1", outcome="completed", hinglish_quality=0.9)
        assert result is not None
        assert result.outcome == "completed"

    def test_aggregated(self):
        from app.voice_agent.swara_metrics import get_metrics_collector
        c = get_metrics_collector()
        agg = c.get_aggregated(hours=1)
        assert agg is not None


class TestTTSWiring:
    """Verify TTS integration"""

    def test_tts_swara_profile(self):
        from app.voice_agent.tts import TextToSpeech
        tts = TextToSpeech(provider="edge")
        assert tts._swara_profile is not None
        assert tts._swara_profile.voice_id is not None

    def test_tts_backward_compat(self):
        from app.voice_agent.tts import TextToSpeech
        tts = TextToSpeech(provider="edge")
        assert tts.provider_name == "edge"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])