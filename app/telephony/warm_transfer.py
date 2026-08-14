"""
Warm Transfer Service
=====================

"In-call action" feature jaise Retell/Vapi/Bland dete hain: AI agent call ke
beech me hi ek HUMAN agent ko transfer kar sakta hai — par cold transfer nahi.
Warm transfer matlab: pehle human ko ek short CONTEXT brief diya jaata hai
(kaun hai lead, kya chahiye, ab tak kya hua), phir dono ko bridge/conference
karke jod diya jaata hai. Lead ko dobara apni baat repeat nahi karni padti.

Warm-transfer pattern (emulated):
    1. HOLD  — lead ko hold pe daalo (hold music / "ek second ruko").
    2. WHISPER — human agent ko call/whisper karke chhota context brief sunao
                 (LLM se summarize karte hain agar brain available ho).
    3. BRIDGE — lead + human ko conference me bridge kar do; AI step back.

Telephony legs `telephony_service` ke through jaate hain. Jab koi real provider
configured nahi hota, to SIMULATION mode me har step log hota hai aur ek
TransferResult return hota hai — pura flow bina keys ke chalta hai.

Usage:
    from app.telephony.warm_transfer import get_warm_transfer

    wt = get_warm_transfer()
    brief = wt.build_brief(conversation_history, lead={"name": "Rahul", ...})
    res = await wt.transfer(call_id="abc", to_human_number="9876543210",
                            context_summary=brief)
    # res -> TransferResult(ok, status, human_call_id, brief, steps, error)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

try:
    from app.config import settings
except Exception:  # pragma: no cover
    settings = None  # type: ignore

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)


@dataclass
class TransferResult:
    """Unified result for a warm-transfer attempt."""

    ok: bool
    status: str  # bridged | failed | no_agent | simulated
    call_id: str | None = None  # original lead call
    human_call_id: str | None = None  # leg dialed to the human agent
    to_human_number: str = ""
    brief: str = ""
    provider: str = "simulation"
    steps: list[str] = field(default_factory=list)
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class WarmTransfer:
    """
    Orchestrates a warm transfer of a live call to a human agent.

    Defensive: telephony ya brain available na ho to bhi crash nahi karta —
    steps log karke ek TransferResult deta hai (SIMULATION).
    """

    def __init__(self, telephony: Any = None, brain: Any = None):
        # Lazily resolve dependencies so import never fails.
        self._telephony = telephony
        self._brain = brain
        self._brain_tried = False

    # ------------------------------------------------------------------ #
    # Dependency resolution (lazy + safe)
    # ------------------------------------------------------------------ #
    def _get_telephony(self):
        if self._telephony is not None:
            return self._telephony
        try:
            from app.telephony.telephony_service import get_telephony_service

            self._telephony = get_telephony_service()
        except Exception as e:
            logger.debug(f"telephony unavailable for warm-transfer: {e}")
            self._telephony = None
        return self._telephony

    def _get_brain(self):
        if self._brain is not None or self._brain_tried:
            return self._brain
        self._brain_tried = True
        try:
            from app.voice_agent.llm_brain import LLMBrain

            self._brain = LLMBrain()
        except Exception as e:
            logger.debug(f"LLMBrain unavailable for brief summarization: {e}")
            self._brain = None
        return self._brain

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    async def transfer(
        self,
        call_id: str,
        to_human_number: str,
        context_summary: str,
    ) -> TransferResult:
        """
        Warm-transfer the live `call_id` to `to_human_number`, whispering
        `context_summary` to the human before bridging.

        Never raises — degrades to a simulated TransferResult on any failure.
        """
        steps: list[str] = []
        to_human_number = (to_human_number or "").strip()

        if not to_human_number:
            return TransferResult(
                ok=False,
                status="no_agent",
                call_id=call_id,
                brief=context_summary,
                error="No human agent number provided.",
                steps=["No to_human_number — cannot transfer."],
            )

        telephony = self._get_telephony()
        provider = getattr(telephony, "provider", "simulation") if telephony else "simulation"

        # STEP 1 — put the lead on hold.
        steps.append(f"[HOLD] Lead call {call_id} placed on hold (hold music).")
        logger.info(f"🤝 [WARM-TRANSFER] Hold lead {call_id}")
        await self._safe_hold(telephony, call_id)

        # STEP 2 — dial the human agent and whisper the context brief.
        steps.append(f"[WHISPER] Dialing human agent {to_human_number} and whispering brief.")
        logger.info(f"🤝 [WARM-TRANSFER] Whisper brief to agent {to_human_number}")
        human_call_id = None
        try:
            if telephony is not None and provider != "simulation":
                # Human-agent leg = transactional (lead asked for a human on a
                # live call) — promotional default put this leg through the DND
                # gate, which fail-closes without a DND provider and killed
                # every warm transfer (audit 2026-07-04).
                result = await telephony.place_call(to_human_number, call_type="transactional")
                human_call_id = getattr(result, "call_id", None)
                status = getattr(result, "status", "")
                steps.append(f"[WHISPER] Agent leg status: {status}")
                if status in ("failed", "no_answer", "busy"):
                    steps.append("[ABORT] Human agent unreachable — return lead to AI.")
                    await self._safe_unhold(telephony, call_id)
                    return TransferResult(
                        ok=False,
                        status="no_agent",
                        call_id=call_id,
                        human_call_id=human_call_id,
                        to_human_number=to_human_number,
                        brief=context_summary,
                        provider=provider,
                        steps=steps,
                        error=f"Human agent leg {status}.",
                    )
            else:
                # Simulation: pretend the agent answered after a short ring.
                await asyncio.sleep(0.1)
                human_call_id = f"human_{call_id}"
                steps.append("[WHISPER] (SIMULATION) Agent answered; brief delivered.")
        except Exception as e:
            logger.error(f"Warm-transfer whisper leg failed: {e}")
            await self._safe_unhold(telephony, call_id)
            return TransferResult(
                ok=False,
                status="failed",
                call_id=call_id,
                to_human_number=to_human_number,
                brief=context_summary,
                provider=provider,
                steps=steps + [f"[ERROR] {e}"],
                error=str(e),
            )

        # The brief itself is "spoken" to the human here (whisper). Log it so the
        # transcript captures what the human heard.
        logger.info(f"🤝 [WARM-TRANSFER] Brief to agent:\n{context_summary}")
        steps.append("[WHISPER] Brief: " + context_summary.replace("\n", " / "))

        # STEP 3 — bridge the lead + human into a conference; AI steps back.
        steps.append(f"[BRIDGE] Conferencing lead {call_id} + agent {human_call_id}.")
        logger.info(f"🤝 [WARM-TRANSFER] Bridge {call_id} <-> {human_call_id}")
        await self._safe_bridge(telephony, call_id, human_call_id)
        await self._safe_unhold(telephony, call_id)

        status = "bridged" if provider != "simulation" else "simulated"
        steps.append(f"[DONE] Warm transfer complete ({status}). AI stepping back.")
        return TransferResult(
            ok=True,
            status=status,
            call_id=call_id,
            human_call_id=human_call_id,
            to_human_number=to_human_number,
            brief=context_summary,
            provider=provider,
            steps=steps,
            meta={"transferred_at": datetime.now().isoformat()},
        )

    def build_brief(
        self,
        conversation_history: list[dict[str, str]],
        lead: dict[str, Any] | None = None,
    ) -> str:
        """
        Build a short human-agent briefing from the conversation + lead data.

        Sync + dependency-free so it always works (used as the whisper text).
        For an LLM-polished brief, call `build_brief_async`.
        """
        lead = lead or {}
        name = lead.get("name") or lead.get("contact_name") or "the lead"
        company = lead.get("company_name") or lead.get("company") or ""
        phone = lead.get("phone") or ""
        interest = lead.get("interest_level") or lead.get("interest_score") or ""

        # Pull the last few user turns as "what they want".
        user_turns = [
            m.get("content", "") for m in (conversation_history or []) if m.get("role") == "user"
        ]
        recent = " | ".join(t for t in user_turns[-3:] if t).strip()

        lines = [f"Warm transfer: {name}" + (f" from {company}" if company else "") + "."]
        if phone:
            lines.append(f"Phone: {phone}.")
        if interest:
            lines.append(f"Interest: {interest}.")
        if recent:
            lines.append(f"They said: {recent}.")
        lines.append("Lead is on the line and ready — please take over warmly.")
        return " ".join(lines)

    async def build_brief_async(
        self,
        conversation_history: list[dict[str, str]],
        lead: dict[str, Any] | None = None,
    ) -> str:
        """LLM-summarized brief if a brain is available; else the rule-based one."""
        base = self.build_brief(conversation_history, lead)
        brain = self._get_brain()
        if brain is None:
            return base
        try:
            transcript = "\n".join(
                f"{m.get('role', 'user')}: {m.get('content', '')}"
                for m in (conversation_history or [])[-12:]
            )
            prompt = (
                "Tum ek call ko human agent ko warm-transfer kar rahe ho. "
                "Niche conversation aur lead info se 2-3 short sentence ka brief "
                "banao jo human agent ko 10 second me sab samjha de: kaun hai, "
                "kya chahiye, ab tak kya hua, next best step. Sirf brief likho.\n\n"
                f"LEAD: {lead or {}}\n\nCONVERSATION:\n{transcript}"
            )
            if hasattr(brain, "_generate"):
                out = await brain._generate(prompt)
                if isinstance(out, str) and out.strip():
                    return out.strip()
        except Exception as e:
            logger.debug(f"LLM brief fallback: {e}")
        return base

    # ------------------------------------------------------------------ #
    # Telephony leg helpers (best-effort; never raise)
    # ------------------------------------------------------------------ #
    async def _safe_hold(self, telephony, call_id) -> None:
        await self._safe_call(telephony, "hold_call", call_id)

    async def _safe_unhold(self, telephony, call_id) -> None:
        await self._safe_call(telephony, "unhold_call", call_id)

    async def _safe_bridge(self, telephony, call_id, human_call_id) -> None:
        if telephony is None:
            return
        for method in ("bridge_calls", "conference", "create_conference"):
            fn = getattr(telephony, method, None)
            if callable(fn):
                try:
                    res = fn(call_id, human_call_id)
                    if asyncio.iscoroutine(res):
                        await res
                    return
                except Exception as e:
                    logger.debug(f"bridge via {method} failed: {e}")

    @staticmethod
    async def _safe_call(telephony, method: str, *args) -> None:
        """Call telephony.<method>(*args) if it exists; swallow errors."""
        if telephony is None:
            return
        fn = getattr(telephony, method, None)
        if not callable(fn):
            return
        try:
            res = fn(*args)
            if asyncio.iscoroutine(res):
                await res
        except Exception as e:
            logger.debug(f"telephony.{method} failed (non-fatal): {e}")


# ---------------------------------------------------------------------- #
# Module-level singleton
# ---------------------------------------------------------------------- #
_warm_transfer: WarmTransfer | None = None


def get_warm_transfer() -> WarmTransfer:
    """Return the process-wide WarmTransfer singleton (lazy init)."""
    global _warm_transfer
    if _warm_transfer is None:
        _warm_transfer = WarmTransfer()
    return _warm_transfer


__all__ = ["WarmTransfer", "TransferResult", "get_warm_transfer"]
