"""
Function / Tool Calling for the AI Voice Agent
==============================================

Yeh wahi "in-call action" capability hai jo Retell/Vapi/Bland dete hain: LLM
call ke beech me hi *tools* call kar sakta hai — appointment book karna,
availability check karna, human ko warm-transfer karna, lead info capture
karna, pricing batana, call end karna. LLM function/tool-calling se yeh trigger
hota hai.

Pieces:
    - Tool          : ek single tool ka declaration (name, description,
                      JSON-schema-ish parameters, async handler).
    - ToolResult    : handler ka unified output {ok, data, error}.
    - ToolRegistry  : tools register/get/list_schemas/execute karta hai
                      (defensive validation + execution).
    - parse_tool_call(llm_output): LLM ke output se tool call nikaalta hai —
                      OpenAI/Gemini-style JSON, ya simple "CALL name {json}".
    - build_default_registry(context): real services se wired built-in tools.
    - get_tool_registry(): module singleton.

Tool schema shape (LLM ko diya jaata hai, OpenAI/Gemini "function" style):
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Book an appointment slot for the lead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "when_iso": {"type": "string", "description": "..."},
                    "name":     {"type": "string"},
                    ...
                },
                "required": ["when_iso", "name", "phone"]
            }
        }
    }

Usage:
    from app.voice_agent.function_calling import (
        get_tool_registry, build_default_registry, parse_tool_call,
    )

    reg = build_default_registry(context={
        "lead": {"name": "Rahul", "phone": "9876543210"},
        "call_id": "abc123",
        "niche": "solar_commercial",
        "support_phone_number": "+919876543210",
    })

    schemas = reg.list_schemas()   # -> pass to your LLM as `tools`

    call = parse_tool_call(llm_output)         # {"name": ..., "args": {...}} or None
    if call:
        result = await reg.execute(call["name"], call["args"])  # -> ToolResult
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
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


# A tool handler is async: (args: dict) -> Any (or a ToolResult).
ToolHandler = Callable[[dict[str, Any]], Awaitable[Any]]


# --------------------------------------------------------------------------- #
# Core dataclasses
# --------------------------------------------------------------------------- #
@dataclass
class Tool:
    """
    A single callable tool exposed to the LLM.

    Attributes:
        name:        unique tool name (snake_case).
        description: what the tool does (LLM reads this to decide when to call).
        parameters:  JSON-schema-ish dict describing args. Minimal shape:
                     {"type": "object",
                      "properties": {"x": {"type": "string"}},
                      "required": ["x"]}
        handler:     async callable (args: dict) -> Any | ToolResult.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def schema(self) -> dict[str, Any]:
        """Return the OpenAI/Gemini-style function schema for this tool."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters or {"type": "object", "properties": {}},
            },
        }

    @property
    def required(self) -> list[str]:
        return list((self.parameters or {}).get("required", []) or [])


@dataclass
class ToolResult:
    """Unified output of a tool execution."""

    ok: bool
    data: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "data": self.data, "error": self.error}


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
class ToolRegistry:
    """
    Holds tools, exposes their schemas to the LLM, and executes them safely.

    Defensive by design: unknown tools, bad args, and handler exceptions all
    return a ToolResult(ok=False, error=...) — execute() never raises.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    # ---- registration ---- #
    def register(self, tool: Tool) -> None:
        """Register (or overwrite) a tool by name."""
        if not tool or not getattr(tool, "name", None):
            logger.warning("register(): ignoring tool without a name.")
            return
        if tool.name in self._tools:
            logger.debug(f"Overwriting existing tool '{tool.name}'.")
        self._tools[tool.name] = tool
        logger.debug(f"🛠️  Registered tool '{tool.name}'.")

    def get(self, name: str) -> Tool | None:
        """Return the tool by name, or None."""
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def list_schemas(self) -> list[dict[str, Any]]:
        """Return all tool schemas (OpenAI/Gemini function-calling style)."""
        return [t.schema() for t in self._tools.values()]

    # ---- execution ---- #
    async def execute(self, name: str, args: dict[str, Any] | None = None) -> ToolResult:
        """
        Validate + run the named tool. Never raises.

        Returns ToolResult(ok=False, error=...) for:
            - unknown tool name
            - missing required parameters
            - handler exceptions
        """
        args = dict(args or {})
        tool = self._tools.get(name)
        if tool is None:
            logger.warning(f"execute(): unknown tool '{name}'.")
            return ToolResult(ok=False, error=f"Unknown tool: {name!r}")

        # Validate required params (defensive — don't crash, just report).
        missing = [r for r in tool.required if r not in args or args[r] in (None, "")]
        if missing:
            return ToolResult(
                ok=False,
                error=f"Missing required parameter(s) for '{name}': {missing}",
            )

        try:
            logger.info(f"🛠️  Executing tool '{name}' args={_safe_args(args)}")
            out = await tool.handler(args)
            if isinstance(out, ToolResult):
                return out
            return ToolResult(ok=True, data=out)
        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"Tool '{name}' handler error: {e}")
            return ToolResult(ok=False, error=str(e))


