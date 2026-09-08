"""
LLM Council — Karpathy-style 3-stage cross-model consensus (free-stack).

Stage 1: parallel opinions from distinct providers/models
Stage 2: anonymized peer ranking (Response A/B/C…)
Stage 3: Chairman synthesizes final answer

Uses free_ai.chat_provider() — NOT the fallback chain (diversity ke liye).
Gated LLM_COUNCIL=0 to disable. Never raises.
"""

from __future__ import annotations

import asyncio
import os
import re
from collections import defaultdict
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Free council members — sirf jinke keys set hon unhe use karenge
_DEFAULT_MEMBERS: list[tuple[str, str, str]] = [
    ("mistral", "mistral-small-latest", "Mistral Small"),
    ("groq", "openai/gpt-oss-20b", "Groq GPT-OSS 20B"),
    ("cerebras", "gpt-oss-120b", "Cerebras 120B"),
    ("gemini", "gemini-2.0-flash-lite", "Gemini Flash Lite"),
]
_CHAIRMAN: tuple[str, str] = ("mistral", "mistral-small-latest")
_MIN_MEMBERS = 2
_COUNCIL_TIMEOUT_S = 45.0


def council_enabled() -> bool:
    return os.getenv("LLM_COUNCIL", "1").strip().lower() not in ("0", "false", "off", "no")


def available_members() -> list[dict[str, str]]:
    """Council members jinke provider keys abhi set hain."""
    try:
        from app.voice_agent import free_ai

        flags = free_ai.PROVIDERS_AVAILABLE
    except Exception:
        flags = {}
    out: list[dict[str, str]] = []
    for provider, model, label in _DEFAULT_MEMBERS:
        if flags.get(provider):
            out.append({"provider": provider, "model": model, "label": label})
    return out


def _timeout_s() -> float:
    try:
        return float(os.getenv("COUNCIL_TIMEOUT_S", str(_COUNCIL_TIMEOUT_S)) or _COUNCIL_TIMEOUT_S)
    except Exception:
        return _COUNCIL_TIMEOUT_S


async def _ask(
    provider: str,
    model: str,
    user: str,
    *,
    system: str = "",
    max_tokens: int = 600,
    temperature: float = 0.5,
) -> tuple[str, str]:
    try:
        from app.voice_agent import free_ai

        return await free_ai.chat_provider(
            provider,
            model,
            system,
            [{"role": "user", "content": user}],
            max_tokens=max_tokens,
            temperature=temperature,
            scope="council",
            timeout_s=_timeout_s(),
        )
    except Exception as e:  # pragma: no cover
        logger.debug("council _ask err %s/%s: %s", provider, model, e)
        return "", provider


async def stage1_collect_responses(
    user_query: str, members: list[dict[str, str]]
) -> list[dict[str, Any]]:
    """Har available member se parallel opinion."""

    async def one(m: dict[str, str]) -> dict[str, Any]:
        text, prov = await _ask(
            m["provider"], m["model"], user_query, max_tokens=700, temperature=0.55
        )
        return {
            "provider": m["provider"],
            "model": m["model"],
            "label": m.get("label") or m["provider"],
            "response": text,
            "ok": bool(text),
        }

    raw = await asyncio.gather(*[one(m) for m in members], return_exceptions=True)
    out: list[dict[str, Any]] = []
    for r in raw:
        if isinstance(r, dict) and r.get("ok"):
            out.append(r)
    return out


def parse_ranking_from_text(ranking_text: str) -> list[str]:
    """FINAL RANKING: section se Response A/B/C order parse karo."""
    text = ranking_text or ""
    if "FINAL RANKING:" in text:
        section = text.split("FINAL RANKING:", 1)[1]
        numbered = re.findall(r"\d+\.\s*Response [A-Z]", section)
        if numbered:
            return [
                re.search(r"Response [A-Z]", m).group()
                for m in numbered
                if re.search(r"Response [A-Z]", m)
            ]
        matches = re.findall(r"Response [A-Z]", section)
        if matches:
            return matches
    return re.findall(r"Response [A-Z]", text)


