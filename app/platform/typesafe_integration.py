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
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, TypedDict, cast

import requests

logger = logging.getLogger(__name__)

# TypeSafe API configuration — resolved at construction time, not import time
TYPEsafe_BASE_URL = "https://api.typesafe.ai"
_DEFAULT_MODEL = "jev-latest"

# --- Typed wire contract ---------------------------------------------------- #
# These describe the exact JSON we SEND and the envelope we EXPECT BACK. They are
# the single source of truth for the System One request/response shape, so a
# payload change is a type error at the call site instead of a 400 at runtime.
#
# NOTE: the response body is intentionally modelled loosely (`total=False` plus
# `Any` leaves) because the API's `answers` leaves legitimately vary by primitive
# (choice -> `choice`, noul -> `noul`, score -> `score`/`confidence`). Strictness
# is applied where it is enforceable (the request), not where it would be a lie.

CredentialStateName = Literal["PRESENT", "ABSENT", "INVALID", "ROTATION_REQUIRED"]


class CredentialState(TypedDict, total=False):
    """Return shape of `credential_state()`. Never contains the key itself."""

    state: CredentialStateName
    enabled: bool
    source: str
    fingerprint: str
    model: str
    pool_size: int
    pool_fingerprints: list[str]


class QuestionPayload(TypedDict, total=False):
    """One serialized question as sent on the wire."""

    type: str
    instructions: str
    criteria: Any


class SystemOneRequest(TypedDict):
    """The exact POST body for /v1/systemone."""

    model: str
    state: dict[str, Any]
    questions: dict[str, QuestionPayload]


class SystemOneAnswer(TypedDict, total=False):
    """A single answer leaf. `total=False` — only one primitive field is present."""

    type: str
    choice: str
    noul: float
    probability: float
    score: float
    confidence: float


class SystemOneResponseBody(TypedDict, total=False):
    """The response envelope. `model`/`answers` are the parts we rely on."""

    model: str
    answers: dict[str, Any]
    usage: dict[str, Any]


# Timeouts are split so a slow/hanging READ cannot consume the connect budget.
# (10s connect, 30s read) — matches the previous flat `timeout=30` upper bound.
_CONNECT_TIMEOUT_SEC = 10.0
_READ_TIMEOUT_SEC = 30.0

# Bounded retry for TRANSIENT provider failures only. TypeSafe is a paid,
# rate-limited API, so a 429/5xx is worth one or two retries — but never an
# unbounded loop, and never on 4xx client errors (retrying those just burns quota).
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3
_MAX_RETRY_SLEEP_SEC = 4.0

# Pool state for multi-key rotation and rate-limit cooldown
_POOL_LOCK = threading.Lock()
_KEY_IDX = 0
_KEY_COOLDOWNS: dict[str, float] = {}  # sha256_fp -> epoch_sec
_RUNTIME_KEYS_FILE = os.path.join("data", "typesafe_keys.json")


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


def _split_keys(raw: str) -> list[str]:
    return [k.strip().lstrip("\ufeff") for k in re.split(r"[,\s\n]+", raw or "") if k.strip().lstrip("\ufeff")]


def _load_runtime_keys() -> list[str]:
    """Admin-set runtime store (data/typesafe_keys.json). [] if absent/unreadable."""
    try:
        if os.path.exists(_RUNTIME_KEYS_FILE):
            with open(_RUNTIME_KEYS_FILE, encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, dict) and isinstance(d.get("keys"), list):
                    return [str(k).strip() for k in d["keys"] if str(k).strip()]
                elif isinstance(d, list):
                    return [str(k).strip() for k in d if str(k).strip()]
    except Exception as e:
        logger.debug("[typesafe] Failed to read runtime keys: %s", e)
    return []


