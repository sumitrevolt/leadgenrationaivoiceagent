"""
TypeSafe Telephony Integration
===============================
Integrates TypeSafe Jev decisions into call routing and call management:
- Call priority routing
- Lead qualification before call
- Outcome prediction
- Retry strategy decisions
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class TelephonyDecision:
    """Decision result from TypeSafe telephony integration."""
    decision_id: str
    call_id: str
    decision_type: str  # "route", "qualify", "predict", "retry"
    result: dict[str, Any]
    confidence: float
    latency_ms: float
    timestamp: str
    source: str  # "typesafe" or "heuristic"


class TypeSafeTelephony:
    """
    TypeSafe-powered telephony integration.

    Provides intelligent call routing, lead qualification,
    outcome prediction, and retry decisions using Jev model.
    """

    def __init__(self):
        self.decision_log = Path("data/telephony_decisions.jsonl")
        self.decision_log.parent.mkdir(parents=True, exist_ok=True)

    def route_call(self, call_data: dict[str, Any]) -> TelephonyDecision:
        """
        Route call to optimal agent/channel using TypeSafe.

        Args:
            call_data: Call details including lead info, campaign, context

        Returns:
            TelephonyDecision with routing recommendation
        """
        start_time = time.time()
        decision_id = f"route_{call_data.get('call_id', 'unknown')}_{int(time.time())}"

        state = {
            "call_id": call_data.get("call_id", ""),
            "lead_id": call_data.get("lead_id", ""),
            "lead_score": call_data.get("lead_score", 50),
            "priority": call_data.get("priority", "medium"),
            "campaign_type": call_data.get("campaign_type", "cold_outreach"),
            "lead_industry": call_data.get("lead_industry", "unknown"),
            "lead_company_size": call_data.get("lead_company_size", 0),
            "time_of_day": call_data.get("time_of_day", "business_hours"),
            "day_of_week": call_data.get("day_of_week", "weekday"),
        }

        questions = {
            "route_to": {
                "type": "choice",
                "instructions": "Route this call to the appropriate agent or queue.",
                "criteria": [
                    "sales_team", "outbound_team", "follow_up_team",
                    "priority_queue", "general_queue", "voicemail_only"
                ]
            },
            "call_priority": {
                "type": "choice",
                "instructions": "Determine call priority for scheduling.",
                "criteria": ["immediate", "high", "normal", "low"]
            },
            "best_time": {
                "type": "choice",
                "instructions": "Recommend best time window for this call.",
                "criteria": ["morning", "afternoon", "evening", "any_time"]
            }
        }

        try:
            from app.platform.typesafe_integration import get_typesafe_client
            client = get_typesafe_client()

            if not client.enabled:
                logger.warning("TypeSafe not enabled, using heuristic call routing")
                return self._heuristic_route(call_data, decision_id, start_time)

            response = client.evaluate(
                model="jev-latest",
                state=state,
                questions=questions
            )

            answers = response.get("answers", {})
            latency_ms = (time.time() - start_time) * 1000

            decision = TelephonyDecision(
                decision_id=decision_id,
                call_id=call_data.get("call_id", "unknown"),
                decision_type="route",
                result={
                    "route_to": answers.get("route_to", {}).get("choice", "general_queue"),
                    "call_priority": answers.get("call_priority", {}).get("choice", "normal"),
                    "best_time": answers.get("best_time", {}).get("choice", "any_time"),
                },
                confidence=0.6,
                latency_ms=latency_ms,
                timestamp=datetime.now(timezone.utc).isoformat(),
                source="typesafe"
            )

            self._log_decision(decision)
            return decision

        except Exception as e:
            logger.error(f"TypeSafe call routing failed: {e}")
            return self._heuristic_route(call_data, decision_id, start_time)

    def qualify_before_call(self, lead_data: dict[str, Any]) -> TelephonyDecision:
        """
        Qualify lead before calling using TypeSafe.

        Args:
            lead_data: Lead information

        Returns:
            TelephonyDecision with qualification result
        """
        start_time = time.time()
        decision_id = f"qualify_{lead_data.get('id', 'unknown')}_{int(time.time())}"

        state = {
            "lead_id": lead_data.get("id", ""),
            "company": lead_data.get("company", ""),
            "industry": lead_data.get("industry", ""),
            "company_size": lead_data.get("company_size", 0),
            "budget_signal": lead_data.get("budget_signal", 0),
            "engagement_score": lead_data.get("engagement_score", 0),
            "fit_score": lead_data.get("fit_score", 0),
            "phone_verified": lead_data.get("phone_verified", False),
            "last_contacted": lead_data.get("last_contacted", "never"),
        }

        questions = {
            "call_worthwhile": {
                "type": "choice",
                "instructions": "Is this lead worth calling based on qualification signals?",
                "criteria": ["yes", "no"]
            },
            "call_priority": {
                "type": "choice",
                "instructions": "Rate call priority if proceeding.",
                "criteria": ["critical", "high", "medium", "low"]
            },
            "expected_outcome": {
                "type": "choice",
                "instructions": "Predict most likely call outcome.",
                "criteria": ["interested", "not_interested", "callback", "no_answer", "voicemail"]
            }
        }

        try:
            from app.platform.typesafe_integration import get_typesafe_client
            client = get_typesafe_client()

            if not client.enabled:
                return self._heuristic_qualify(lead_data, decision_id, start_time)

            response = client.evaluate(
                model="jev-latest",
                state=state,
                questions=questions
            )

            answers = response.get("answers", {})
            latency_ms = (time.time() - start_time) * 1000

            decision = TelephonyDecision(
                decision_id=decision_id,
                call_id=lead_data.get("id", "unknown"),
                decision_type="qualify",
                result={
                    "call_worthwhile": answers.get("call_worthwhile", {}).get("choice", "no") == "yes",
                    "call_priority": answers.get("call_priority", {}).get("choice", "medium"),
                    "expected_outcome": answers.get("expected_outcome", {}).get("choice", "no_answer"),
                },
                confidence=0.6,
                latency_ms=latency_ms,
                timestamp=datetime.now(timezone.utc).isoformat(),
                source="typesafe"
            )

            self._log_decision(decision)
            return decision

        except Exception as e:
            logger.error(f"TypeSafe lead qualification failed: {e}")
            return self._heuristic_qualify(lead_data, decision_id, start_time)

    def predict_outcome(self, call_context: dict[str, Any]) -> TelephonyDecision:
        """
        Predict call outcome using TypeSafe.

        Args:
            call_context: Call context including lead data, history, timing

        Returns:
            TelephonyDecision with outcome prediction
        """
        start_time = time.time()
        decision_id = f"predict_{call_context.get('call_id', 'unknown')}_{int(time.time())}"

        state = {
            "call_id": call_context.get("call_id", ""),
            "lead_id": call_context.get("lead_id", ""),
            "lead_history": call_context.get("lead_history", []),
            "previous_outcomes": call_context.get("previous_outcomes", []),
            "call_duration_expected": call_context.get("call_duration_expected", 120),
            "agent_experience": call_context.get("agent_experience", "medium"),
            "time_of_day": call_context.get("time_of_day", "business_hours"),
            "day_of_week": call_context.get("day_of_week", "weekday"),
        }

        questions = {
            "predicted_outcome": {
                "type": "choice",
                "instructions": "Predict the most likely call outcome.",
                "criteria": ["interested", "not_interested", "callback", "no_answer", "voicemail", "busy"]
            },
            "success_probability": {
                "type": "score",
                "instructions": "Rate probability of positive outcome (0-100).",
                "min": 0,
                "max": 100
            },
            "recommended_script": {
                "type": "choice",
                "instructions": "Select optimal call script based on context.",
                "criteria": ["cold_outreach", "warm_followup", "appointment_confirm", "re_engagement"]
            }
        }

        try:
            from app.platform.typesafe_integration import get_typesafe_client
            client = get_typesafe_client()

            if not client.enabled:
                return self._heuristic_predict(call_context, decision_id, start_time)

            response = client.evaluate(
                model="jev-latest",
                state=state,
                questions=questions
            )

            answers = response.get("answers", {})
            latency_ms = (time.time() - start_time) * 1000

            decision = TelephonyDecision(
                decision_id=decision_id,
                call_id=call_context.get("call_id", "unknown"),
                decision_type="predict",
                result={
                    "predicted_outcome": answers.get("predicted_outcome", {}).get("choice", "no_answer"),
                    "success_probability": answers.get("success_probability", {}).get("score", 50),
                    "recommended_script": answers.get("recommended_script", {}).get("choice", "cold_outreach"),
                },
                confidence=answers.get("success_probability", {}).get("confidence", 0.5),
                latency_ms=latency_ms,
                timestamp=datetime.now(timezone.utc).isoformat(),
                source="typesafe"
            )

            self._log_decision(decision)
            return decision

        except Exception as e:
            logger.error(f"TypeSafe outcome prediction failed: {e}")
            return self._heuristic_predict(call_context, decision_id, start_time)

    def decide_retry(self, call_data: dict[str, Any], outcome: str) -> TelephonyDecision:
        """
        Decide whether to retry a call using TypeSafe.

        Args:
            call_data: Original call details
            outcome: Call outcome (no_answer, busy, voicemail, etc.)

        Returns:
            TelephonyDecision with retry recommendation
        """
        start_time = time.time()
        decision_id = f"retry_{call_data.get('call_id', 'unknown')}_{int(time.time())}"

        state = {
            "call_id": call_data.get("call_id", ""),
            "lead_id": call_data.get("lead_id", ""),
            "lead_score": call_data.get("lead_score", 50),
            "outcome": outcome,
            "retry_count": call_data.get("retry_count", 0),
            "max_retries": call_data.get("max_retries", 3),
            "last_attempt": call_data.get("last_attempt", "unknown"),
            "time_since_last": call_data.get("time_since_last", 0),
        }

        questions = {
            "should_retry": {
                "type": "choice",
                "instructions": "Should we retry this call based on lead value and outcome?",
                "criteria": ["yes", "no"]
            },
            "retry_timing": {
                "type": "choice",
                "instructions": "When should the retry be attempted?",
                "criteria": ["immediate", "today", "tomorrow", "next_week", "never"]
            },
            "retry_strategy": {
                "type": "choice",
                "instructions": "What strategy should be used for retry?",
                "criteria": ["same_agent", "different_agent", "different_time", "different_channel"]
            }
        }

        try:
            from app.platform.typesafe_integration import get_typesafe_client
            client = get_typesafe_client()

            if not client.enabled:
                return self._heuristic_retry(call_data, outcome, decision_id, start_time)

            response = client.evaluate(
                model="jev-latest",
                state=state,
                questions=questions
            )

            answers = response.get("answers", {})
            latency_ms = (time.time() - start_time) * 1000

            decision = TelephonyDecision(
                decision_id=decision_id,
                call_id=call_data.get("call_id", "unknown"),
                decision_type="retry",
                result={
                    "should_retry": answers.get("should_retry", {}).get("choice", "no") == "yes",
                    "retry_timing": answers.get("retry_timing", {}).get("choice", "tomorrow"),
                    "retry_strategy": answers.get("retry_strategy", {}).get("choice", "same_agent"),
                },
                confidence=0.6,
                latency_ms=latency_ms,
                timestamp=datetime.now(timezone.utc).isoformat(),
                source="typesafe"
            )

            self._log_decision(decision)
            return decision

        except Exception as e:
            logger.error(f"TypeSafe retry decision failed: {e}")
            return self._heuristic_retry(call_data, outcome, decision_id, start_time)

    def _log_decision(self, decision: TelephonyDecision):
        """Log decision to JSONL file."""
        try:
            with open(self.decision_log, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "decision_id": decision.decision_id,
                    "call_id": decision.call_id,
                    "decision_type": decision.decision_type,
                    "result": decision.result,
                    "confidence": decision.confidence,
                    "latency_ms": decision.latency_ms,
                    "timestamp": decision.timestamp,
                    "source": decision.source,
                }) + "\n")
        except Exception as e:
            logger.warning(f"Failed to log telephony decision: {e}")

    # Heuristic fallbacks

    def _heuristic_route(self, call_data: dict, decision_id: str, start_time: float) -> TelephonyDecision:
        """Fallback heuristic for call routing."""
        priority = call_data.get("priority", "medium")
        lead_score = call_data.get("lead_score", 50)

        if priority == "critical" or lead_score >= 80:
            route, call_prio = "priority_queue", "immediate"
        elif priority == "high" or lead_score >= 60:
            route, call_prio = "sales_team", "high"
        else:
            route, call_prio = "general_queue", "normal"

        return TelephonyDecision(
            decision_id=decision_id,
            call_id=call_data.get("call_id", "unknown"),
            decision_type="route",
            result={"route_to": route, "call_priority": call_prio, "best_time": "any_time"},
            confidence=0.5,
            latency_ms=(time.time() - start_time) * 1000,
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="heuristic"
        )

    def _heuristic_qualify(self, lead_data: dict, decision_id: str, start_time: float) -> TelephonyDecision:
        """Fallback heuristic for lead qualification."""
        fit_score = lead_data.get("fit_score", 50)
        budget = lead_data.get("budget_signal", 50)

        worthwhile = fit_score >= 50 and budget >= 40
        priority = "critical" if fit_score >= 80 else "high" if fit_score >= 60 else "medium"

        return TelephonyDecision(
            decision_id=decision_id,
            call_id=lead_data.get("id", "unknown"),
            decision_type="qualify",
            result={
                "call_worthwhile": worthwhile,
                "call_priority": priority,
                "expected_outcome": "interested" if worthwhile else "no_answer"
            },
            confidence=0.5,
            latency_ms=(time.time() - start_time) * 1000,
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="heuristic"
        )

    def _heuristic_predict(self, call_context: dict, decision_id: str, start_time: float) -> TelephonyDecision:
        """Fallback heuristic for outcome prediction."""
        lead_score = call_context.get("lead_score", 50)

        if lead_score >= 80:
            outcome, prob = "interested", 75
        elif lead_score >= 60:
            outcome, prob = "callback", 60
        elif lead_score >= 40:
            outcome, prob = "voicemail", 40
        else:
            outcome, prob = "no_answer", 25

        return TelephonyDecision(
            decision_id=decision_id,
            call_id=call_context.get("call_id", "unknown"),
            decision_type="predict",
            result={
                "predicted_outcome": outcome,
                "success_probability": prob,
                "recommended_script": "cold_outreach"
            },
            confidence=0.5,
            latency_ms=(time.time() - start_time) * 1000,
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="heuristic"
        )

    def _heuristic_retry(self, call_data: dict, outcome: str, decision_id: str, start_time: float) -> TelephonyDecision:
        """Fallback heuristic for retry decision."""
        retry_count = call_data.get("retry_count", 0)
        lead_score = call_data.get("lead_score", 50)
        max_retries = call_data.get("max_retries", 3)

        should_retry = retry_count < max_retries and lead_score >= 40 and outcome in ["no_answer", "busy", "voicemail"]
        timing = "tomorrow" if should_retry else "never"

        return TelephonyDecision(
            decision_id=decision_id,
            call_id=call_data.get("call_id", "unknown"),
            decision_type="retry",
            result={
                "should_retry": should_retry,
                "retry_timing": timing,
                "retry_strategy": "same_agent"
            },
            confidence=0.5,
            latency_ms=(time.time() - start_time) * 1000,
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="heuristic"
        )


# Singleton instance
_telephony: TypeSafeTelephony | None = None


def get_telephony() -> TypeSafeTelephony:
    """Get or create singleton TypeSafeTelephony."""
    global _telephony
    if _telephony is None:
        _telephony = TypeSafeTelephony()
    return _telephony


def route_call(call_data: dict) -> TelephonyDecision:
    """Quick function to route a call."""
    return get_telephony().route_call(call_data)


def qualify_before_call(lead_data: dict) -> TelephonyDecision:
    """Quick function to qualify lead before call."""
    return get_telephony().qualify_before_call(lead_data)


def predict_outcome(call_context: dict) -> TelephonyDecision:
    """Quick function to predict call outcome."""
    return get_telephony().predict_outcome(call_context)


def decide_retry(call_data: dict, outcome: str) -> TelephonyDecision:
    """Quick function to decide retry."""
    return get_telephony().decide_retry(call_data, outcome)


__all__ = [
    "TypeSafeTelephony",
    "TelephonyDecision",
    "get_telephony",
    "route_call",
    "qualify_before_call",
    "predict_outcome",
    "decide_retry",
]
