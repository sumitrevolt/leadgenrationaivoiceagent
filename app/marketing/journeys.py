"""Omnichannel journey / rule engine (Expedify-style) — event → condition → action.

Ek event (inquiry/signup/no-show/reply) aane par matching ENABLED rules chalte
hain. Har action DEFAULT = **DRAFT** (WhatsApp/email message ready, 1-click human
send) — auto-send NAHI (ban-safe + tumhari "1-click human" culture). Cross-channel
automation ek hi rule-engine se.

GATED: `emit_event` sirf JOURNEY_ENGINE=1 pe actions chalata (default OFF = aaj
jaisa zero change). Engine import-safe, kabhi raise nahi karta.

Store: data/journeys.jsonl (rules) · data/journey_runs.jsonl (execution log/drafts).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_JOURNEYS = os.path.join("data", "journeys.jsonl")
_RUNS = os.path.join("data", "journey_runs.jsonl")

# Valid trigger events (jis par rules fire ho sakte).
TRIGGERS = {"inquiry_received", "signup", "no_show", "email_reply", "manual"}
# Valid actions (sab ban-safe: draft/note; koi auto-send default me nahi).
ACTIONS = {
    "draft_whatsapp",
    "draft_email",
    "schedule_callback",
    "notify",
    "add_tag",
    "request_review",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _enabled() -> bool:
    return os.environ.get("JOURNEY_ENGINE", "0").strip().lower() in ("1", "true", "yes")


# --------------------------------------------------------------------------- #
# Store (jsonl, defensive — kabhi raise nahi)
# --------------------------------------------------------------------------- #
def _read(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception as e:
        logger.debug(f"[journeys] read {path} skip: {e}")
    return rows


def _write_all(path: str, rows: list[dict[str, Any]]) -> None:
    # Lock + atomic — 2 web workers (API CRUD + triggers) concurrent likh sakte.
    try:
        from app.utils.file_lock import locked_rewrite

        content = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        if not locked_rewrite(path, content):
            logger.warning(f"[journeys] locked write failed: {path}")
    except Exception as e:
        logger.warning(f"[journeys] write {path} failed: {e}")


def _append(path: str, rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[journeys] append {path} failed: {e}")


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
def list_journeys() -> list[dict[str, Any]]:
    return _read(_JOURNEYS)


def add_journey(
    name: str,
    trigger: str,
    actions: list[dict[str, Any]],
    condition: dict[str, Any] | None = None,
    enabled: bool = False,
) -> dict[str, Any]:
    """Naya rule banao. enabled default FALSE (review karke ON karo). Kabhi raise nahi."""
    trig = (trigger or "").strip()
    if trig not in TRIGGERS:
        trig = "manual"
    safe_actions = []
    for a in actions or []:
        t = str((a or {}).get("type") or "").strip()
        if t in ACTIONS:
            safe_actions.append({"type": t, "params": (a.get("params") or {})})
    rec = {
        "id": uuid.uuid4().hex[:12],
        "name": (name or "Untitled rule").strip()[:120],
        "trigger": trig,
        "condition": condition or {},
        "actions": safe_actions,
        "enabled": bool(enabled),
        "created_at": _now(),
    }
    rows = list_journeys()
    rows.append(rec)
    _write_all(_JOURNEYS, rows)
    return rec


def set_enabled(journey_id: str, enabled: bool) -> bool:
    rows = list_journeys()
    hit = False
    for r in rows:
        if r.get("id") == journey_id:
            r["enabled"] = bool(enabled)
            hit = True
    if hit:
        _write_all(_JOURNEYS, rows)
    return hit


def delete_journey(journey_id: str) -> bool:
    rows = list_journeys()
    new = [r for r in rows if r.get("id") != journey_id]
    if len(new) != len(rows):
        _write_all(_JOURNEYS, new)
        return True
    return False


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    return list(reversed(_read(_RUNS)))[:limit]


def seed_defaults() -> int:
    """Agar koi rule na ho to 3 useful rules seed karo (DISABLED — review karke ON)."""
    if list_journeys():
        return 0
    defaults = [
        {
            "name": "Inquiry → WhatsApp + email follow-up draft",
            "trigger": "inquiry_received",
            "condition": {},
            "actions": [
                {"type": "draft_whatsapp", "params": {"topic": "naye inquiry ka turant follow-up"}},
                {"type": "draft_email", "params": {"topic": "inquiry thank-you + next step"}},
            ],
            "enabled": False,
        },
        {
            "name": "Signup → welcome WhatsApp draft",
            "trigger": "signup",
            "condition": {},
            "actions": [
                {"type": "draft_whatsapp", "params": {"topic": "welcome + onboarding next step"}}
            ],
            "enabled": False,
        },
        {
            "name": "No-show → reschedule callback note",
            "trigger": "no_show",
            "condition": {},
            "actions": [
                {
                    "type": "schedule_callback",
                    "params": {"reason": "missed appointment reschedule"},
                },
                {"type": "draft_whatsapp", "params": {"topic": "missed call, reschedule offer"}},
            ],
            "enabled": False,
        },
    ]
    rows = []
    for d in defaults:
        rows.append(
            {
                "id": uuid.uuid4().hex[:12],
                "created_at": _now(),
                **d,
            }
        )
    _write_all(_JOURNEYS, rows)
    return len(rows)


def ensure_active_defaults() -> int:
    """JOURNEY_ENGINE=1 par kam se kam ek inquiry rule ON — warna emit empty loop.

    Pehle seed (disabled) jab store khali; phir inquiry rule enable ya naya add.
    Returns count enabled/added (0 ya 1). Kabhi raise nahi.

    IMPORTANT: sirf *kisi* enabled rule ka hona kaafi NAHI — enabled rule
    ``signup``/``manual`` ho to inquiry events ab bhi empty loop me marte.
    Check specifically for enabled ``inquiry_received``.
    """
    if not _enabled():
        return 0
    try:
        rules = list_journeys()
        if not rules:
            seed_defaults()
            rules = list_journeys()
        if any(r.get("enabled") and r.get("trigger") == "inquiry_received" for r in rules):
            return 0
        for r in rules:
            if r.get("trigger") == "inquiry_received":
                if set_enabled(str(r.get("id") or ""), True):
                    logger.info(
                        "[journeys] auto-enabled default inquiry rule (engine on, none active)"
                    )
                    return 1
        # Rules exist but no inquiry_received (custom-only store) — add one enabled.
        add_journey(
            name="Inquiry → WhatsApp + email follow-up draft",
            trigger="inquiry_received",
            actions=[
                {"type": "draft_whatsapp", "params": {"topic": "naye inquiry ka turant follow-up"}},
                {"type": "draft_email", "params": {"topic": "inquiry thank-you + next step"}},
            ],
            enabled=True,
        )
        logger.info("[journeys] added+enabled inquiry rule (no inquiry trigger in store)")
        return 1
    except Exception as e:
        logger.debug(f"[journeys] ensure_active_defaults skip: {e}")
        return 0


# --------------------------------------------------------------------------- #
# Action executors — sab ban-safe (draft/note). free-LLM se Hinglish drafts.
# --------------------------------------------------------------------------- #
async def _do_draft(channel: str, topic: str, context: dict[str, Any]) -> dict[str, Any]:
    who = context.get("business_name") or context.get("name") or "customer"
    try:
        from app.voice_agent import free_ai

        sys = (
            f"Tum ek polite Indian sales assistant ho. {channel} ke liye ek SHORT "
            "(2-3 line) Hinglish message likho. Sirf message, koi explanation nahi."
        )
        prompt = f"Kis ke liye: {who}. Topic: {topic}."
        msg, prov = await free_ai.chat(
            sys, [{"role": "user", "content": prompt}], max_tokens=160, temperature=0.7
        )
    except Exception as e:
        msg, prov = "", ""
        logger.debug(f"[journeys] draft llm skip: {e}")
    return {
        "channel": channel,
        "draft": msg or f"Namaste {who}! Aapse follow-up ke liye contact kar rahe hain.",
        "provider": prov,
        "auto_sent": False,  # ban-safe: human 1-click bhejega
    }


async def _run_action(action: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    t = action.get("type")
    p = action.get("params") or {}
    topic = str(p.get("topic") or p.get("reason") or "follow-up")
    if t == "draft_whatsapp":
        return {"action": t, **(await _do_draft("WhatsApp", topic, context))}
    if t == "draft_email":
        return {"action": t, **(await _do_draft("Email", topic, context))}
    if t == "schedule_callback":
        # ban-safe: sirf suggestion note (real call existing AUTO_CALLBACK path par hi).
        return {
            "action": t,
            "note": f"Callback suggested: {topic}",
            "phone": context.get("phone"),
            "auto_called": False,
        }
    if t == "notify":
        return {"action": t, "note": str(p.get("text") or "notify"), "to": p.get("to")}
    if t == "add_tag":
        return {"action": t, "tag": str(p.get("tag") or "")}
    if t == "request_review":
        # Sentiment-gated review request (review_engine) — draft/link (ban-safe).
        try:
            from app.marketing import review_engine

            r = await review_engine.request_review(
                business_name=context.get("business_name") or "Hamari team",
                customer_name=context.get("name") or "",
                customer_phone=context.get("phone") or "",
                sentiment_score=p.get("sentiment_score"),
            )
            return {
                "action": t,
                "channel": "Review",
                "gate": r.get("gate"),
                "draft": r.get("message"),
                "review_link": r.get("review_link"),
                "auto_sent": r.get("auto_sent"),
            }
        except Exception as e:
            return {"action": t, "error": str(e)[:120]}
    return {"action": t, "skipped": True}


def _matches(rule: dict[str, Any], event: str, context: dict[str, Any]) -> bool:
    if not rule.get("enabled"):
        return False
    if rule.get("trigger") != event:
        return False
    cond = rule.get("condition") or {}
    for k, v in cond.items():
        if str(context.get(k, "")).strip().lower() != str(v).strip().lower():
            return False
    return True


async def emit_event(event: str, context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Ek event fire karo → matching enabled rules ke actions chalao (drafts).

    GATED by JOURNEY_ENGINE=1 (default off = kuch nahi hota). Har run
    data/journey_runs.jsonl me log hota (1-click human send ke liye drafts).
    Kabhi raise nahi karta.
    """
    if not _enabled():
        return []
    ensure_active_defaults()
    ctx = context or {}
    runs: list[dict[str, Any]] = []
    try:
        for rule in list_journeys():
            if not _matches(rule, event, ctx):
                continue
            results = []
            for action in rule.get("actions", []):
                try:
                    results.append(await _run_action(action, ctx))
                except Exception as e:
                    logger.debug(f"[journeys] action fail: {e}")
            run = {
                "id": uuid.uuid4().hex[:12],
                "journey_id": rule.get("id"),
                "journey_name": rule.get("name"),
                "event": event,
                "context": {
                    k: ctx.get(k) for k in ("business_name", "name", "phone", "niche", "city")
                },
                "results": results,
                "at": _now(),
            }
            _append(_RUNS, run)
            runs.append(run)
            logger.info(f"[journeys] '{rule.get('name')}' ran on {event} ({len(results)} actions)")
    except Exception as e:
        logger.warning(f"[journeys] emit '{event}' failed: {e}")
    if runs:
        # Staff-visibility (2026-07-01): journey/rule automation fires from many real
        # hooks (inquiry, booking-reminder, reply-triage, pipeline-ops...) with zero
        # staff attribution today — invisible on /app/team. Attribute to "ira"
        # (Journey Automation Manager). Only logged when a rule actually matched
        # (not every emit_event no-op call) to avoid noise.
        try:
            from app.platform import team

            names = ", ".join(r.get("journey_name") or "?" for r in runs)
            team.log_event("ira", "journey_triggered", f"{event} → {names}")
        except Exception:
            pass
    return runs


__all__ = [
    "TRIGGERS",
    "ACTIONS",
    "list_journeys",
    "add_journey",
    "set_enabled",
    "delete_journey",
    "list_runs",
    "seed_defaults",
    "ensure_active_defaults",
    "emit_event",
]