def _safe_args(args: dict[str, Any]) -> dict[str, Any]:
    """Redact obvious PII for logs."""
    redacted = dict(args)
    for k in ("phone", "email", "to_human_number"):
        if k in redacted and redacted[k]:
            v = str(redacted[k])
            redacted[k] = (v[:3] + "***") if len(v) > 3 else "***"
    return redacted


# --------------------------------------------------------------------------- #
# LLM output -> tool call parsing
# --------------------------------------------------------------------------- #
_CALL_RE = re.compile(r"CALL\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(\{.*\})?", re.DOTALL)


def parse_tool_call(llm_output: Any) -> dict[str, Any] | None:
    """
    Extract a tool call from an LLM response.

    Supports BOTH:

    1. Structured tool-call JSON (OpenAI/Gemini/Anthropic-ish). The output may be:
       - a dict with "tool_calls" / "function_call" / "name"+"arguments"
       - a JSON string of the same
       - a bare {"name": "...", "arguments": {...}} / {"tool": "...", "args": {...}}

    2. Simple inline convention inside free text:
           CALL book_appointment {"when_iso": "2026-06-10T15:00", "name": "Rahul"}
       (args JSON optional; missing -> {}).

    Returns {"name": str, "args": dict} or None if no tool call is present.
    Never raises — bad JSON just yields None.
    """
    if llm_output is None:
        return None

    # --- dict / object forms ---
    if isinstance(llm_output, dict):
        parsed = _parse_dict_tool_call(llm_output)
        if parsed:
            return parsed
        # maybe it's a chat-completion-like object serialized to dict — fall
        # through to string scan of its content.
        text = json.dumps(llm_output)
    else:
        text = str(llm_output)

    # --- JSON string of a tool call ---
    stripped = _strip_code_fences(text).strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            obj = json.loads(stripped)
            parsed = _parse_dict_tool_call(obj)
            if parsed:
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

    # --- simple "CALL name {json}" convention ---
    m = _CALL_RE.search(text)
    if m:
        name = m.group(1)
        raw_args = m.group(2)
        args: dict[str, Any] = {}
        if raw_args:
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                # try to grab the first balanced {...}
                args = _loads_first_object(raw_args) or {}
        return {"name": name, "args": args if isinstance(args, dict) else {}}

    return None


