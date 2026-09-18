"""
TypeSafe Integration Module — System One API Contract (2026-09-18)

Canonical contract:
- Base URL: https://api.typesafe.ai (NOT /v1)
- Endpoint: POST /v1/systemone
- Default model: jev-latest (configurable via TYPESAFE_MODEL env var)
- Payload: {model, state, questions}
- Response: {model, answers, usage}

Legacy endpoints (/choice, /noul, /score, /health) are obsolete.
This module implements only the System One endpoint.

Security (2026-09-17): A live ~100-char API key was hardcoded here as the
`os.getenv(...)` FALLBACK DEFAULT (introduced in 7317f990). That has been
REMOVED. Read order:
  1. env var TYPEsafe_API_KEY (production: /opt/leadgen/.env)
  2. "" (empty) -> the integration is INERT, not silently authenticated.
The exposed key is in git history (7317f990) and MUST be revoked/rotated.
"""
import os
import logging
from typing import Any, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# TypeSafe API configuration
TYPEsafe_API_KEY = os.getenv("TYPEsafe_API_KEY", "").strip() or ""
TYPEsafe_BASE_URL = "https://api.typesafe.ai"
TYPEsafe_MODEL = os.getenv("TYPESAFE_MODEL", "jev-latest")


@dataclass
class TypeSafeResponse:
    """Response from TypeSafe System One API"""
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    model: Optional[str] = None
    latency_sec: float = 0.0

    @property
    def value(self) -> Optional[Any]:
        """Get the primary value from first answer"""
        if self.result and "answers" in self.result:
            answers = self.result["answers"]
            for v in answers.values():
                return v.get("choice") or v.get("probability") or v.get("score")
        return None

    @property
    def confidence(self) -> float:
        """Get confidence/probability from first answer"""
        if self.result and "answers" in self.result:
            answers = self.result["answers"]
            for v in answers.values():
                return v.get("confidence", v.get("probability", 0.5))
        return 0.5

    @property
    def answers(self) -> Dict[str, Any]:
        """Get all answers dict"""
        if self.result:
            return self.result.get("answers", {})
        return {}


class Choice:
    """Choice question primitive for TypeSafe System One"""
    def __init__(self, question: str, criteria: Dict[str, str], instructions: str = ""):
        self.question = question
        self.criteria = criteria
        self.instructions = instructions

    def to_dict(self, name: str) -> Dict[str, Any]:
        return {
            "type": "choice",
            "question": self.question,
            "criteria": self.criteria,
            "instructions": self.instructions,
        }


class Noul:
    """Noul (yes/no) question primitive for TypeSafe System One"""
    def __init__(self, question: str, instructions: str = ""):
        self.question = question
        self.instructions = instructions

    def to_dict(self, name: str) -> Dict[str, Any]:
        return {
            "type": "noul",
            "question": self.question,
            "instructions": self.instructions,
        }


class Score:
    """Score question primitive for TypeSafe System One"""
    def __init__(self, question: str, criteria: Dict[str, str], instructions: str = ""):
        self.question = question
        self.criteria = criteria
        self.instructions = instructions

    def to_dict(self, name: str) -> Dict[str, Any]:
        return {
            "type": "score",
            "question": self.question,
            "criteria": self.criteria,
            "instructions": self.instructions,
        }