def _load_all_keys() -> list[str]:
    """Collect TypeSafe keys from multiple canonical sources, deduped + ordered.
    Sources checked:
      1. TYPESAFE_API_KEYS (comma/space/newline separated)
      2. Individual numbered keys: TYPESAFE_API_KEY_1 .. TYPESAFE_API_KEY_4
      3. TYPESAFE_API_KEY (canonical single/comma-separated)
      4. TYPEsafe_API_KEY (legacy)
      5. data/typesafe_keys.json (admin runtime store)
      6. .env.production.local (local developer fallback)
    """
    raw_keys: list[str] = []

    # 1. Multi-key env var
    multi = os.getenv("TYPESAFE_API_KEYS", "")
    if multi:
        raw_keys.extend(_split_keys(multi))

    # 2. Numbered keys (e.g. TYPESAFE_API_KEY_1 through TYPESAFE_API_KEY_4)
    for i in range(1, 5):
        numbered = os.getenv(f"TYPESAFE_API_KEY_{i}", "")
        if numbered:
            raw_keys.extend(_split_keys(numbered))

    # 3. Canonical single/comma-separated key
    single = os.getenv("TYPESAFE_API_KEY", "")
    if single:
        raw_keys.extend(_split_keys(single))

    # 4. Legacy env key
    legacy = os.getenv("TYPEsafe_API_KEY", "")
    if legacy:
        raw_keys.extend(_split_keys(legacy))

    # 5. Runtime keys file
    raw_keys.extend(_load_runtime_keys())

    # 6. Encrypted KeyManager vault slots (TS_A..TS_D)
    try:
        from app.platform.key_manager import get_key_manager

        km = get_key_manager()
        raw_keys.extend(km.get_all_typesafe_slot_keys())
    except Exception as _e:
        logger.debug("[typesafe] Failed to load keys from key_manager vault: %s", _e)

    # Deduplicate while preserving order & filter compromised fingerprints
    seen: set[str] = set()
    cleaned: list[str] = []
    for k in raw_keys:
        clean = k.strip().lstrip("\ufeff")
        if clean and clean not in seen:
            seen.add(clean)
            fp = fingerprint(clean)
            if fp not in COMPROMISED_FINGERPRINTS:
                cleaned.append(clean)

    return cleaned


def _get_api_key() -> str:
    """Read API key from pool, with canonical env fallback for exposed tripwires."""
    keys = _load_all_keys()
    if not keys:
        return (os.getenv("TYPESAFE_API_KEY") or os.getenv("TYPEsafe_API_KEY") or "").strip().lstrip("\ufeff")
    return get_active_api_key()


def get_active_api_key() -> str:
    """Get the currently active API key from the rotation pool.
    Skips keys currently in cooldown (e.g. following a 429) if healthy keys exist.
    """
    global _KEY_IDX
    keys = _load_all_keys()
    if not keys:
        return (os.getenv("TYPESAFE_API_KEY") or os.getenv("TYPEsafe_API_KEY") or "").strip().lstrip("\ufeff")

    with _POOL_LOCK:
        now = time.time()
        for offset in range(len(keys)):
            candidate_idx = (_KEY_IDX + offset) % len(keys)
            k = keys[candidate_idx]
            fp = fingerprint(k)
            cooldown_until = _KEY_COOLDOWNS.get(fp, 0.0)
            if now >= cooldown_until:
                _KEY_IDX = candidate_idx
                return k

        # If all keys are in cooldown, return the one that expires earliest
        best_k = min(keys, key=lambda k: _KEY_COOLDOWNS.get(fingerprint(k), 0.0))
        return best_k


def advance_key(failed_key: str | None = None, cooldown_sec: float = 60.0) -> str:
    """Rotate pool index to next key, placing failed_key in cooldown."""
    global _KEY_IDX
    keys = _load_all_keys()
    if not keys:
        return ""

    with _POOL_LOCK:
        if failed_key:
            fp = fingerprint(failed_key)
            _KEY_COOLDOWNS[fp] = time.time() + cooldown_sec
            logger.info("[typesafe_pool] Key %s entered cooldown for %.1fs", fp, cooldown_sec)
        _KEY_IDX = (_KEY_IDX + 1) % len(keys)
        return keys[_KEY_IDX]


