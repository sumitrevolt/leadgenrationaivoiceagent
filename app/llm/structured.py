"""Structured, validated LLM outputs via **Instructor** over the free providers.

The marketing/automation code asks the LLM for JSON and then parses it by hand —
which breaks when a free model adds prose or drops a field. Instructor pins the
output to a Pydantic model and **auto-retries** until it validates, so callers get a
typed object instead of fragile text. Works over our free OpenAI-compatible providers
(Cerebras → Groq) via JSON mode.

No env flag — it's a utility: if `instructor`/`openai` or a provider key is missing,
``extract`` returns ``None`` and the caller keeps its existing template fallback.
Never raises.

Use:
  from pydantic import BaseModel
  from app.llm.structured import extract
  class Post(BaseModel):
      caption: str
      hashtags: list[str]
  post = extract(Post, system="You are a marketing writer.", user="Diwali offer post for a salon")
  if post is None:   # deps/key missing -> fall back to existing template path
      ...
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Type, TypeVar

logger = logging.getLogger(__name__)

# LLM observability (G1) — optional, NEVER breaks this path if module absent.
try:
    from app.observability_llm import llm_span as _llm_span
except Exception:  # pragma: no cover
    from contextlib import contextmanager as _contextmanager

    @_contextmanager
    def _llm_span(*_a, **_k):
        class _NoopSpan:
            def record(self, *_a, **_k):
                pass

        yield _NoopSpan()


T = TypeVar("T")


def _provider() -> tuple | None:
    cb = os.getenv("CEREBRAS_API_KEY")
    if cb:
        return "https://api.cerebras.ai/v1", cb, os.getenv("DEFAULT_LLM", "gpt-oss-120b")
    gq = os.getenv("GROQ_API_KEY")
    if gq:
        # Groq llama-3.3-70b-versatile decommissions 2026-08-16 → gpt-oss-120b.
        return (
            "https://api.groq.com/openai/v1",
            gq,
            os.getenv("STRUCTURED_GROQ_MODEL", "openai/gpt-oss-120b"),
        )
    return None


def _strict_model(base_url: str) -> str | None:
    """Pick a STRICT-capable free model for native ``json_schema`` mode.

    Server-enforced ``response_format={'type':'json_schema', strict:true}`` only
    works on models that honour the JSON-Schema grammar. Cerebras documents
    ``gpt-oss-120b`` as its production model with native strict JSON Schema.

    Returns a model id, or ``None`` when the provider has no strict-capable model
    (caller then skips straight to the existing ``Mode.JSON`` path).
    """
    try:
        bu = (base_url or "").lower()
        if "cerebras" in bu:
            # qwen-3-32b was retired from the public endpoint. Ignore that stale
            # historical override so old deployments do not hard-404 forever.
            configured = os.getenv("STRUCTURED_STRICT_MODEL", "gpt-oss-120b").strip()
            return "gpt-oss-120b" if configured == "qwen-3-32b" else configured
        if "groq" in bu:
            # Groq strict path: prefer qwen3.6-27b (langchain-groq migration note —
            # gpt-oss may not honour strict json_schema the same way).
            return os.getenv("STRUCTURED_STRICT_MODEL", "qwen/qwen3.6-27b")
    except Exception:
        return None
    return None


def _json_schema_mode():
    """Return ``instructor.Mode.JSON_SCHEMA`` if this instructor build has it, else None.

    Older instructor versions lack the native strict json_schema mode; in that
    case we transparently skip the strict-first attempt. Never raises.
    """
    try:
        import instructor

        return getattr(instructor.Mode, "JSON_SCHEMA", None)
    except Exception:
        return None


def available() -> bool:
    try:
        import instructor  # noqa: F401
        import openai  # noqa: F401

        return _provider() is not None
    except Exception:
        return False


def extract(
    response_model: type[T],
    system: str,
    user: str,
    max_tokens: int = 800,
    max_retries: int = 2,
    temperature: float = 0.4,
) -> T | None:
    """Return a validated `response_model` instance from a free LLM, or None.

    Never raises. Caller should treat None as "use the existing template fallback".
    """
    prov = _provider()
    if prov is None:
        return None
    base_url, api_key, model = prov
    messages = [
        {"role": "system", "content": system or ""},
        {"role": "user", "content": user},
    ]

    def _run(mode, mdl) -> T | None:
        # JSON mode = works with Cerebras/Groq (they lack OpenAI tool-calling mode).
        import instructor
        from openai import OpenAI

        client = instructor.from_openai(OpenAI(base_url=base_url, api_key=api_key), mode=mode)
        with _llm_span("extract", model=mdl, provider="free") as _obs:
            _result = client.chat.completions.create(
                model=mdl,
                response_model=response_model,
                max_retries=max_retries,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=messages,
            )
            _obs.record()
            return _result

    # Attempt 1 (additive): native server-enforced strict json_schema on a
    # strict-capable model. Falls through silently on any failure.
    _strict_mode = _json_schema_mode()
    _strict_mdl = _strict_model(base_url)
    if _strict_mode is not None and _strict_mdl:
        try:
            return _run(_strict_mode, _strict_mdl)
        except Exception as exc:
            logger.info("structured.extract strict json_schema failed (%s) — JSON fallback", exc)

    # Attempt 2: existing Mode.JSON path (unchanged behaviour).
    try:
        import instructor

        return _run(instructor.Mode.JSON, model)
    except Exception as exc:
        logger.info("structured.extract failed (%s) — caller should use fallback", exc)
        return None


async def aextract(
    response_model: type[T],
    system: str,
    user: str,
    max_tokens: int = 800,
    max_retries: int = 2,
    temperature: float = 0.4,
) -> T | None:
    """Async variant of extract() for async flows (e.g. marketing generators).

    Returns a validated `response_model` instance or None. Never raises.
    """
    prov = _provider()
    if prov is None:
        return None
    base_url, api_key, model = prov
    messages = [
        {"role": "system", "content": system or ""},
        {"role": "user", "content": user},
    ]

    async def _run(mode, mdl) -> T | None:
        import instructor
        from openai import AsyncOpenAI

        client = instructor.from_openai(AsyncOpenAI(base_url=base_url, api_key=api_key), mode=mode)
        with _llm_span("extract", model=mdl, provider="free") as _obs:
            _result = await client.chat.completions.create(
                model=mdl,
                response_model=response_model,
                max_retries=max_retries,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=messages,
            )
            _obs.record()
            return _result

    # Attempt 1 (additive): native server-enforced strict json_schema mode.
    _strict_mode = _json_schema_mode()
    _strict_mdl = _strict_model(base_url)
    if _strict_mode is not None and _strict_mdl:
        try:
            return await _run(_strict_mode, _strict_mdl)
        except Exception as exc:
            logger.info("structured.aextract strict json_schema failed (%s) — JSON fallback", exc)

    # Attempt 2: existing Mode.JSON path (unchanged behaviour).
    try:
        import instructor

        return await _run(instructor.Mode.JSON, model)
    except Exception as exc:
        logger.info("structured.aextract failed (%s) — caller should use fallback", exc)
        return None


__all__ = ["available", "extract", "aextract"]