class TypeSafeClient:
    """TypeSafe System One API client for AI judgments"""

    def __init__(self, api_key: str = TYPEsafe_API_KEY, model: str = TYPEsafe_MODEL):
        self.api_key = (api_key or "").strip()
        self.model = model
        self.base_url = TYPEsafe_BASE_URL
        self._initialized = False
        self.enabled = bool(self.api_key)

    def initialize(self) -> TypeSafeResponse:
        """Initialize — fail-closed if no key."""
        if not self.enabled:
            logger.debug("TypeSafe INERT: no API key configured")
            return TypeSafeResponse(success=False, error="INERT: no API key configured")
        # No separate /health endpoint — first real call proves connectivity.
        self._initialized = True
        return TypeSafeResponse(success=True)

    def system_one(self, state: Dict[str, Any], questions: Dict[str, Any]) -> TypeSafeResponse:
        """
        Call the canonical System One endpoint.

        Args:
            state: Current context/state dict
            questions: Dict of typed question builders (Choice/Noul/Score)

        Returns:
            TypeSafeResponse with answers
        """
        if not self.enabled:
            return TypeSafeResponse(success=False, error="INERT: no API key configured")

        import requests
        from time import time

        # Build questions payload
        questions_payload = {}
        for name, q in questions.items():
            if isinstance(q, Choice):
                questions_payload[name] = q.to_dict(name)
            elif isinstance(q, Noul):
                questions_payload[name] = q.to_dict(name)
            elif isinstance(q, Score):
                questions_payload[name] = q.to_dict(name)
            else:
                logger.warning(f"TypeSafe: unknown question type for {name}, skipping")

        payload = {
            "model": self.model,
            "state": state,
            "questions": questions_payload,
        }

        url = f"{self.base_url}/v1/systemone"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        start = time()
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            latency = time() - start

            if response.status_code == 200:
                data = response.json()
                logger.info(f"TypeSafe system_one success in {latency:.2f}s")
                return TypeSafeResponse(
                    success=True,
                    result=data,
                    model=data.get("model"),
                    latency_sec=latency,
                )
            else:
                logger.error(f"TypeSafe system_one failed: {response.status_code} {response.text[:200]}")
                return TypeSafeResponse(
                    success=False,
                    error=f"HTTP {response.status_code}: {response.text[:200]}",
                    latency_sec=latency,
                )
        except Exception as e:
            latency = time() - start
            logger.error(f"TypeSafe system_one exception: {e}")
            return TypeSafeResponse(success=False, error=str(e), latency_sec=latency)

    def choice(self, question: str, state: Dict[str, Any], criteria: Dict[str, str]) -> TypeSafeResponse:
        """Compatibility wrapper around system_one for a single Choice question."""
        resp = self.system_one(state, {"q": Choice(question, criteria)})
        if resp.success and resp.answers:
            ans = resp.answers.get("q", {})
            return TypeSafeResponse(
                success=True,
                result={"choice": ans.get("choice"), "confidence": ans.get("confidence")},
                model=resp.model,
            )
        return resp

    def noul(self, question: str, state: Dict[str, Any]) -> TypeSafeResponse:
        """Compatibility wrapper around system_one for a single Noul question."""
        resp = self.system_one(state, {"q": Noul(question)})
        if resp.success and resp.answers:
            ans = resp.answers.get("q", {})
            return TypeSafeResponse(
                success=True,
                result={"probability": ans.get("probability")},
                model=resp.model,
            )
        return resp

    def score(self, question: str, state: Dict[str, Any], criteria: Dict[str, str]) -> TypeSafeResponse:
        """Compatibility wrapper around system_one for a single Score question."""
        resp = self.system_one(state, {"q": Score(question, criteria)})
        if resp.success and resp.answers:
            ans = resp.answers.get("q", {})
            return TypeSafeResponse(
                success=True,
                result={"score": ans.get("score")},
                model=resp.model,
            )
        return resp

    def is_initialized(self) -> bool:
        return self._initialized


# Global client instance
_typesafe_client: Optional[TypeSafeClient] = None


def get_typesafe_client() -> TypeSafeClient:
    global _typesafe_client
    if _typesafe_client is None:
        _typesafe_client = TypeSafeClient()
        _typesafe_client.initialize()
    return _typesafe_client


def typesafe_choice(question: str, state: Dict[str, Any], criteria: Dict[str, str]) -> TypeSafeResponse:
    return get_typesafe_client().choice(question, state, criteria)


def typesafe_noul(question: str, state: Dict[str, Any]) -> TypeSafeResponse:
    return get_typesafe_client().noul(question, state)


def typesafe_score(question: str, state: Dict[str, Any], criteria: Dict[str, str]) -> TypeSafeResponse:
    return get_typesafe_client().score(question, state, criteria)


def typesafe_system_one(state: Dict[str, Any], questions: Dict[str, Any]) -> TypeSafeResponse:
    """Convenience function for System One calls."""
    return get_typesafe_client().system_one(state, questions)