def record_key_success(key: str) -> None:
    """Clear cooldown on successful API response."""
    fp = fingerprint(key)
    if fp in _KEY_COOLDOWNS:
        _KEY_COOLDOWNS.pop(fp, None)


def get_typesafe_pool_status() -> dict[str, Any]:
    """Safe pool status for diagnostics and monitoring (fingerprints only)."""
    keys = _load_all_keys()
    now = time.time()
    active_healthy = [k for k in keys if now >= _KEY_COOLDOWNS.get(fingerprint(k), 0.0)]
    return {
        "total_keys": len(keys),
        "healthy_keys": len(active_healthy),
        "current_index": _KEY_IDX if keys else 0,
        "fingerprints": [fingerprint(k) for k in keys],
        "cooldowns": {
            fp: round(exp - now, 1)
            for fp, exp in _KEY_COOLDOWNS.items()
            if exp > now
        },
    }


def credential_state() -> CredentialState:
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
        else ("env:TYPESAFE_API_KEYS" if (os.getenv("TYPESAFE_API_KEYS") or "").strip() else "env:TYPEsafe_API_KEY")
    )
    fp = fingerprint(key)
    state: CredentialStateName = (
        "ROTATION_REQUIRED" if fp in COMPROMISED_FINGERPRINTS else "PRESENT"
    )
    all_keys = _load_all_keys()
    return {
        "state": state,
        "enabled": True,
        "source": source,
        "fingerprint": fp,
        "model": model,
        "pool_size": len(all_keys),
        "pool_fingerprints": [fingerprint(k) for k in all_keys],
    }