def _parse_dict_tool_call(obj: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize the many possible dict shapes into {'name','args'}."""
    if not isinstance(obj, dict):
        return None

    # OpenAI chat: {"tool_calls": [{"function": {"name","arguments"}}]}
    tcs = obj.get("tool_calls")
    if isinstance(tcs, list) and tcs:
        fn = (tcs[0] or {}).get("function", {}) if isinstance(tcs[0], dict) else {}
        name = fn.get("name")
        if name:
            return {"name": name, "args": _coerce_args(fn.get("arguments"))}

    # OpenAI legacy: {"function_call": {"name","arguments"}}
    fc = obj.get("function_call")
    if isinstance(fc, dict) and fc.get("name"):
        return {"name": fc["name"], "args": _coerce_args(fc.get("arguments"))}

    # Bare: {"name": ..., "arguments"/"args"/"parameters": {...}}
    name = obj.get("name") or obj.get("tool") or obj.get("tool_name")
    if name:
        raw = (
            obj.get("arguments")
            if "arguments" in obj
            else obj.get("args", obj.get("parameters", {}))
        )
        return {"name": name, "args": _coerce_args(raw)}

    return None


def _coerce_args(raw: Any) -> dict[str, Any]:
    """arguments may be a dict or a JSON string — normalize to dict."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            val = json.loads(raw)
            return val if isinstance(val, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _strip_code_fences(text: str) -> str:
    return text.replace("```json", "").replace("```", "")


def _loads_first_object(text: str) -> dict[str, Any] | None:
    """Extract + parse the first balanced {...} from text."""
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


# --------------------------------------------------------------------------- #
# Built-in tools — wired to real services, simulate when unavailable.
# --------------------------------------------------------------------------- #
def build_default_registry(context: dict[str, Any] | None = None) -> ToolRegistry:
    """
    Build a registry pre-loaded with the standard in-call tools, wired to the
    real services (calendar_booking, warm_transfer, telephony) where available
    and degrading to sensible simulated results otherwise.

    `context` carries per-call info the handlers may need, e.g.:
        {
          "lead": {"name": "...", "phone": "...", "company_name": "..."},
          "call_id": "...",
          "niche": "solar_commercial",
          "conversation_history": [...],
          "to_human_number": "+91...",     # human agent (optional)
          "support_phone_number": "+91...",
        }
    """
    ctx = dict(context or {})
    reg = ToolRegistry()

    # ---------------- book_appointment ---------------- #
    async def _book_appointment(args: dict[str, Any]) -> ToolResult:
        lead = ctx.get("lead", {}) or {}
        name = args.get("name") or lead.get("name") or lead.get("contact_name") or ""
        phone = args.get("phone") or lead.get("phone") or ""
        when_iso = args.get("when_iso") or args.get("when") or ""
        notes = args.get("notes") or f"Booked via AI voice agent for {ctx.get('niche', '')}"
        try:
            from app.integrations.calendar_booking import get_calendar

            cal = get_calendar()
            res = await cal.book_slot(
                when_iso=when_iso,
                name=name,
                phone=phone,
                notes=notes,
                client_id=str(ctx.get("client_id") or ""),
                niche=str(ctx.get("niche") or ""),
            )
            return ToolResult(
                ok=res.ok,
                data={
                    "booking_id": res.booking_id,
                    "when": res.when,
                    "confirmation_text": res.confirmation_text,
                    "provider": res.provider,
                },
                error=res.error,
            )
        except Exception as e:
            logger.error(f"book_appointment: calendar unavailable ({e})")
            return ToolResult(
                ok=False,
                error=f"calendar unavailable: {e}",
                data={
                    "when": when_iso,
                    "confirmation_text": (
                        "Abhi booking system available nahi hai — main aapki detail le leti hoon, "
                        "hamari team aapko call karke slot confirm kar degi."
                    ),
                    "provider": "unavailable",
                },
            )

    reg.register(
        Tool(
            name="book_appointment",
            description=(
                "Book an appointment/demo slot for the lead at a specific time. "
                "Call this once the lead agrees to a date and time."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "when_iso": {
                        "type": "string",
                        "description": "Start time, ISO 8601 e.g. '2026-06-10T15:00'.",
                    },
                    "name": {"type": "string", "description": "Lead's name."},
                    "phone": {"type": "string", "description": "Lead's phone number."},
                    "notes": {"type": "string", "description": "Optional context/notes."},
                },
                "required": ["when_iso"],
            },
            handler=_book_appointment,
        )
    )

    # ---------------- check_availability ---------------- #
    async def _check_availability(args: dict[str, Any]) -> ToolResult:
        date_str = args.get("date") or args.get("date_str") or ""
        duration = int(args.get("duration_min", 15) or 15)
        try:
            from app.integrations.calendar_booking import get_calendar

            cal = get_calendar()
            slots = await cal.check_availability(date_str, duration_min=duration)
            return ToolResult(
                ok=True,
                data={"date": date_str, "slots": slots[:8], "total": len(slots)},
            )
        except Exception as e:
            logger.error(f"check_availability: calendar unavailable ({e}); offering standard hours")
            return ToolResult(
                ok=True,
                data={
                    "date": date_str,
                    "slots": [f"{date_str}T10:00", f"{date_str}T15:00"],
                    "total": 2,
                    "provider": "default_hours",
                    "note": "standard business hours (live calendar unavailable)",
                },
            )

    reg.register(
        Tool(
            name="check_availability",
            description=(
                "Check free appointment slots for a given date before offering times to the lead."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date 'YYYY-MM-DD' to check availability for.",
                    },
                    "duration_min": {
                        "type": "integer",
                        "description": "Meeting length in minutes (default 15).",
                    },
                },
                "required": ["date"],
            },
            handler=_check_availability,
        )
    )

    # ---------------- reschedule_appointment ---------------- #
    async def _reschedule_appointment(args: dict[str, Any]) -> ToolResult:
        lead = ctx.get("lead", {}) or {}
        phone = args.get("phone") or lead.get("phone") or ""
        new_when = args.get("new_when_iso") or args.get("when_iso") or args.get("when") or ""
        try:
            from app.integrations.calendar_booking import get_calendar

            cal = get_calendar()
            res = await cal.reschedule(
                new_when_iso=new_when,
                phone=phone,
                booking_id=args.get("booking_id") or "",
                name=args.get("name") or lead.get("name") or "",
                client_id=str(ctx.get("client_id") or ""),
                niche=str(ctx.get("niche") or ""),
            )
            return ToolResult(
                ok=res.ok,
                data={
                    "booking_id": res.booking_id,
                    "when": res.when,
                    "confirmation_text": res.confirmation_text,
                    "provider": res.provider,
                },
                error=res.error,
            )
        except Exception as e:
            logger.error(f"reschedule_appointment: calendar unavailable ({e})")
            return ToolResult(
                ok=False,
                error=f"calendar unavailable: {e}",
                data={
                    "confirmation_text": (
                        "Abhi reschedule system available nahi — main note kar leti hoon, "
                        "team aapko call karke naya slot confirm kar degi."
                    ),
                },
            )

    reg.register(
        Tool(
            name="reschedule_appointment",
            description=(
                "Move an EXISTING appointment to a new time. Call when the lead asks "
                "to reschedule/postpone/change their booked slot."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "new_when_iso": {
                        "type": "string",
                        "description": "New start time, ISO 8601 e.g. '2026-06-30T15:00'.",
                    },
                    "phone": {
                        "type": "string",
                        "description": "Lead's phone (to find their booking).",
                    },
                    "booking_id": {
                        "type": "string",
                        "description": "Existing booking id (optional).",
                    },
                    "name": {"type": "string", "description": "Lead's name (optional)."},
                },
                "required": ["new_when_iso"],
            },
            handler=_reschedule_appointment,
        )
    )

    # ---------------- transfer_to_human ---------------- #
    async def _transfer_to_human(args: dict[str, Any]) -> ToolResult:
        to_human = (
            args.get("to_human_number")
            or ctx.get("to_human_number")
            or (settings.support_phone_number if settings else "")
            or ""
        )
        call_id = ctx.get("call_id") or args.get("call_id") or "unknown-call"
        reason = args.get("reason", "")
        lead = ctx.get("lead", {}) or {}
        history = ctx.get("conversation_history", []) or []
        try:
            from app.telephony.warm_transfer import get_warm_transfer

            wt = get_warm_transfer()
            brief = await wt.build_brief_async(history, lead)
            if reason:
                brief = f"{brief} Reason for transfer: {reason}."
            res = await wt.transfer(
                call_id=call_id,
                to_human_number=to_human,
                context_summary=brief,
            )
            return ToolResult(
                ok=res.ok,
                data={
                    "status": res.status,
                    "human_call_id": res.human_call_id,
                    "brief": res.brief,
                    "steps": res.steps,
                    "provider": res.provider,
                },
                error=res.error,
            )
        except Exception as e:
            logger.error(f"transfer_to_human: transfer unavailable ({e})")
            return ToolResult(
                ok=False,
                error=f"transfer unavailable: {e}",
                data={
                    "status": "unavailable",
                    "confirmation_text": (
                        "Abhi live transfer possible nahi hai — main aapka number note kar leti hoon, "
                        "hamari team turant callback karegi."
                    ),
                    "provider": "unavailable",
                },
            )

    reg.register(
        Tool(
            name="transfer_to_human",
            description=(
                "Warm-transfer the live call to a human agent, passing along a "
                "context brief so the lead doesn't repeat themselves. Use when the "
                "lead wants a human, has a complex request, or is high-value."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Why the transfer is needed.",
                    },
                    "to_human_number": {
                        "type": "string",
                        "description": "Optional override for the human agent's number.",
                    },
                },
                "required": [],
            },
            handler=_transfer_to_human,
        )
    )

    # ---------------- capture_lead_info ---------------- #
    async def _capture_lead_info(args: dict[str, Any]) -> ToolResult:
        # Merge captured fields into the shared context's lead dict so the rest
        # of the pipeline can read them.
        lead = ctx.setdefault("lead", {})
        fields = {k: v for k, v in args.items() if v not in (None, "")}
        lead.update(fields)
        logger.info(f"🛠️  Captured lead info: {list(fields.keys())}")
        return ToolResult(ok=True, data={"captured": fields, "lead": lead})

    reg.register(
        Tool(
            name="capture_lead_info",
            description=(
                "Store qualification info the lead just shared (decision maker, "
                "budget, timeline, email, etc.) so it's saved to the CRM."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                    "company_name": {"type": "string"},
                    "budget_range": {"type": "string"},
                    "timeline": {"type": "string"},
                    "is_decision_maker": {"type": "boolean"},
                    "interest_level": {
                        "type": "string",
                        "description": "high | medium | low | none",
                    },
                    "notes": {"type": "string"},
                },
                "required": [],
            },
            handler=_capture_lead_info,
        )
    )

    # ---------------- get_pricing_info ---------------- #
    async def _get_pricing_info(args: dict[str, Any]) -> ToolResult:
        niche = args.get("niche") or ctx.get("niche") or ""
        # Grounded pricing — FLAT monthly per niche-band (voice_packages.py = source of truth).
        try:
            from app.marketing.voice_packages import (
                BANDS,
                PILOT_CALL_CAP,
                PILOT_DAYS,
                niche_band,
            )

            band = niche_band(niche) if niche else "A"
            price = BANDS[band]["price_month"]
            pricing = {
                "model": "flat_monthly_per_band",
                "price_inr_month": price,
                "band": band,
                "summary": (
                    f"Flat ₹{price:,}/mo (Band {band}) — UNLIMITED AI calls aapke niche pe, "
                    f"koi per-lead ya per-minute charge nahi. Pehle {PILOT_DAYS}-din free pilot "
                    f"({PILOT_CALL_CAP} calls, ₹0, koi card nahi). Cancel anytime."
                ),
            }
        except Exception:
            pricing = {
                "model": "flat_monthly_per_band",
                "summary": (
                    "Flat monthly per niche-band — Band A ₹4,999, B ₹9,999, C ₹19,999/mo. "
                    "UNLIMITED AI calls, koi per-lead/per-minute charge nahi. Free 7-din pilot."
                ),
            }
        # Enrich with niche deal value from niches.py if available.
        try:
            from app.niches import NICHES

            cfg = NICHES.get(niche, {}) if niche else {}
            if cfg.get("avg_deal_value"):
                pricing["niche_avg_deal_value"] = cfg["avg_deal_value"]
            if cfg.get("name"):
                pricing["niche"] = cfg["name"]
        except Exception:
            pass
        return ToolResult(ok=True, data=pricing)

    reg.register(
        Tool(
            name="get_pricing_info",
            description=(
                "Get the grounded pricing details to quote to the lead "
                "(flat monthly per niche-band model). Use when the lead asks about cost."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "niche": {
                        "type": "string",
                        "description": "Optional niche key for niche-specific deal value.",
                    },
                },
                "required": [],
            },
            handler=_get_pricing_info,
        )
    )

    # ---------------- end_call ---------------- #
    async def _end_call(args: dict[str, Any]) -> ToolResult:
        outcome = args.get("outcome", "ended")
        reason = args.get("reason", "")
        call_id = ctx.get("call_id") or args.get("call_id") or "unknown-call"
        # Best-effort hangup via telephony if it exposes one; never required.
        try:
            from app.telephony.telephony_service import get_telephony_service

            svc = get_telephony_service()
            for m in ("hangup", "end_call", "hangup_call"):
                fn = getattr(svc, m, None)
                if callable(fn):
                    res = fn(call_id)
                    if hasattr(res, "__await__"):
                        await res
                    break
        except Exception as e:
            logger.debug(f"end_call telephony hangup skipped: {e}")
        logger.info(f"🛠️  end_call requested (outcome={outcome}).")
        return ToolResult(
            ok=True,
            data={"should_end": True, "outcome": outcome, "reason": reason},
        )

    reg.register(
        Tool(
            name="end_call",
            description=(
                "End the call politely. Use when the conversation is complete, the "
                "lead is not interested after handling objections, or a goodbye is given."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "outcome": {
                        "type": "string",
                        "description": "qualified | not_interested | callback | ended",
                    },
                    "reason": {"type": "string"},
                },
                "required": [],
            },
            handler=_end_call,
        )
    )

    logger.info(f"🛠️  Default tool registry built: {reg.names()}")
    return reg


# --------------------------------------------------------------------------- #
# Module-level singleton
# --------------------------------------------------------------------------- #
_registry: ToolRegistry | None = None


def get_tool_registry(context: dict[str, Any] | None = None) -> ToolRegistry:
    """
    Return the process-wide ToolRegistry singleton (lazy init with defaults).

    Note: the default registry's handlers close over the `context` provided on
    first call. For per-call context, prefer building a fresh registry with
    `build_default_registry(context)`.
    """
    global _registry
    if _registry is None:
        _registry = build_default_registry(context)
    return _registry


__all__ = [
    "Tool",
    "ToolResult",
    "ToolRegistry",
    "parse_tool_call",
    "build_default_registry",
    "get_tool_registry",
]
