"""Eval + deliverability hub — admin cockpit helpers (never-raise)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def deliverability_summary() -> dict[str, Any]:
    """DNS (SPF/DKIM/DMARC) + email warmup/complaint gate — ek payload."""
    out: dict[str, Any] = {"ok": True, "problems": [], "healthy": True}
    try:
        from app.platform import deliverability_monitor

        out["dns"] = await deliverability_monitor.run_check()
        for p in out["dns"].get("problems") or []:
            if isinstance(p, str):
                out["problems"].append(
                    {"kya": p, "fix": "Hostinger DNS / deliverability_monitor doc"}
                )
    except Exception as e:
        out["dns"] = {"error": str(e)[:200]}
        out["problems"].append({"kya": "DNS check fail", "fix": str(e)[:120]})
    try:
        from app.platform import email_warmup

        w = email_warmup.status()
        out["warmup"] = w
        rate = float(w.get("complaint_rate_7d_pct") or 0)
        thr = float(w.get("complaint_pause_threshold_pct") or 0.25)
        if w.get("paused"):
            out["problems"].append(
                {
                    "kya": f"Warmup PAUSED: {w.get('paused_reason') or 'unknown'}",
                    "fix": "Bounce/complaint fix karo, phir /api/growth/outreach/warmup/resume",
                }
            )
        elif rate >= thr and int(w.get("sent_7d") or 0) >= 400:
            out["problems"].append(
                {
                    "kya": f"Complaint rate {rate}% (7d) — Gmail/Yahoo gate",
                    "fix": "Outreach pause ho sakta hai — list quality + unsub link check karo",
                }
            )
    except Exception as e:
        out["warmup"] = {"error": str(e)[:200]}
    out["healthy"] = len(out["problems"]) == 0
    out["ok"] = "error" not in out.get("dns", {}) or "error" not in out.get("warmup", {})
    return out


async def run_rag_ab_gate(timeout_s: float = 120.0) -> dict[str, Any]:
    """Live KB pe RAG A/B gate (thread + deadline). Returns PASS/FAIL + delta table."""

    def _sync() -> dict[str, Any]:
        try:
            from scripts.rag_retrieval_ab import (
                compute_deltas,
                format_delta_table,
                make_kb_retrieve_fn,
            )

            fns = make_kb_retrieve_fn()
            report = compute_deltas(fns)
            winner = report.get("winner")
            rec = (
                f"Gate PASS — '{winner}' proven. Flip USE_RERANKER/USE_HYBRID_SEARCH per winner."
                if report.get("passed")
                else "Gate FAIL — retrieval flags OFF rakho; ColBERT/crossencoder mat bake karo abhi."
            )
            return {
                "ok": True,
                "passed": bool(report.get("passed")),
                "winner": winner,
                "report": report,
                "table": format_delta_table(report),
                "recommendation": rec,
            }
        except Exception as e:
            logger.warning("[eval_hub] rag ab gate failed: %s", e)
            return {"ok": False, "passed": False, "error": str(e)[:240]}

    try:
        result = await asyncio.wait_for(asyncio.to_thread(_sync), timeout=timeout_s)
    except asyncio.TimeoutError:
        return {"ok": False, "passed": False, "error": f"timeout after {timeout_s}s"}
    # Deep Memory: PASS hone pe winning (query, answer) pair KB me boost
    if result.get("passed") and result.get("winner"):
        await record_positive_eval(
            query="RAG retrieval gate — best strategy kya hai?",
            answer=result.get("recommendation", result["winner"]),
            namespace="skills",
        )
    return result


async def record_positive_eval(query: str, answer: str, namespace: str = "default") -> bool:
    """Deep Memory pattern: positive RAG eval → KB upsert for retrieval reinforcement.

    Har baar jab ek query ka answer accepted ho (user-feedback ya eval-gate PASS),
    woh (Q, A) pair KB me store ho — agla similar query directly yahi hit karega.
    Gated by EVAL_KB_BOOST=1. Never raises.
    """
    import os

    if os.environ.get("EVAL_KB_BOOST", "").strip() not in ("1", "true", "yes", "on"):
        return False
    q = (query or "").strip()
    a = (answer or "").strip()
    if not q or not a:
        return False
    try:
        from app.voice_agent.knowledge_base import get_knowledge_base

        kb = get_knowledge_base()
        doc_text = f"Q: {q}\nA: {a}"
        added = await asyncio.wait_for(
            asyncio.to_thread(
                lambda: kb.add_documents(
                    [{"text": doc_text, "source": "eval_positive"}], namespace=namespace
                )
            ),
            timeout=5.0,
        )
        return bool(added)
    except Exception as e:
        logger.debug("record_positive_eval skipped: %s", e)
        return False


__all__ = ["deliverability_summary", "run_rag_ab_gate", "record_positive_eval"]
