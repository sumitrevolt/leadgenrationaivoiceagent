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


def _provider() -> Optional[tuple]:
    cb = os.getenv("CEREBRAS_API_KEY")
    if cb:
        return "https://api.cerebras.ai/v1", cb, os.getenv("DEFAULT_LLM", "gpt-oss-120b")
    gq = os.getenv("GROQ_API_KEY")
    if gq:
        return "https://api.groq.com/openai/v1", gq, "llama-3.3-70b-versatile"
    return None


def available() -> bool:
    try:
        import instructor  # noqa: F401
        import openai  # noqa: F401

        return _provider() is not None
    except Exception:
        return False


def extract(
    response_model: Type[T],
    system: str,
    user: str,
    max_tokens: int = 800,
    max_retries: int = 2,
    temperature: float = 0.4,
) -> Optional[T]:
    """Return a validated `response_model` instance from a free LLM, or None.

    Never raises. Caller should treat None as "use the existing template fallback".
    """
    prov = _provider()
    if prov is None:
        return None
    base_url, api_key, model = prov
    try:
        import instructor
        from openai import OpenAI

        # JSON mode = works with Cerebras/Groq (they lack OpenAI tool-calling mode).
        client = instructor.from_openai(
            OpenAI(base_url=base_url, api_key=api_key), mode=instructor.Mode.JSON
        )
        with _llm_span("extract", model=model, provider="free") as _obs:
            _result = client.chat.completions.create(
                model=model,
                response_model=response_model,
                max_retries=max_retries,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system or ""},
                    {"role": "user", "content": user},
                ],
            )
            _obs.record()
            return _result
    except Exception as exc:
        logger.info("structured.extract failed (%s) — caller should use fallback", exc)
        return None


async def aextract(
    response_model: Type[T],
    system: str,
    user: str,
    max_tokens: int = 800,
    max_retries: int = 2,
    temperature: float = 0.4,
) -> Optional[T]:
    """Async variant of extract() for async flows (e.g. marketing generators).

    Returns a validated `response_model` instance or None. Never raises.
    """
    prov = _provider()
    if prov is None:
        return None
    base_url, api_key, model = prov
    try:
        import instructor
        from openai import AsyncOpenAI

        client = instructor.from_openai(
            AsyncOpenAI(base_url=base_url, api_key=api_key), mode=instructor.Mode.JSON
        )
        with _llm_span("extract", model=model, provider="free") as _obs:
            _result = await client.chat.completions.create(
                model=model,
                response_model=response_model,
                max_retries=max_retries,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system or ""},
                    {"role": "user", "content": user},
                ],
            )
            _obs.record()
            return _result
    except Exception as exc:
        logger.info("structured.aextract failed (%s) — caller should use fallback", exc)
        return None


__all__ = ["available", "extract", "aextract"]
