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
  1. env var TYPESAFE_API_KEY (production: /opt/leadgen/.env)
  2. env var TYPEsafe_API_KEY (legacy backward-compat)
  3. "" (empty) -> the integration is INERT, not silently authenticated.
The exposed key is in git history (7317f990) and MUST be revoked/rotated.

Credential state vocabulary (2026-09-18) — used by `credential_state()` below,
`automation_health.wiring_gaps()` and `scripts/typesafe_status.py`:
  PRESENT            key configured in the PROCESS env (this module never reads
                     a .env file — app code has no load_dotenv; dev runs must
                     pass `uvicorn --env-file .env`)
  ABSENT             no key -> every call site silently degrades to its fallback
  INVALID            key present but the API rejected it (HTTP 401/403) — needs
                     a live probe, so only the status script reports it
  ROTATION_REQUIRED  key is one of the already-EXPOSED fingerprints — never arm
"""

import hashlib
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

# TypeSafe API configuration — resolved at construction time, not import time
TYPEsafe_BASE_URL = "https://api.typesafe.ai"
_DEFAULT_MODEL = "jev-latest"


def _get_api_key() -> str:
    """Read API key from canonical env, with legacy fallback."""
    return (os.getenv("TYPESAFE_API_KEY") or os.getenv("TYPEsafe_API_KEY") or "").strip() or ""


def fingerprint(value: str) -> str:
    """sha256[:12] of a credential — safe to print/log. NEVER the credential itself."""
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


# Credentials that are already EXPOSED and must never be re-armed. Hashes only
# (a hash is not a secret — and the plaintext sits in public git history anyway).
COMPROMISED_FINGERPRINTS: dict[str, str] = {
    # getenv fallback default in this file, commit 7317f990 (removed in 979c2229).
    "fe66d7de1807": "committed in 7317f990 (removed 979c2229)",
}


def credential_state() -> dict[str, Any]:
    """Config-only credential state. NO network call, NEVER logs the value.

    `INVALID` is deliberately not detectable here — proving a key was rejected
    needs a live request, which belongs to `scripts/typesafe_status.py --probe`
    (bounded, on demand) and not to a health/brief path that runs per page load.
    """
    key = _get_api_key()
    model = os.getenv("TYPESAFE_MODEL") or _DEFAULT_MODEL
    if not key:
        return {
            "state": "ABSENT",
            "enabled": False,
            "source": "none",
            "fingerprint": "",
            "model": model,
        }
    source = (
        "env:TYPESAFE_API_KEY"
        if (os.getenv("TYPESAFE_API_KEY") or "").strip()
        else "env:TYPEsafe_API_KEY"
    )
    fp = fingerprint(key)
    return {
        "state": "ROTATION_REQUIRED" if fp in COMPROMISED_FINGERPRINTS else "PRESENT",
        "enabled": True,
        "source": source,
        "fingerprint": fp,
        "model": model,
    }


@dataclass
class TypeSafeResponse:
    """Response from TypeSafe System One API"""

    success: bool
    result: dict[str, Any] | None = None
    error: str | None = None
    model: str | None = None
    latency_sec: float = 0.0

    @property
    def value(self) -> Any | None:
        """Get the primary value from first answer.

        Noul answers carry the field `noul` (NOT `probability`/`confidence` —
        see TypeSafe quickstart response contract), so it must be checked
        explicitly with None-guards (a 0.0 noul is falsy but meaningful).
        """
        if self.result and "answers" in self.result:
            answers = self.result["answers"]
            for v in answers.values():
                for key in ("choice", "noul", "probability", "score"):
                    if v.get(key) is not None:
                        return v.get(key)
        return None

    @property
    def confidence(self) -> float:
        """Get confidence/probability from first answer.

        Noul answers report no `confidence` field; the `noul` probability is
        the honest proxy (a 0.99 noul means high certainty in the outcome).
        """
        if self.result and "answers" in self.result:
            answers = self.result["answers"]
            for v in answers.values():
                if v.get("confidence") is not None:
                    return v.get("confidence")
                for key in ("probability", "noul"):
                    if v.get(key) is not None:
                        return v.get(key)
        return 0.5

    @property
    def answers(self) -> dict[str, Any]:
        """Get all answers dict"""
        if self.result:
            return self.result.get("answers", {})
        return {}


class Choice:
    """Choice question primitive for TypeSafe System One

    Official SDK contract:
    {type: "choice", instructions: str, criteria: {...}}
    The `question` argument is mapped to `instructions` in the payload.
    """

    def __init__(self, question: str, criteria: dict[str, str], instructions: str = ""):
        # `question` is the user-facing label; official wire field is `instructions`
        self.question = question
        self.criteria = criteria
        self.instructions = instructions or question

    def to_dict(self, name: str) -> dict[str, Any]:
        return {
            "type": "choice",
            "instructions": self.instructions,
            "criteria": self.criteria,
        }


class Noul:
    """Noul (yes/no) question primitive for TypeSafe System One

    Official SDK contract:
    {type: "noul", instructions: str, optional criteria}
    """

    def __init__(self, question: str, instructions: str = ""):
        self.question = question
        self.instructions = instructions or question

    def to_dict(self, name: str) -> dict[str, Any]:
        return {
            "type": "noul",
            "instructions": self.instructions,
        }


class Score:
    """Score question primitive for TypeSafe System One

    Official SDK contract:
    {type: "score", instructions: str, criteria: [...]}
    Criteria is a LIST (not dict) — e.g., ["low", "medium", "high"]
    """

    def __init__(self, question: str, criteria: list[str], instructions: str = ""):
        self.question = question
        # Accept both list and dict for backward compat, but prefer list
        self.criteria: list[str] = criteria
        self.instructions = instructions or question

    def to_dict(self, name: str) -> dict[str, Any]:
        return {
            "type": "score",
            "instructions": self.instructions,
            "criteria": self.criteria,
        }


class TypeSafeClient:
    """TypeSafe System One API client for AI judgments"""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = (api_key or _get_api_key()).strip() or ""
        self.model = model or os.getenv("TYPESAFE_MODEL") or _DEFAULT_MODEL
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

    def system_one(self, state: dict[str, Any], questions: dict[str, Any]) -> TypeSafeResponse:
        """
        Call the canonical System One endpoint.

        Every invocation carries a traceable record: model, input (state +
        questions), returned answers, HTTP status, latency, and
        success/failure are all present on the returned TypeSafeResponse
        (or in the error).

        Args:
            state: Current context/state dict
            questions: Dict of typed question builders (Choice/Noul/Score)

        Returns:
            TypeSafeResponse with answers
        """
        if not self.enabled:
            return TypeSafeResponse(
                success=False,
                error="INERT: no API key configured",
                model=self.model,
                latency_sec=0.0,
            )

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
                logger.error(
                    f"TypeSafe system_one failed: {response.status_code} {response.text[:200]}"
                )
                return TypeSafeResponse(
                    success=False,
                    error=f"HTTP {response.status_code}: {response.text[:200]}",
                    latency_sec=latency,
                )
        except Exception as e:
            latency = time() - start
            logger.error(f"TypeSafe system_one exception: {e}")
            return TypeSafeResponse(success=False, error=str(e), latency_sec=latency)

    def choice(
        self, question: str, state: dict[str, Any], criteria: dict[str, str]
    ) -> TypeSafeResponse:
        """Compatibility wrapper around system_one for a single Choice question."""
        return self.system_one(state, {"q": Choice(question, criteria)})

    def noul(self, question: str, state: dict[str, Any]) -> TypeSafeResponse:
        """Compatibility wrapper around system_one for a single Noul question."""
        return self.system_one(state, {"q": Noul(question)})

    def score(
        self,
        question: str,
        state: dict[str, Any],
        criteria: list[str] | dict[str, str],
    ) -> TypeSafeResponse:
        """Compatibility wrapper around system_one for a single Score question.

        Official Score criteria is a LIST of level descriptions. A dict is
        accepted for backward compat (values used, in insertion order).
        """
        if isinstance(criteria, dict):
            criteria = list(criteria.values())
        return self.system_one(state, {"q": Score(question, criteria)})

    def is_initialized(self) -> bool:
        return self._initialized


# Global client instance
_typesafe_client: TypeSafeClient | None = None


def get_typesafe_client() -> TypeSafeClient:
    global _typesafe_client
    if _typesafe_client is None:
        _typesafe_client = TypeSafeClient()
        _typesafe_client.initialize()
    return _typesafe_client


def typesafe_choice(
    question: str, state: dict[str, Any], criteria: dict[str, str]
) -> TypeSafeResponse:
    return get_typesafe_client().choice(question, state, criteria)


def typesafe_noul(question: str, state: dict[str, Any]) -> TypeSafeResponse:
    return get_typesafe_client().noul(question, state)


def typesafe_score(
    question: str, state: dict[str, Any], criteria: list[str] | dict[str, str]
) -> TypeSafeResponse:
    return get_typesafe_client().score(question, state, criteria)


def typesafe_system_one(state: dict[str, Any], questions: dict[str, Any]) -> TypeSafeResponse:
    """Convenience function for System One calls."""
    return get_typesafe_client().system_one(state, questions)
