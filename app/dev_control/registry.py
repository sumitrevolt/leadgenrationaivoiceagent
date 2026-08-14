"""Configuration-driven worker model catalog and routing preview.

Model ids are deliberately environment-backed: provider names can exist in the
catalog without silently enabling an unverified or billable endpoint.

Planner / enforcer separation (ADR: hybrid flagship control plane):
  * ``route_preview`` is the PLANNER -- it returns the *ideal* provider escalation
    order for a task, including flagships that are not yet configured. It never
    performs a side effect.
  * ``app.dev_control.gateway`` is the ENFORCER -- it walks that ideal order and
    skips any non-local provider that is unconfigured or over budget, always
    falling back to the local model.

Keeping the two apart means an operator can see "we *would* use GLM here" in the
route preview while the gateway still guarantees nothing unconfigured/paid ever
fires by default. ``effective_provider`` in the preview is the honest "what will
actually run right now" answer given current configuration.
"""

from __future__ import annotations

import os
from typing import Any

_ENV_KEY = {
    "local": "LOCAL_LLM_URL",
    "glm": "GLM_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "kimi": "KIMI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "qwen": "QWEN_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
}


def _configured(provider: str) -> bool:
    env_name = _ENV_KEY.get(provider, "")
    return bool(os.getenv(env_name, "").strip()) if env_name else False


def _model(provider: str, default: str) -> str:
    return os.getenv(f"DEV_{provider.upper()}_MODEL", "").strip() or default


def _cost(provider: str, direction: str, default: float) -> float:
    """Per-provider $/million token cost, env-overridable so an operator can pin
    real metered prices without a code change (enterprise FinOps tunability)."""
    raw = os.getenv(f"DEV_{provider.upper()}_COST_{direction.upper()}", "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            return default
    return default


def _entry(
    provider: str,
    model_default: str,
    *,
    cost_in: float,
    cost_out: float,
    privacy: str,
    capabilities: list[str],
    extra_configured: bool = False,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": _model(provider, model_default),
        "configured": _configured(provider) or extra_configured,
        "cost_input_usd_per_million": _cost(provider, "in", cost_in),
        "cost_output_usd_per_million": _cost(provider, "out", cost_out),
        "privacy": privacy,
        "capabilities": capabilities,
    }


MODEL_CATALOG: dict[str, dict[str, Any]] = {
    "local": _entry(
        "local",
        "local-coding",
        cost_in=0.0,
        cost_out=0.0,
        privacy="local",
        capabilities=["code", "tests", "docs", "sensitive"],
        extra_configured=bool(os.getenv("OLLAMA_URL", "").strip()),
    ),
    "glm": _entry(
        "glm",
        "glm-5.2",
        cost_in=1.4,
        cost_out=4.4,
        privacy="external",
        capabilities=["code", "reasoning", "long_context"],
    ),
    "minimax": _entry(
        "minimax",
        "MiniMax-M3",
        cost_in=0.30,
        cost_out=1.20,
        privacy="external",
        capabilities=["code", "multimodal", "long_context"],
    ),
    "kimi": _entry(
        "kimi",
        "Kimi-K2.7-Code",
        cost_in=0.15,
        cost_out=0.60,
        privacy="external",
        capabilities=["code", "long_context"],
    ),
    "deepseek": _entry(
        "deepseek",
        "deepseek-chat",
        cost_in=0.27,
        cost_out=1.10,
        privacy="external",
        capabilities=["code", "reasoning"],
    ),
    "qwen": _entry(
        "qwen",
        "qwen3-coder",
        cost_in=0.20,
        cost_out=0.80,
        privacy="external",
        capabilities=["code", "reasoning"],
    ),
    "claude": _entry(
        "claude",
        "claude-reviewer",
        cost_in=3.0,
        cost_out=15.0,
        privacy="external",
        capabilities=["review", "architecture", "security"],
    ),
}

# Ideal escalation order per routing class (planner only -- enforcer filters).
_REVIEW_ORDER = ["claude", "glm", "deepseek", "local"]
_HIGH_COMPLEXITY_ORDER = ["glm", "deepseek", "kimi", "local"]
_ROUTINE_ORDER = ["local", "deepseek"]


def _dedupe_with_local(order: list[str]) -> list[str]:
    ordered: list[str] = []
    for c in order:
        if c in MODEL_CATALOG and c not in ordered:
            ordered.append(c)
    if "local" not in ordered:
        ordered.append("local")
    return ordered


def route_preview(*, task_type: str, sensitivity: str, complexity: str) -> dict[str, Any]:
    """Return a deterministic, side-effect-free routing decision (the PLAN).

    ``selected_provider``/``fallbacks`` describe the ideal escalation order (may
    include unconfigured flagships). ``effective_provider`` is what will actually
    run right now given configuration -- always a configured provider or ``local``.
    """
    sensitive = sensitivity.strip().lower() in {"sensitive", "restricted"}
    if sensitive:
        selected, fallbacks, reason = "local", ["local"], "sensitive_data_local_only"
        ordered = ["local"]
    else:
        if task_type.strip().lower() in {"review", "security", "architecture"}:
            ordered, reason = _dedupe_with_local(_REVIEW_ORDER), "high_value_review"
        elif complexity.strip().lower() == "high":
            ordered, reason = _dedupe_with_local(_HIGH_COMPLEXITY_ORDER), "high_complexity"
        else:
            ordered, reason = _dedupe_with_local(_ROUTINE_ORDER), "local_first_routine_work"
        selected, fallbacks = ordered[0], ordered[1:]

    effective = next(
        (c for c in ordered if c == "local" or MODEL_CATALOG[c]["configured"]), "local"
    )
    return {
        "selected_provider": selected,
        "selected_model": MODEL_CATALOG[selected]["model"],
        "fallbacks": fallbacks,
        "effective_provider": effective,
        "effective_model": MODEL_CATALOG[effective]["model"],
        "candidates": ordered,
        "configured": {c: bool(MODEL_CATALOG[c]["configured"]) for c in ordered},
        "reason": reason,
    }