async def stage2_collect_rankings(
    user_query: str,
    stage1_results: list[dict[str, Any]],
    members: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Har member anonymized responses rank kare."""
    labels = [chr(65 + i) for i in range(len(stage1_results))]
    label_to_model = {
        f"Response {label}": f"{r['label']} ({r['provider']})"
        for label, r in zip(labels, stage1_results)
    }
    responses_text = "\n\n".join(
        f"Response {label}:\n{r['response']}" for label, r in zip(labels, stage1_results)
    )
    ranking_prompt = f"""You are evaluating different responses to the following question:

Question: {user_query}

Here are the responses from different models (anonymized):

{responses_text}

Your task:
1. First, evaluate each response individually. For each response, explain what it does well and what it does poorly.
2. Then, at the very end of your response, provide a final ranking.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Do not add any other text or explanations in the ranking section

Example of the correct format for your ENTIRE response:

Response A provides good detail on X but misses Y...
Response B is accurate but lacks depth on Z...
Response C offers the most comprehensive answer...

FINAL RANKING:
1. Response C
2. Response A
3. Response B

Now provide your evaluation and ranking:"""

    async def rank(m: dict[str, str]) -> dict[str, Any]:
        text, prov = await _ask(
            m["provider"],
            m["model"],
            ranking_prompt,
            max_tokens=900,
            temperature=0.3,
        )
        parsed = parse_ranking_from_text(text)
        return {
            "provider": m["provider"],
            "model": m["model"],
            "label": m.get("label") or m["provider"],
            "ranking": text,
            "parsed_ranking": parsed,
            "ok": bool(text),
        }

    raw = await asyncio.gather(*[rank(m) for m in members], return_exceptions=True)
    out: list[dict[str, Any]] = []
    for r in raw:
        if isinstance(r, dict) and r.get("ok"):
            out.append(r)
    return out, label_to_model


def calculate_aggregate_rankings(
    stage2_results: list[dict[str, Any]],
    label_to_model: dict[str, str],
) -> list[dict[str, Any]]:
    """Cross-ranker average position — lower avg_rank = better."""
    model_positions: dict[str, list[int]] = defaultdict(list)
    for row in stage2_results:
        parsed = row.get("parsed_ranking") or parse_ranking_from_text(row.get("ranking") or "")
        for position, label in enumerate(parsed, start=1):
            model_name = label_to_model.get(label)
            if model_name:
                model_positions[model_name].append(position)
    aggregate: list[dict[str, Any]] = []
    for model, positions in model_positions.items():
        if positions:
            aggregate.append(
                {
                    "model": model,
                    "average_rank": round(sum(positions) / len(positions), 2),
                    "rankings_count": len(positions),
                }
            )
    aggregate.sort(key=lambda x: x["average_rank"])
    return aggregate


async def stage3_synthesize_final(
    user_query: str,
    stage1_results: list[dict[str, Any]],
    stage2_results: list[dict[str, Any]],
    chairman_provider: str,
    chairman_model: str,
) -> dict[str, Any]:
    """Chairman (Boss) — sab opinions + rankings merge karke final answer."""
    stage1_text = "\n\n".join(
        f"Model: {r['label']} ({r['provider']})\nResponse: {r['response']}" for r in stage1_results
    )
    stage2_text = "\n\n".join(
        f"Reviewer: {r['label']}\nRanking:\n{r['ranking']}" for r in stage2_results
    )
    chairman_prompt = f"""You are the Chairman of an LLM Council. Multiple AI models answered a user's question, then peer-reviewed each other's responses.

Original Question: {user_query}

STAGE 1 — Individual Responses:
{stage1_text}

STAGE 2 — Peer Rankings:
{stage2_text}

Your task: synthesize everything into ONE clear, accurate, actionable answer (Hinglish Roman script OK).
Consider individual insights, peer rankings, and agreement/disagreement patterns.
Be concise but complete (6-12 lines). Sirf final answer — meta commentary mat do."""

    text, prov = await _ask(
        chairman_provider,
        chairman_model,
        chairman_prompt,
        system="Tum LLM Council ke Chairman (Boss) ho. Collective wisdom se best final answer do.",
        max_tokens=800,
        temperature=0.35,
    )
    if not text:
        return {
            "provider": chairman_provider,
            "model": chairman_model,
            "response": "Council synthesis fail — chairman response nahi bana. Dobara try karo.",
            "ok": False,
        }
    return {
        "provider": chairman_provider,
        "model": chairman_model,
        "response": text,
        "ok": True,
    }


async def run_full_council(user_query: str) -> dict[str, Any]:
    """Complete 3-stage council. Never raises."""
    user_query = (user_query or "").strip()
    if not council_enabled():
        return {"ok": False, "error": "LLM Council disabled (LLM_COUNCIL=0)"}
    members = available_members()
    if len(members) < _MIN_MEMBERS:
        return {
            "ok": False,
            "error": f"Kam se kam {_MIN_MEMBERS} LLM providers chahiye — ab sirf {len(members)} available. Keys check karo.",
            "available_members": members,
        }

    chairman = _CHAIRMAN
    if not any(m["provider"] == chairman[0] for m in members):
        chairman = (members[0]["provider"], members[0]["model"])

    # Check past council verdicts (obsidian second brain)
    _past_context = ""
    try:
        from app.platform import obsidian_sync as _obs

        _past_context = _obs.brain_context(user_query, k=2)
    except Exception:
        pass

    # Prepend past-verdict context to the query so every stage sees it
    enriched_query = user_query
    if _past_context:
        enriched_query = (
            f"[Past Council Context]\n{_past_context}\n\n[Current Question]\n{user_query}"
        )

    try:
        stage1 = await stage1_collect_responses(enriched_query, members)
        if len(stage1) < _MIN_MEMBERS:
            return {
                "ok": False,
                "error": f"Stage 1: sirf {len(stage1)}/{len(members)} models ne jawab diya — quota/keys check karo.",
                "stage1": stage1,
                "available_members": members,
            }

        stage2, label_to_model = await stage2_collect_rankings(enriched_query, stage1, members)
        aggregate = calculate_aggregate_rankings(stage2, label_to_model)
        stage3 = await stage3_synthesize_final(
            enriched_query, stage1, stage2, chairman[0], chairman[1]
        )

        # Obsidian second-brain — write verdict to Decisions/ (INERT if OBSIDIAN_SYNC unset).
        try:
            from app.platform import obsidian_sync as _obs

            _obs.write_council_verdict(
                user_query,
                (stage3.get("response") or "")[:500],
                stage1,
            )
        except Exception:
            pass

        return {
            "ok": True,
            "stage1": stage1,
            "stage2": stage2,
            "stage3": stage3,
            "metadata": {
                "label_to_model": label_to_model,
                "aggregate_rankings": aggregate,
                "chairman": {"provider": chairman[0], "model": chairman[1]},
                "members_used": len(members),
            },
        }
    except Exception as e:  # pragma: no cover
        logger.warning("run_full_council failed: %s", e)
        return {"ok": False, "error": str(e)[:200]}


__all__ = [
    "council_enabled",
    "available_members",
    "parse_ranking_from_text",
    "calculate_aggregate_rankings",
    "run_full_council",
]