def _as_float(value: Any) -> float | None:
    """Best-effort numeric coercion; None when the value is not numeric.

    Explicit isinstance narrowing rather than `float(v)` inside a try/except:
    `v.get(...)` is `Any | None`, so a bare `float(...)` is both a mypy error
    (arg-type) and a latent TypeError if the guard is ever refactored away.
    `bool` is excluded on purpose — a boolean answer is not a confidence score.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


@dataclass
class TypeSafeResponse:
    """Response from TypeSafe System One API"""

    success: bool
    result: dict[str, Any] | None = None
    error: str | None = None
    model: str | None = None
    latency_sec: float = 0.0
    attempts: int = 1

    def _answer_items(self) -> list[Any]:
        """Normalize `answers` (object | array | scalar) into a list of leaves.

        The documented shape is an object keyed by question id, but array-shaped
        responses have been observed in the wild, so both are accepted. Kept in
        ONE place so `value`/`confidence`/`answers` cannot drift apart.
        """
        if not self.result:
            return []
        answers = self.result.get("answers")
        if isinstance(answers, dict):
            return list(answers.values())
        if isinstance(answers, list):
            return list(answers)
        return []

    @property
    def has_answer(self) -> bool:
        """True when the API returned at least one usable answer leaf.

        ADDITIVE to `confidence`, which must keep returning its 0.5 fallback for
        backward compatibility. Without this flag a caller cannot tell "the model
        said 50%" apart from "the model said nothing" — and for a paid decision
        engine those are very different, so the distinction is explicit here
        rather than inferred from a magic number.
        """
        return bool(self._answer_items())

    @staticmethod
    def _clamp_01(v: Any) -> Any:
        """Clamp numeric TypeSafe answers to [0, 1].

        The wire contract states scores/probabilities are 0.0-1.0, but the API has
        returned values slightly above 1.0 (e.g. 1.02) in production. Clamp rather
        than reject — a 1.02 score is a strong positive signal, not an error.
        """
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return max(0.0, min(1.0, float(v)))
        return v

    @property
    def value(self) -> Any | None:
        """Get the primary value from first answer.

        Noul answers carry the field `noul` (NOT `probability`/`confidence` —
        see TypeSafe quickstart response contract), so it must be checked
        explicitly with None-guards (a 0.0 noul is falsy but meaningful).
        """
        for v in self._answer_items():
            if isinstance(v, dict):
                for key in ("choice", "noul", "probability", "score"):
                    if v.get(key) is not None:
                        return self._clamp_01(v.get(key))
            elif isinstance(v, (str, int, float, bool)):
                return v
        return None

    @property
    def score(self) -> float | None:
        """Get the clamped score (0.0-1.0) from first Score answer.

        The wire contract states scores are 0.0-1.0, but the API has returned
        values above 1.0 (e.g. 1.02, 2.4) in production. This property clamps
        to [0, 1] for safe downstream consumption.
        """
        for v in self._answer_items():
            if isinstance(v, dict):
                raw = v.get("score")
                if raw is not None:
                    return self._clamp_01(_as_float(raw))
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                return self._clamp_01(float(v))
        return None

    @property
    def confidence(self) -> float:
        """Get confidence/probability from first answer.

        Noul answers report no `confidence` field; the `noul` probability is
        the honest proxy (a 0.99 noul means high certainty in the outcome).
        Returns 0.5 when there is no usable answer — callers that need to tell
        that case apart from a genuine 50% should read `has_answer` first.
        """
        for v in self._answer_items():
            if isinstance(v, dict):
                for key in ("confidence", "probability", "noul"):
                    if v.get(key) is None:
                        continue
                    coerced = _as_float(v.get(key))
                    if coerced is not None:
                        return self._clamp_01(coerced)
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                return self._clamp_01(float(v))
        return 0.5

    @property
    def answers(self) -> dict[str, Any]:
        """Get all answers as a dict. Array-shaped payloads are keyed `ans_<i>`."""
        if self.result:
            raw = self.result.get("answers", {})
            if isinstance(raw, dict):
                return raw
            if isinstance(raw, list):
                return {f"ans_{i}": v for i, v in enumerate(raw)}
        return {}


class Choice:
    """Choice question primitive for TypeSafe System One

    Official SDK contract:
    {type: "choice", instructions: str, criteria: {...}}
    The `question` argument is mapped to `instructions` in the payload.
    Supports both dict and list (auto-normalized to object mapping).
    """

    def __init__(
        self,
        question: str,
        criteria: dict[str, str] | list[str] | tuple[str, ...],
        instructions: str = "",
    ):
        self.question = question
        if isinstance(criteria, (list, tuple)):
            # Convert Array ["opt1", "opt2"] -> {"opt1": "opt1", "opt2": "opt2"}
            self.criteria = {str(item): str(item) for item in criteria}
        elif isinstance(criteria, dict):
            self.criteria = {str(k): str(v) for k, v in criteria.items()}
        else:
            self.criteria = {"default": str(criteria)}
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
    Criteria is a LIST (not dict) — e.g., ["low", "medium", "high"].
    Supports both list and dict (auto-normalized to list).
    """

    def __init__(
        self,
        question: str,
        criteria: list[str] | dict[str, str] | tuple[str, ...],
        instructions: str = "",
    ):
        self.question = question
        if isinstance(criteria, dict):
            self.criteria = [str(v) for v in criteria.values()]
        elif isinstance(criteria, (list, tuple)):
            self.criteria = [str(item) for item in criteria]
        else:
            self.criteria = [str(criteria)]
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
        # None means auto-discover; an explicit empty string means deliberately
        # inert (critical for fail-closed callers and hermetic tests).
        resolved_key = _get_api_key() if api_key is None else api_key
        self.api_key = resolved_key.strip() or ""
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

    @staticmethod
    def _serialize_question(name: str, q: Any) -> QuestionPayload | None:
        """Serialize one question builder to its wire shape, or None if invalid.

        Returning None (rather than dropping the question) is what lets
        `system_one` fail loudly. A wire-shaped dict is passed through so
        callers that already build payloads by hand keep working.
        """
        if isinstance(q, (Choice, Noul, Score)):
            return cast(QuestionPayload, q.to_dict(name))
        if isinstance(q, dict) and isinstance(q.get("type"), str):
            return cast(QuestionPayload, q)
        return None

    def system_one(
        self,
        state: dict[str, Any],
        questions: Mapping[str, Choice | Noul | Score | QuestionPayload],
        *,
        connect_timeout_sec: float | None = None,
        read_timeout_sec: float | None = None,
        max_attempts: int | None = None,
    ) -> TypeSafeResponse:
        """
        Call the canonical System One endpoint.

        Every invocation carries a traceable record: model, input (state +
        questions), returned answers, HTTP status, latency, retry count and
        success/failure are all present on the returned TypeSafeResponse.

        Args:
            state: Current context/state dict
            questions: Mapping of name -> Choice/Noul/Score builder. A
                wire-shaped dict (`{"type": ...}`) is accepted for backward
                compatibility.
            connect_timeout_sec/read_timeout_sec/max_attempts: Optional tighter
                bounds for latency-sensitive call sites; defaults preserve the
                canonical retry policy and values are capped at its max attempts.

        Returns:
            TypeSafeResponse. `error` carries a stable prefix so callers can
            branch without string-sniffing prose: INERT, INVALID_QUESTION_TYPE,
            TIMEOUT, NETWORK, INVALID_JSON, HTTP_<status>, UNEXPECTED.
        """
        if not self.enabled:
            return TypeSafeResponse(
                success=False,
                error="INERT: no API key configured",
                model=self.model,
                latency_sec=0.0,
            )

        # An unrecognised question type is a FAILURE, not a skip. Silently
        # dropping it used to return a "successful" response that was missing an
        # answer the caller believed it had asked for — the exact silent
        # degradation that makes an automation look healthy while doing nothing.
        questions_payload: dict[str, QuestionPayload] = {}
        for name, q in questions.items():
            serialized = self._serialize_question(name, q)
            if serialized is None:
                return TypeSafeResponse(
                    success=False,
                    error=(
                        f"INVALID_QUESTION_TYPE: {name!r} is {type(q).__name__}; expected "
                        "Choice, Noul, Score or a wire-shaped dict"
                    ),
                    model=self.model,
                    latency_sec=0.0,
                )
            questions_payload[name] = serialized

        payload: SystemOneRequest = {
            "model": self.model,
            "state": state,
            "questions": questions_payload,
        }

        connect_timeout = (
            float(connect_timeout_sec)
            if connect_timeout_sec is not None and float(connect_timeout_sec) > 0
            else _CONNECT_TIMEOUT_SEC
        )
        read_timeout = (
            float(read_timeout_sec)
            if read_timeout_sec is not None and float(read_timeout_sec) > 0
            else _READ_TIMEOUT_SEC
        )
        attempt_budget = max(1, min(int(max_attempts or _MAX_ATTEMPTS), _MAX_ATTEMPTS))
        url = f"{self.base_url}/v1/systemone"
        start = time.time()
        attempts = 0
        last_error = "UNEXPECTED: no attempt made"

        while attempts < attempt_budget:
            attempts += 1
            current_key = self.api_key or get_active_api_key()
            headers = {
                "Authorization": f"Bearer {current_key}",
                "Content-Type": "application/json",
            }
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=(connect_timeout, read_timeout),
                )
            except requests.Timeout as exc:
                # Connect/read timeout is transient — worth the retry budget and advancing key.
                last_error = f"TIMEOUT: {exc}"
                advance_key(current_key, cooldown_sec=10.0)
            except requests.RequestException as exc:
                last_error = f"NETWORK: {exc}"
                advance_key(current_key, cooldown_sec=10.0)
            except Exception as exc:  # noqa: BLE001 - contract: never raise to caller
                # Anything else is a BUG, not a provider condition. Log with a
                # traceback (logger.exception) so it is visible, and still return
                # a typed failure so callers keep their never-raises contract.
                logger.exception("TypeSafe system_one unexpected error")
                return TypeSafeResponse(
                    success=False,
                    error=f"UNEXPECTED: {type(exc).__name__}: {exc}",
                    model=self.model,
                    latency_sec=time.time() - start,
                    attempts=attempts,
                )
            else:
                status = response.status_code
                if status == 200:
                    record_key_success(current_key)
                    latency = time.time() - start
                    try:
                        data = response.json()
                    except ValueError as exc:
                        logger.error(f"TypeSafe system_one returned a non-JSON body: {exc}")
                        return TypeSafeResponse(
                            success=False,
                            error=f"INVALID_JSON: {exc}",
                            model=self.model,
                            latency_sec=latency,
                            attempts=attempts,
                        )
                    logger.info(
                        f"TypeSafe system_one success in {latency:.2f}s (attempt {attempts})"
                    )
                    return TypeSafeResponse(
                        success=True,
                        result=data,
                        model=data.get("model") or self.model,
                        latency_sec=latency,
                        attempts=attempts,
                    )

                last_error = f"HTTP {status}: {(response.text or '')[:200]}"
                if status not in _RETRY_STATUS:
                    # 4xx (bad key / bad payload) is NOT transient. Retrying only
                    # burns paid quota and delays the real error, so fail fast.
                    logger.error(f"TypeSafe system_one failed: {last_error}")
                    return TypeSafeResponse(
                        success=False,
                        error=last_error,
                        model=self.model,
                        latency_sec=time.time() - start,
                        attempts=attempts,
                    )
                # Rotate key on 429 / 5xx error
                cooldown = 60.0 if status == 429 else 15.0
                advance_key(current_key, cooldown_sec=cooldown)
                logger.warning(
                    f"TypeSafe system_one transient {last_error} (attempt {attempts}/{attempt_budget}) -> rotated key"
                )

            if attempts < attempt_budget:
                time.sleep(min(2.0 ** (attempts - 1), _MAX_RETRY_SLEEP_SEC))

        logger.error(f"TypeSafe system_one exhausted {attempts} attempt(s): {last_error}")
        return TypeSafeResponse(
            success=False,
            error=last_error,
            model=self.model,
            latency_sec=time.time() - start,
            attempts=attempts,
        )

    def choice(
        self,
        question: str,
        state: dict[str, Any],
        criteria: dict[str, str] | list[str] | tuple[str, ...],
    ) -> TypeSafeResponse:
        """Compatibility wrapper around system_one for a single Choice question.
        Supports both dict and list/tuple criteria (auto-coerced).
        """
        return self.system_one(state, {"q": Choice(question, criteria)})

    def noul(self, question: str, state: dict[str, Any]) -> TypeSafeResponse:
        """Compatibility wrapper around system_one for a single Noul question."""
        return self.system_one(state, {"q": Noul(question)})

    def score(
        self,
        question: str,
        state: dict[str, Any],
        criteria: list[str] | dict[str, str] | tuple[str, ...],
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
    question: str,
    state: dict[str, Any],
    criteria: dict[str, str] | list[str] | tuple[str, ...],
) -> TypeSafeResponse:
    return get_typesafe_client().choice(question, state, criteria)


def typesafe_noul(question: str, state: dict[str, Any]) -> TypeSafeResponse:
    return get_typesafe_client().noul(question, state)


def typesafe_score(
    question: str, state: dict[str, Any], criteria: list[str] | dict[str, str]
) -> TypeSafeResponse:
    return get_typesafe_client().score(question, state, criteria)


def typesafe_system_one(
    state: dict[str, Any],
    questions: Mapping[str, Choice | Noul | Score | QuestionPayload],
) -> TypeSafeResponse:
    """Convenience function for System One calls."""
    return get_typesafe_client().system_one(state, questions)
