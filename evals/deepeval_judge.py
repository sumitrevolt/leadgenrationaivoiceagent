"""
deepeval_judge.py — FREE LLM judge for DeepEval (RAG/answer-quality regression).

KYUN: promptfoo prompt-level adversarial check karta; DeepEval RAG OUTPUT quality
(faithfulness/answer-relevancy) ko gate karta — alag layer, genuine gap-filler.
self_improve + code_upgrader behaviour mutate karte hain → eval gate na ho to
autonomous change CHUP-CHAP quality gira sakta. Yeh wahi safety-rail.

FREE-STACK: judge bhi free hai — Cerebras/Groq OpenAI-compatible endpoint (wahi key
jo promptfoo llm-eval.yml use karta: OPENAI_API_KEY + OPENAI_BASE_URL). Koi paid
OpenAI nahi. deepeval = CI/dev-only dep (requirements-dev.txt; prod lock me NAHI).

GRACEFUL: deepeval missing YA judge key absent => judge_available()=False =>
tests skip ho jaate (CI green rehti, advisory). Kabhi hard-fail nahi.

ENV (priority order):
  EVAL_JUDGE_API_KEY  > OPENAI_API_KEY > CEREBRAS_API_KEY > GROQ_API_KEY
  EVAL_JUDGE_BASE_URL > OPENAI_BASE_URL > (default Cerebras /v1)
  EVAL_JUDGE_MODEL    > (default gpt-oss-120b)
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

_DEFAULT_BASE = "https://api.cerebras.ai/v1"
_DEFAULT_MODEL = "gpt-oss-120b"


def _first_env(*keys: str) -> str:
    for k in keys:
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    return ""


def judge_api_key() -> str:
    return _first_env("EVAL_JUDGE_API_KEY", "OPENAI_API_KEY", "CEREBRAS_API_KEY", "GROQ_API_KEY")


def judge_base_url() -> str:
    return _first_env("EVAL_JUDGE_BASE_URL", "OPENAI_BASE_URL") or _DEFAULT_BASE


def judge_model() -> str:
    return _first_env("EVAL_JUDGE_MODEL") or _DEFAULT_MODEL


def _deepeval_ok() -> bool:
    try:
        import deepeval  # noqa: F401
        from deepeval.models.base_model import DeepEvalBaseLLM  # noqa: F401
        from openai import OpenAI  # noqa: F401

        return True
    except Exception:
        return False


def judge_available() -> bool:
    """deepeval + openai installed AND a judge key set. False => tests skip."""
    return bool(_deepeval_ok() and judge_api_key())


def get_judge() -> Optional[Any]:
    """Return a DeepEval judge model bound to the free provider, or None."""
    if not judge_available():
        return None
    try:
        from deepeval.models.base_model import DeepEvalBaseLLM
        from openai import OpenAI

        class _FreeJudge(DeepEvalBaseLLM):
            """OpenAI-compatible free judge (Cerebras/Groq). Schema-aware generate
            (DeepEval newer versions JSON schema maangti) + plain-text fallback."""

            def __init__(self) -> None:
                self._model = judge_model()
                self._client = OpenAI(api_key=judge_api_key(), base_url=judge_base_url())

            def load_model(self) -> Any:  # deepeval contract
                return self._client

            def get_model_name(self) -> str:
                return f"free-judge:{self._model}"

            def _complete(self, prompt: str, schema: Any = None) -> str:
                sys_msg = "You are a strict, objective evaluation judge."
                if schema is not None:
                    sys_msg += " Respond ONLY with a single valid JSON object, no prose."
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": sys_msg},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0,
                    max_tokens=1200,
                )
                return (resp.choices[0].message.content or "").strip()

            def generate(self, prompt: str, schema: Any = None) -> Any:
                text = self._complete(prompt, schema)
                if schema is None:
                    return text
                # best-effort JSON -> pydantic schema (DeepEval structured metrics)
                try:
                    m = re.search(r"\{.*\}", text, re.S)
                    data = json.loads(m.group(0)) if m else {}
                    return schema(**data)
                except Exception:
                    # last resort: let deepeval parse the raw string (older versions)
                    return text

            async def a_generate(self, prompt: str, schema: Any = None) -> Any:
                return self.generate(prompt, schema)

        return _FreeJudge()
    except Exception:
        return None


def skip_reason() -> str:
    if not _deepeval_ok():
        return "deepeval/openai not installed (pip install -r requirements-dev.txt)"
    if not judge_api_key():
        return "no judge key (set CEREBRAS_API_KEY / OPENAI_API_KEY / GROQ_API_KEY)"
    return ""
