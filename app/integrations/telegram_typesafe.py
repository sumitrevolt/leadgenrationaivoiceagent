"""
TypeSafe-Driven Telegram Bot Integration (LeadGen AI)
=====================================================
Uses TypeSafe AI System One models (default: jev-latest) for:
1. Message intent classification
2. Supervisory routing across the 9 Hermes bots
3. Response validation and quality scoring
4. Fail-closed / safe deterministic fallback when TypeSafe is disabled or unavailable
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from app.platform.typesafe_integration import (
    Choice,
    Noul,
    Score,
    TypeSafeClient,
    TypeSafeResponse,
    get_typesafe_client,
)

logger = logging.getLogger(__name__)

# Allowed intents
INTENT_CHOICES = {
    "status_check": "Inquire about system health, orchestrator state, or metrics (/status)",
    "task_query": "Ask about active or pending tasks, task ledger, or assignments (/tasks)",
    "agent_query": "Ask about the 31 specialist agents or their workforce status (/agents)",
    "command": "Execute a control action such as pause, resume, or dispatch (/pause, /resume)",
    "general_question": "Ask a general question about LeadGen AI features or documentation",
    "other": "Unclear, ambiguous, or conversational message",
}

# The 9 canonical Hermes supervisory bots
HERMES_BOT_CHOICES = {
    "board": "Executive Strategy, Metrics & High-level Prioritization",
    "pilot": "Operational Orchestration, Task Dispatch & Workflow Handoff",
    "guardian": "Security, Compliance, Policy & Access Verification",
    "engineering": "Code, Tools & Infrastructure Automation",
    "platform": "SRE, Database, System Health & Reliability",
    "sales": "Revenue Pipeline, Inbound Conversion & Deals",
    "hunter": "Prospecting, Scraping & Outbound Lists",
    "operations": "CRM Delivery, Execution & Automation Loops",
    "success": "Customer Assurance, Retention & Delivery Verification",
}


class TelegramIntentClassifier:
    """Classify Telegram messages using TypeSafe AI System One."""

    def __init__(self, client: TypeSafeClient | None = None):
        self.client = client or get_typesafe_client()

    def classify_intent(self, message_text: str, user_id: str, is_owner: bool = False) -> dict[str, Any]:
        """Classify message intent, actionability, and priority."""
        text = (message_text or "").strip()
        lower = text.lower()

        # Deterministic shortcut for slash commands to ensure zero-latency execution
        if lower.startswith("/status"):
            return {
                "success": True,
                "intent": "status_check",
                "priority": "medium",
                "is_actionable": True,
                "confidence": 1.0,
                "source": "deterministic_command",
            }
        elif lower.startswith("/tasks"):
            return {
                "success": True,
                "intent": "task_query",
                "priority": "medium",
                "is_actionable": True,
                "confidence": 1.0,
                "source": "deterministic_command",
            }
        elif lower.startswith("/agents"):
            return {
                "success": True,
                "intent": "agent_query",
                "priority": "low",
                "is_actionable": False,
                "confidence": 1.0,
                "source": "deterministic_command",
            }
        elif lower.startswith(("/pause", "/resume")):
            return {
                "success": True,
                "intent": "command",
                "priority": "high",
                "is_actionable": True,
                "confidence": 1.0,
                "source": "deterministic_command",
            }

        if not self.client.enabled:
            # Deterministic fallback when TypeSafe API key is absent
            fallback_intent = "general_question" if "?" in text else "other"
            return {
                "success": True,
                "intent": fallback_intent,
                "priority": "medium",
                "is_actionable": bool("urgent" in lower or "fix" in lower or "error" in lower),
                "confidence": 0.6,
                "source": "fallback_offline",
            }

        state = {
            "message": text,
            "user_id": str(user_id),
            "is_owner": is_owner,
        }
        questions = {
            "intent": Choice(
                "What is the primary intent of this Telegram message?",
                INTENT_CHOICES,
            ),
            "is_actionable": Noul(
                "Does this message require an operational action or task execution?"
            ),
            "priority": Score(
                "Rate the operational priority of this message",
                ["low", "medium", "high", "critical"],
            ),
        }

        try:
            resp: TypeSafeResponse = self.client.system_one(state, questions)
            if not resp.success or not resp.has_answer:
                return {
                    "success": False,
                    "intent": "other",
                    "priority": "medium",
                    "is_actionable": False,
                    "confidence": 0.5,
                    "error": resp.error or "no_answer_returned",
                    "source": "typesafe_error",
                }

            answers = resp.answers
            intent_leaf = answers.get("intent", {})
            prio_leaf = answers.get("priority", {})
            action_leaf = answers.get("is_actionable", {})

            intent = intent_leaf.get("choice", "other") if isinstance(intent_leaf, dict) else "other"
            confidence = intent_leaf.get("confidence", 0.75) if isinstance(intent_leaf, dict) else 0.75
            priority = prio_leaf.get("choice", "medium") if isinstance(prio_leaf, dict) else "medium"
            is_actionable = action_leaf.get("noul", 0.0) >= 0.5 if isinstance(action_leaf, dict) else False

            return {
                "success": True,
                "intent": intent,
                "priority": priority,
                "is_actionable": is_actionable,
                "confidence": float(confidence),
                "model": resp.model,
                "latency_sec": resp.latency_sec,
                "source": "typesafe_system_one",
            }
        except Exception as e:
            logger.warning("[telegram_typesafe] Classification failed: %s", e)
            return {
                "success": False,
                "intent": "other",
                "priority": "medium",
                "is_actionable": False,
                "confidence": 0.5,
                "error": str(e),
                "source": "typesafe_exception",
            }


class TelegramBotCoordinator:
    """Coordinate routing across the 9 Hermes supervisory bots."""

    def __init__(self, client: TypeSafeClient | None = None):
        self.client = client or get_typesafe_client()

    def route_to_hermes_bot(
        self,
        message_text: str,
        user_id: str,
        is_owner: bool = False,
    ) -> dict[str, Any]:
        """Route message to one of the 9 Hermes bots."""
        text = (message_text or "").strip()
        lower = text.lower()

        # Deterministic keyword routing shortcuts
        if any(w in lower for w in ("revenue", "money", "sale", "lead", "deal")):
            return {"success": True, "handler": "sales", "confidence": 0.9, "source": "keyword_match"}
        if any(w in lower for w in ("db", "infra", "sre", "server", "vps", "uptime")):
            return {"success": True, "handler": "platform", "confidence": 0.9, "source": "keyword_match"}
        if any(w in lower for w in ("code", "bug", "deploy", "git", "pr")):
            return {"success": True, "handler": "engineering", "confidence": 0.9, "source": "keyword_match"}
        if any(w in lower for w in ("security", "dnd", "trai", "compliance", "policy")):
            return {"success": True, "handler": "guardian", "confidence": 0.9, "source": "keyword_match"}

        if not self.client.enabled:
            return {"success": True, "handler": "pilot", "confidence": 0.6, "source": "fallback_default"}

        state = {
            "message": text,
            "user_id": str(user_id),
            "is_owner": is_owner,
            "available_bots": list(HERMES_BOT_CHOICES.keys()),
        }
        questions = {
            "target_bot": Choice(
                "Which of the 9 Hermes supervisory bots should handle this request?",
                HERMES_BOT_CHOICES,
            ),
            "confidence": Score(
                "Rate confidence in this routing decision",
                ["low", "medium", "high", "very_high"],
            ),
        }

        try:
            resp: TypeSafeResponse = self.client.system_one(state, questions)
            if not resp.success or not resp.has_answer:
                return {"success": False, "handler": "pilot", "confidence": 0.5, "error": resp.error}

            answers = resp.answers
            bot_leaf = answers.get("target_bot", {})
            conf_leaf = answers.get("confidence", {})

            handler = bot_leaf.get("choice", "pilot") if isinstance(bot_leaf, dict) else "pilot"
            conf_val = conf_leaf.get("choice", "medium") if isinstance(conf_leaf, dict) else "medium"
            conf_num = 0.9 if conf_val == "very_high" else 0.75 if conf_val == "high" else 0.5

            return {
                "success": True,
                "handler": handler,
                "confidence": conf_num,
                "model": resp.model,
                "latency_sec": resp.latency_sec,
                "source": "typesafe_system_one",
            }
        except Exception as e:
            logger.warning("[telegram_typesafe] Routing failed: %s", e)
            return {"success": False, "handler": "pilot", "confidence": 0.5, "error": str(e)}


class TelegramResponseValidator:
    """Validate bot responses for quality and appropriateness using TypeSafe."""

    def __init__(self, client: TypeSafeClient | None = None):
        self.client = client or get_typesafe_client()

    def validate_response(
        self,
        response_text: str,
        intent: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Validate response quality and appropriateness."""
        text = (response_text or "").strip()
        if not text:
            return {"success": False, "quality": "poor", "appropriate": False, "complete": False, "error": "empty_text"}

        if not self.client.enabled:
            # Deterministic offline quality check
            is_good = len(text) > 20 and not text.startswith("Error:")
            return {
                "success": True,
                "quality": "good" if is_good else "adequate",
                "appropriate": True,
                "complete": is_good,
                "quality_score": 3.0 if is_good else 2.0,
                "source": "offline_check",
            }

        state = {
            "response": text,
            "intent": intent,
            "context": context or {},
        }
        questions = {
            "quality": Score(
                "Rate the quality and helpfulness of this response",
                ["poor", "adequate", "good", "excellent"],
            ),
            "appropriate": Noul("Is this response appropriate and safe for the user?"),
            "complete": Noul("Does this response fully address the user query?"),
        }

        try:
            resp: TypeSafeResponse = self.client.system_one(state, questions)
            if not resp.success or not resp.has_answer:
                return {
                    "success": False,
                    "quality": "adequate",
                    "appropriate": True,
                    "complete": True,
                    "quality_score": 2.0,
                    "error": resp.error,
                }

            answers = resp.answers
            q_leaf = answers.get("quality", {})
            app_leaf = answers.get("appropriate", {})
            comp_leaf = answers.get("complete", {})

            quality = q_leaf.get("choice", "adequate") if isinstance(q_leaf, dict) else "adequate"
            appropriate = (app_leaf.get("noul", 1.0) >= 0.5) if isinstance(app_leaf, dict) else True
            complete = (comp_leaf.get("noul", 1.0) >= 0.5) if isinstance(comp_leaf, dict) else True

            score_map = {"poor": 1.0, "adequate": 2.0, "good": 3.0, "excellent": 4.0}
            quality_score = score_map.get(quality, 2.0)

            return {
                "success": True,
                "quality": quality,
                "appropriate": appropriate,
                "complete": complete,
                "quality_score": quality_score,
                "model": resp.model,
                "latency_sec": resp.latency_sec,
                "source": "typesafe_system_one",
            }
        except Exception as e:
            logger.warning("[telegram_typesafe] Validation failed: %s", e)
            return {
                "success": False,
                "quality": "adequate",
                "appropriate": True,
                "complete": True,
                "quality_score": 2.0,
                "error": str(e),
            }


# Singletons
_intent_classifier: TelegramIntentClassifier | None = None
_bot_coordinator: TelegramBotCoordinator | None = None
_response_validator: TelegramResponseValidator | None = None


def get_intent_classifier() -> TelegramIntentClassifier:
    global _intent_classifier
    if _intent_classifier is None:
        _intent_classifier = TelegramIntentClassifier()
    return _intent_classifier


def get_bot_coordinator() -> TelegramBotCoordinator:
    global _bot_coordinator
    if _bot_coordinator is None:
        _bot_coordinator = TelegramBotCoordinator()
    return _bot_coordinator


def get_response_validator() -> TelegramResponseValidator:
    global _response_validator
    if _response_validator is None:
        _response_validator = TelegramResponseValidator()
    return _response_validator


__all__ = [
    "TelegramIntentClassifier",
    "TelegramBotCoordinator",
    "TelegramResponseValidator",
    "get_intent_classifier",
    "get_bot_coordinator",
    "get_response_validator",
    "HERMES_BOT_CHOICES",
    "INTENT_CHOICES",
]
