"""Provider-pinned, budget-aware gateway for engineering worker calls.

The gateway is intentionally side-effect-light: it chooses a provider, calls the
existing free-AI adapter, and returns structured usage evidence. Worktree edits,
commits, and deployment remain separate gated stages.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Awaitable, Callable

from app.dev_control.registry import MODEL_CATALOG, route_preview
from app.dev_control.service import admit_cost

ProviderCall = Callable[..., Awaitable[tuple[str, str] | tuple[str, str, dict[str, Any]]]]


def _provider_name(alias: str) -> str:
    return "ollama" if alias == "local" else alias


async def invoke(
    *,
    task_id: str,
    task_type: str,
    sensitivity: str,
    complexity: str,
    system: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    task_budget_usd: Decimal,
    daily_remaining_usd: Decimal,
    provider_call: ProviderCall | None = None,
) -> dict[str, Any]:
    """Run one bounded provider call and return audit-ready evidence."""
    decision = route_preview(task_type=task_type, sensitivity=sensitivity, complexity=complexity)
    candidates = [decision["selected_provider"], *decision.get("fallbacks", [])]
    attempted: list[dict[str, Any]] = []
    for alias in candidates:
        meta = MODEL_CATALOG.get(alias) or {}
        if not meta.get("configured") and alias != "local":
            attempted.append({"provider": alias, "skipped": "unconfigured"})
            continue
        admission = admit_cost(
            provider=alias,
            estimated_input_tokens=sum(len(str(m.get("content") or "")) for m in messages) // 4,
            estimated_output_tokens=max_tokens,
            task_budget_usd=task_budget_usd,
            daily_remaining_usd=daily_remaining_usd,
        )
        if not admission["allowed"]:
            return {
                "ok": False,
                "task_id": task_id,
                "reason": admission["reason"],
                "selected_provider": alias,
                "attempted": attempted,
                "usage": {
                    "estimated_cost_usd": str(admission["estimated_cost_usd"]),
                    "estimated": True,
                },
            }
        try:
            if provider_call is None:
                from app.voice_agent import free_ai

                provider_call = free_ai.chat_provider
            raw = await provider_call(
                _provider_name(alias),
                meta.get("model", ""),
                system,
                messages,
                max_tokens=max_tokens,
                temperature=0.2,
                scope=f"dev-task:{task_id}",
            )
            if len(raw) == 3:
                text, provider, usage = raw
            else:
                text, provider = raw
                usage = {
                    "estimated": True,
                    "prompt_tokens": sum(len(str(m.get("content") or "")) for m in messages) // 4,
                    "completion_tokens": len(text or "") // 4,
                }
            if text:
                input_tokens = int(usage.get("prompt_tokens") or 0)
                output_tokens = int(usage.get("completion_tokens") or 0)
                actual_cost = (
                    Decimal(input_tokens) * Decimal(str(meta.get("cost_input_usd_per_million", 0)))
                    + Decimal(output_tokens)
                    * Decimal(str(meta.get("cost_output_usd_per_million", 0)))
                ) / Decimal(1_000_000)
                return {
                    "ok": True,
                    "task_id": task_id,
                    "provider": provider or _provider_name(alias),
                    "model": meta.get("model"),
                    "text": text,
                    "usage": {**usage, "actual_cost_usd": str(actual_cost)},
                }
            attempted.append({"provider": alias, "error": "empty_response"})
        except Exception as exc:  # provider failure must fall through safely
            attempted.append({"provider": alias, "error": str(exc)[:160]})
    return {
        "ok": False,
        "task_id": task_id,
        "reason": "all_providers_failed",
        "attempted": attempted,
        "usage": {"estimated": True},
    }
