"""Dedicated code-review agent — Kilo-Code "Review agent" parity.

Kilo Code ka ek alag standout mode = dedicated "Review agent" jo diff/code ko
multi-dimension (correctness/security/performance/style/tests) pe LLM se review
karwa ke structured findings deta — blind one-shot prompt nahi. Is project me
review-bot skills the par koi RUNTIME review-agent endpoint nahi tha.

Yeh module woh capability AI staff + admin ko deta (read-only, never-raise, gated):
  - `review(code, dimensions)` → free-LLM se JSON findings ({dimension, severity,
    line, message} + summary). LLM fail/garbage → static minimal result (never empty).
  - Admin POST /api/agents-ext/code-review → ad-hoc code/diff review.
  - coordinator engineering crew future me same helper reuse kar sakte.

Design (project patterns):
  - `enabled()` sirf AUTOMATIC agent-review ko gate karta — default OFF = zero
    behaviour change. `review()` khud hamesha safe-callable (admin endpoint ke liye),
    bilkul jaise code_search.search flag-independent chalta.
  - free_ai LAZY import (heavy chain) — function ke andar, module-top pe nahi.
  - Defensive JSON parse (LLM kabhi prose+json mix deta) — strip to {...}.
  - Koi error / LLM down → static fallback dict (kabhi raise nahi, kabhi empty nahi).

Flag: CODE_REVIEWER=1
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_DEFAULT_DIMENSIONS = ["correctness", "security", "performance", "style", "tests"]
_CODE_CAP = 8000  # bahut bade diff par LLM ko sirf head bhejo (token + latency guard)
_VALID_SEVERITY = ("high", "med", "low")


def enabled() -> bool:
    """Gates AUTOMATIC agent review. Admin endpoint flag-independent."""
    return (os.getenv("CODE_REVIEWER") or "").strip().lower() in ("1", "true", "yes")


def _normalize_dimensions(dimensions: list[str] | None) -> list[str]:
    if not dimensions:
        return list(_DEFAULT_DIMENSIONS)
    out: list[str] = []
    for d in dimensions:
        s = str(d or "").strip().lower()
        if s and s not in out:
            out.append(s)
    return out or list(_DEFAULT_DIMENSIONS)


def _static_result(code: str, dimensions: list[str], note: str) -> dict[str, Any]:
    """LLM-independent minimal review — kabhi empty/raise na ho is liye floor."""
    return {
        "ok": False,
        "summary": f"static review ({note}) — LLM grounding unavailable",
        "dimensions": dimensions,
        "findings": [
            {
                "dimension": "review",
                "severity": "low",
                "line": None,
                "message": (
                    "LLM review unavailable; manual review recommended. "
                    f"({len((code or '').splitlines())} lines submitted)"
                ),
            }
        ],
    }


def _extract_json(text: str) -> dict[str, Any] | None:
    """LLM output me se pehla {...} block nikaalo (prose-wrapped JSON common hai)."""
    if not text:
        return None
    raw = text.strip()
    # ```json fences hata do
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1] if raw.count("```") >= 2 else raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        obj = json.loads(raw[start : end + 1])
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _clean_findings(obj: dict[str, Any]) -> list[dict[str, Any]]:
    """Parsed findings ko normalize — severity/line ko safe banao."""
    rows = obj.get("findings")
    if not isinstance(rows, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        sev = str(r.get("severity") or "low").strip().lower()
        if sev not in _VALID_SEVERITY:
            sev = "low"
        line = r.get("line")
        try:
            line = int(line) if line is not None else None
        except Exception:
            line = None
        cleaned.append(
            {
                "dimension": str(r.get("dimension") or "general").strip().lower()[:40],
                "severity": sev,
                "line": line,
                "message": str(r.get("message") or "").strip()[:600],
            }
        )
    return cleaned


async def review(code: str, dimensions: list[str] | None = None) -> dict[str, Any]:
    """Code/diff ka structured multi-dimension review.

    `code` = raw source YA unified-diff string (pass-through; LLM dono samajh leta).
    `dimensions` default = correctness/security/performance/style/tests.

    Returns {ok, summary, dimensions, findings:[{dimension,severity,line,message}]}.
    Never raises; LLM fail/garbage → static minimal result (never empty).
    """
    dims = _normalize_dimensions(dimensions)
    src = (code or "").strip()
    if not src:
        return {
            "ok": True,
            "summary": "empty input — nothing to review",
            "dimensions": dims,
            "findings": [],
        }

    snippet = src[:_CODE_CAP]
    try:
        import asyncio

        from app.voice_agent import free_ai

        system = (
            "You are a senior code reviewer. Review the provided code (which may be a "
            "unified diff). Be precise and terse. ONLY report real issues. Respond with "
            "STRICT JSON, no prose, in this exact shape: "
            '{"findings":[{"dimension":"<one of the requested>","severity":"high|med|low",'
            '"line":<int or null>,"message":"<short actionable note>"}],"summary":"<1-2 lines>"}. '
            "If the code is clean, return an empty findings list and a brief positive summary."
        )
        user = "Review dimensions: " + ", ".join(dims) + "\n\nCODE / DIFF:\n" + snippet
        reply, _provider = await asyncio.wait_for(
            free_ai.chat(
                system,
                [{"role": "user", "content": user}],
                max_tokens=600,
                temperature=0.2,
            ),
            timeout=45,
        )
        obj = _extract_json(reply or "")
        if not obj:
            return _static_result(src, dims, "unparseable LLM output")
        findings = _clean_findings(obj)
        summary = str(obj.get("summary") or "").strip()[:600] or "review complete"
        return {
            "ok": True,
            "summary": summary,
            "dimensions": dims,
            "findings": findings,
        }
    except Exception as e:  # pragma: no cover - defensive (never break the caller)
        logger.debug(f"code_reviewer.review failed: {e}")
        return _static_result(src, dims, "llm error/timeout")


__all__ = ["enabled", "review"]
