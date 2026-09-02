"""Omnichannel Cadence Orchestrator — 2026 ka winning pattern.

Ek lead ko EK multi-channel sequence pe chalata: email → SMS → voice → LinkedIn →
WhatsApp, day-offset ke saath. Har step ban-safe **DRAFT/setup** deta (auto-send
sirf us channel ke apne gate pe: email AUTO_EMAIL_OUTREACH, SMS SMS_DLT_ENABLED,
WhatsApp opted-in only). Yahi "bahut saare approaches" ko EK system me baandhta hai.

GATED `CADENCE_ENGINE=1` (default off = kuch nahi). Reuse only: prospector.build_pitch,
sms_dlt, linkedin_assist (rebuild nahi). Store: data/cadence_leads.jsonl (per-lead
state) + data/cadence_runs.jsonl (step drafts, 1-click human send). Kabhi raise nahi.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _LEADS() -> str:
    """Cadence per-lead state — resolved per call, never frozen at import."""
    from app.platform import runtime_data_authority as _auth

    return str(
        _auth.resolve_store_path(
            store_id="automation.cadence_runs",
            legacy_path=Path("data") / "cadence_leads.jsonl",
            target_segments=("automation", "cadence_leads.jsonl"),
        )
    )


def _RUNS() -> str:
    """Cadence step-run drafts — sibling file under the same store family."""
    from app.platform import runtime_data_authority as _auth

    return str(
        _auth.resolve_store_path(
            store_id="automation.cadence_runs",
            legacy_path=Path("data") / "cadence_runs.jsonl",
            target_segments=("automation", "cadence_runs.jsonl"),
        )
    )


# The cadence (2026 multi-touch). day = enroll ke kitne din baad.
DEFAULT_CADENCE: list[dict[str, Any]] = [
    {"day": 0, "channel": "email", "action": "intro"},
    {"day": 0, "channel": "sms", "action": "intro"},
    {"day": 1, "channel": "whatsapp", "action": "intro"},
    {"day": 2, "channel": "voice", "action": "callback"},
    {"day": 3, "channel": "linkedin", "action": "connect"},
    {"day": 5, "channel": "sms", "action": "reminder"},
    {"day": 7, "channel": "email", "action": "breakup"},
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _enabled() -> bool:
    return os.environ.get("CADENCE_ENGINE", "0").strip().lower() in ("1", "true", "yes")


def _read(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return rows


def _write_all(path: str, rows: list[dict[str, Any]]) -> None:
    # Lock + atomic — web (API enroll) + celery (run_due) dono likhte hain.
    try:
        from app.utils.file_lock import locked_rewrite

        content = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        if not locked_rewrite(path, content):
            logger.warning(f"[cadence] locked write failed: {path}")
    except Exception as e:
        logger.warning(f"[cadence] write {path} failed: {e}")


def _append(path: str, rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def enroll(lead: dict[str, Any]) -> dict[str, Any]:
    """Ek lead ko cadence pe daalo (dedupe by phone/email). Kabhi raise nahi."""
    biz = (lead.get("business_name") or lead.get("name") or "Business").strip()
    phone = "".join(c for c in str(lead.get("phone") or "") if c.isdigit())[-10:]
    email = (lead.get("email") or "").strip().lower()
    # Resolver at each I/O site — binding to a local unbinds the allowlist (A3).
    rows = _read(_LEADS())
    for r in rows:
        if (phone and r.get("phone") == phone) or (email and r.get("email") == email):
            return r  # already enrolled
    rec = {
        "id": uuid.uuid4().hex[:12],
        "business_name": biz,
        "phone": phone,
        "email": email,
        "niche": (lead.get("niche") or "general"),
        "city": (lead.get("city") or ""),
        "step_idx": 0,
        "status": "active",
        "enrolled_at": _now().isoformat(),
    }
    rows.append(rec)
    _write_all(_LEADS(), rows)
    return rec


def enroll_many(leads: list[dict[str, Any]]) -> int:
    return sum(1 for ld in (leads or []) if enroll(ld))


async def _execute_step(rec: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
    """Ek channel-step chalao → draft/result. Ban-safe (auto-send channel-gate pe)."""
    ch, action = step["channel"], step["action"]
    biz, niche = rec["business_name"], rec["niche"]
    phone, city = rec.get("phone", ""), rec.get("city", "")
    out: dict[str, Any] = {"channel": ch, "action": action, "auto_sent": False}
    try:
        if ch == "email":
            out["draft"] = (
                f"[Email/{action}] {biz} — AI marketing + 2-min inquiry calling. Free audit: leadsgenai.in/audit"
            )
            out["note"] = "auto via AUTO_EMAIL_OUTREACH (Rohan)"
        elif ch == "sms":
            from app.integrations import sms_dlt

            msg = sms_dlt.render(action if action in sms_dlt.TEMPLATES else "intro", biz=biz)
            out["draft"] = msg
            if phone:
                res = await sms_dlt.send_template(
                    phone, action if action in sms_dlt.TEMPLATES else "intro", biz=biz
                )
                out["auto_sent"] = bool(res.get("ok"))
                out["sms"] = res
        elif ch == "whatsapp":
            import urllib.parse

            from app.platform import prospector

            try:
                pitch = prospector.build_pitch(biz, niche, city)
            except Exception:
                pitch = f"Namaste {biz}! LeadGen AI — AI se leads. Free audit: leadsgenai.in/audit"
            out["draft"] = pitch
            if phone:
                out["wa_link"] = (
                    "https://wa.me/91" + phone + "?text=" + urllib.parse.quote(pitch[:320])
                )
            out["note"] = "1-click human send (cold auto = ban)"
        elif ch == "voice":
            out["note"] = "AI callback queued (telephony+DLT live hone par auto)"
            out["draft"] = f"Voice: {biz} ko AI callback — qualify + demo + booking."
        elif ch == "linkedin":
            from app.marketing import linkedin_assist

            d = await linkedin_assist.draft_outreach(biz, biz, niche)
            out["draft"] = d.get("connect_note")
            out["linkedin"] = {k: d.get(k) for k in ("comment", "connect_note", "dm")}
            out["note"] = "manual send (ToS); comment-first"
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)[:120]
    return out


async def run_due(limit: int = 100) -> dict[str, Any]:
    """Due steps advance karo across enrolled leads. GATED CADENCE_ENGINE. Kabhi raise nahi.

    ``limit`` = max ACTIVE leads to examine (not file-prefix rows). Prod pe pehle
    ~100 ``done`` rows file ke top pe baithe the → ``rows[:limit]`` sirf unhe
    dekhta tha aur 7k+ active leads starve ho rahe the (Anika idle).
    """
    if not _enabled():
        return {"ok": False, "reason": "CADENCE_ENGINE off"}
    rows = _read(_LEADS())
    advanced = 0
    examined_active = 0
    for rec in rows:
        if examined_active >= limit:
            break
        if rec.get("status") != "active":
            continue
        examined_active += 1
        try:
            enrolled = datetime.fromisoformat(str(rec["enrolled_at"]).replace("Z", "+00:00"))
        except Exception:
            continue
        days = (_now() - enrolled).total_seconds() / 86400.0
        idx = int(rec.get("step_idx", 0))
        progressed = False
        while idx < len(DEFAULT_CADENCE) and DEFAULT_CADENCE[idx]["day"] <= days:
            step = DEFAULT_CADENCE[idx]
            res = await _execute_step(rec, step)
            _append(
                _RUNS(),
                {
                    "lead_id": rec["id"],
                    "business_name": rec["business_name"],
                    "step": idx,
                    **res,
                    "at": _now().isoformat(),
                },
            )
            idx += 1
            progressed = True
        if progressed:
            rec["step_idx"] = idx
            if idx >= len(DEFAULT_CADENCE):
                rec["status"] = "done"
            advanced += 1
    if advanced:
        _write_all(_LEADS(), rows)
    active = sum(1 for r in rows if r.get("status") == "active")
    if advanced:
        # Staff-visibility (2026-07-01): omnichannel cadence runs on a schedule
        # (team_scheduler.py) with zero staff attribution today — invisible on
        # /app/team. Attribute to "anika" (Cadence Manager).
        try:
            from app.platform import team

            team.log_event(
                "anika",
                "cadence_advanced",
                f"{advanced} leads progressed, {active} active in sequence",
            )
        except Exception:
            pass
    return {
        "ok": True,
        "advanced": advanced,
        "active": active,
        "total": len(rows),
        "examined_active": examined_active,
    }


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    return list(reversed(_read(_RUNS())))[:limit]


def stats() -> dict[str, Any]:
    rows = _read(_LEADS())
    # Apollo-style per-step analytics: har channel/action pe kitne touches gaye
    # (sequence ka kaunsa step kitna chala — drop-off saaf dikhta).
    step_counts: dict[str, int] = {}
    try:
        for r in _read(_RUNS()):
            key = f"{r.get('channel', '?')}:{r.get('action', '?')}"
            step_counts[key] = step_counts.get(key, 0) + 1
    except Exception:
        pass
    return {
        "enrolled": len(rows),
        "active": sum(1 for r in rows if r.get("status") == "active"),
        "done": sum(1 for r in rows if r.get("status") == "done"),
        "cadence_steps": len(DEFAULT_CADENCE),
        "engine_on": _enabled(),
        "step_touches": step_counts,
    }


__all__ = ["DEFAULT_CADENCE", "enroll", "enroll_many", "run_due", "list_runs", "stats"]
