"""WhatsApp campaign push engine — templates, suppression, drip + reactivation runner.

This is the background "send engine" behind the official Cloud API sender
(:mod:`app.marketing.whatsapp_campaign`). It is the WhatsApp analogue of the
content scheduler's ``run_due()`` pattern.

Pieces
------
1. **Template store** (``data/wa_templates.jsonl``) — register / list / update-status of
   Meta message templates. Meta approves templates server-side; we only track
   name / language / category / body / status so the panel + runner know which
   approved templates exist. Only ``status="approved"`` templates are auto-sent.
2. **Suppression list** (``data/wa_suppression.jsonl``) — opt-out / blocked / repeatedly
   failing numbers. ``is_suppressed`` short-circuits every send; ``record_failure``
   auto-suppresses a number after N failures (bounce/block protection).
3. **Campaign queue** (``data/wa_campaigns.jsonl``) — drip + reactivation jobs scheduled
   for a date, prepared/sent by :func:`run_due` (scheduler calls it hourly).

SAFETY (obey exactly): default behaviour is ban-safe 1-click links. Auto TEMPLATE
sends happen ONLY when ``WHATSAPP_AUTO_SEND=1`` AND official creds are present AND the
template is approved AND the number is opted-in + not suppressed. Spaced + daily-capped.
Never uses an unofficial gateway. Never raises.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import date, datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_TEMPLATES_FILE = os.path.join("data", "wa_templates.jsonl")
_CAMPAIGN_FILE = os.path.join("data", "wa_campaigns.jsonl")


def _suppression_path() -> str:
    """WhatsApp suppression ledger — resolved per call, never at import.

    A module-level constant freezes the path when this module is first imported,
    which is exactly what makes a store impossible to move (and impossible to
    redirect from a fixture that runs later). This is a Tier-0 compliance
    authority: opting a number back in by accident is a TCCCPR problem, not a
    tidiness problem.

    Returns `str` because every caller here passes it straight to the module's
    own `_read`/`_append`/`_write_all` helpers, which have always taken strings.
    """
    from pathlib import Path

    from app.platform import runtime_data_authority as _auth

    return str(
        _auth.resolve_store_path(
            store_id="compliance.wa_suppression",
            legacy_path=Path("data") / "wa_suppression.jsonl",
            target_segments=("compliance", "wa_suppression.jsonl"),
        )
    )


# Auto-suppress a number after this many recorded delivery failures.
_FAIL_SUPPRESS_THRESHOLD = 3


# --------------------------------------------------------------------------- #
# tiny jsonl helpers (mirror content_schedule.py)
# --------------------------------------------------------------------------- #
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: str) -> list[dict]:
    out: list[dict] = []
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            out.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return out


def _write_all(path: str, items: list[dict]) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.info("wa runner write err (%s): %s", path, e)


def _append(path: str, item: dict) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.info("wa runner append err (%s): %s", path, e)


def _digits(phone: str | None) -> str:
    """Normalize to E.164-ish digits (India 10-digit -> 91XXXXXXXXXX)."""
    d = "".join(c for c in str(phone or "") if c.isdigit())
    if len(d) == 10:
        d = "91" + d
    elif d.startswith("0") and len(d) == 11:
        d = "91" + d[1:]
    return d


# --------------------------------------------------------------------------- #
# Template store
# --------------------------------------------------------------------------- #
_TEMPLATE_CATEGORIES = {"MARKETING", "UTILITY", "AUTHENTICATION"}
_TEMPLATE_STATUSES = {"draft", "pending", "approved", "rejected", "paused", "disabled"}


def register_template(
    name: str,
    body: str = "",
    language: str = "en",
    category: str = "MARKETING",
    status: str = "pending",
    example_params: list[str] | None = None,
) -> dict[str, Any]:
    """Register / upsert a Meta template record (by name+language). Returns the record.

    NOTE: this does NOT create the template on Meta — templates are submitted &
    approved in WhatsApp Manager / via the Business Management API. This is a local
    mirror so the panel + runner know which approved templates exist.
    """
    name = (name or "").strip()
    language = (language or "en").strip() or "en"
    if not name:
        return {"error": "name_required"}
    cat = (category or "MARKETING").strip().upper()
    if cat not in _TEMPLATE_CATEGORIES:
        cat = "MARKETING"
    st = (status or "pending").strip().lower()
    if st not in _TEMPLATE_STATUSES:
        st = "pending"
    items = _read(_TEMPLATES_FILE)
    rec = None
    for it in items:
        if it.get("name") == name and it.get("language") == language:
            rec = it
            break
    if rec is None:
        rec = {"id": uuid.uuid4().hex[:8], "created_at": _now()}
        items.append(rec)
    rec.update(
        {
            "name": name,
            "language": language,
            "category": cat,
            "body": (body or "").strip(),
            "status": st,
            "example_params": [str(p) for p in (example_params or [])],
            "updated_at": _now(),
        }
    )
    _write_all(_TEMPLATES_FILE, items)
    return rec


def list_templates(status: str | None = None) -> list[dict]:
    items = _read(_TEMPLATES_FILE)
    if status:
        items = [i for i in items if i.get("status") == status.strip().lower()]
    items.sort(key=lambda i: (i.get("status") != "approved", i.get("name", "")))
    return items


def get_template(name: str, language: str = "en") -> dict | None:
    for it in _read(_TEMPLATES_FILE):
        if (
            it.get("name") == (name or "").strip()
            and it.get("language") == (language or "en").strip()
        ):
            return it
    return None


def update_template_status(name: str, status: str, language: str = "en") -> bool:
    """Track Meta's approval decision locally (approved/rejected/paused/…)."""
    st = (status or "").strip().lower()
    if st not in _TEMPLATE_STATUSES:
        return False
    items = _read(_TEMPLATES_FILE)
    hit = False
    for it in items:
        if it.get("name") == (name or "").strip() and (
            not language or it.get("language") == language.strip()
        ):
            it["status"] = st
            it["updated_at"] = _now()
            hit = True
    if hit:
        _write_all(_TEMPLATES_FILE, items)
    return hit


def template_is_approved(name: str, language: str = "en") -> bool:
    t = get_template(name, language)
    return bool(t and t.get("status") == "approved")


# --------------------------------------------------------------------------- #
# Suppression list (opt-out / blocked / bounced)
# --------------------------------------------------------------------------- #
def is_suppressed(phone: str) -> bool:
    """True if this number must not be messaged.

    Returns True when the suppression store cannot be RESOLVED. The caller is
    about to decide whether to send; without a trustworthy opt-out list the only
    safe answer is "do not". A missing or empty file still reads as
    not-suppressed — that is an answer, not an outage.
    """
    d = _digits(phone)
    if not d:
        return False
    try:
        _suppression_path()
    except Exception as exc:  # noqa: BLE001 — any resolution failure is the same verdict
        logger.error("compliance.wa_suppression authority UNRESOLVABLE: %s", exc)
        return True
    for it in _read(_suppression_path()):
        if it.get("phone") == d:
            return True
    return False


def suppress(phone: str, reason: str = "opt_out") -> dict[str, Any]:
    """Add a number to the suppression list (won't be auto-messaged again)."""
    d = _digits(phone)
    if not d:
        return {"error": "bad_phone"}
    # Guard first, then resolve at the call site — see consent_ledger.record_opt_out
    # for why the resolver expression is kept visible to the path scanner.
    try:
        _suppression_path()
    except Exception as exc:  # noqa: BLE001
        logger.error("wa suppress FAILED (authority unresolvable) for ***%s: %s", d[-4:], exc)
        return {"phone": d, "suppressed": False, "error": "suppression_authority_unavailable"}
    if not is_suppressed(d):
        _append(
            _suppression_path(),
            {"phone": d, "reason": (reason or "opt_out")[:60], "at": _now()},
        )
    return {"phone": d, "suppressed": True, "reason": reason}


def unsuppress(phone: str) -> bool:
    d = _digits(phone)
    if not d:
        return False
    items = _read(_suppression_path())
    keep = [i for i in items if i.get("phone") != d]
    if len(keep) != len(items):
        _write_all(_suppression_path(), keep)
        return True
    return False


def list_suppressed(limit: int = 500) -> list[dict]:
    return _read(_suppression_path())[-limit:][::-1]


def record_failure(phone: str, reason: str = "send_failed") -> None:
    """Record a delivery failure; auto-suppress after repeated failures (bounce protection)."""
    d = _digits(phone)
    if not d:
        return
    _append(
        os.path.join("data", "wa_failures.jsonl"),
        {"phone": d, "reason": (reason or "")[:120], "at": _now()},
    )
    try:
        fails = [f for f in _read(os.path.join("data", "wa_failures.jsonl")) if f.get("phone") == d]
        if len(fails) >= _FAIL_SUPPRESS_THRESHOLD and not is_suppressed(d):
            suppress(d, reason="auto_failures")
            logger.info("wa: auto-suppressed %s after %d failures", d, len(fails))
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Recipient resolution — opted-in numbers only
# --------------------------------------------------------------------------- #
def _opted_in(phone: str) -> bool:
    """A number is sendable only if it has digits and is NOT suppressed.

    (Opt-in itself is captured upstream — inquiry forms, customers who messaged us,
    explicit consent. Suppression encodes opt-out/block. We never cold-blast.)
    """
    return bool(_digits(phone)) and not is_suppressed(phone)


def _client_customers(client_id: str, max_n: int = 500) -> list[dict]:
    """Best-effort: a client's opted-in customers (phone + name) from crm_lite."""
    out: list[dict] = []
    try:
        from app.marketing import crm_lite

        rows = crm_lite.list_customers(client_id)  # type: ignore[attr-defined]
        for r in rows or []:
            ph = r.get("phone") if isinstance(r, dict) else None
            if ph and _opted_in(ph):
                out.append({"phone": _digits(ph), "name": (r.get("name") or "").strip()})
            if len(out) >= max_n:
                break
    except Exception as e:
        logger.debug("client_customers err: %s", e)
    return out


# --------------------------------------------------------------------------- #
# Campaign queue (drip / reactivation) — scheduled jobs
# --------------------------------------------------------------------------- #
_CAMPAIGN_KINDS = {"drip", "reactivation", "broadcast"}


def schedule_campaign(
    kind: str,
    template_name: str,
    business_name: str = "",
    client_id: str = "",
    language: str = "en",
    date_iso: str = "",
    recipients: list[dict] | None = None,
    params: list[str] | None = None,
    note: str = "",
) -> dict[str, Any]:
    """Queue a WhatsApp campaign for a date. Sent by :func:`run_due` when due.

    recipients = [{"phone","name"?}]; if empty + client_id given, the client's
    opted-in customers are resolved at run time.
    """
    k = (kind or "").strip().lower()
    if k not in _CAMPAIGN_KINDS:
        k = "drip"
    item = {
        "id": uuid.uuid4().hex[:8],
        "kind": k,
        "template_name": (template_name or "").strip(),
        "language": (language or "en").strip() or "en",
        "business_name": (business_name or "").strip(),
        "client_id": (client_id or "").strip(),
        "date": (date_iso or date.today().isoformat()).strip()[:10],
        "recipients": [
            {"phone": _digits(r.get("phone")), "name": (r.get("name") or "").strip()}
            for r in (recipients or [])
            if isinstance(r, dict) and _digits(r.get("phone"))
        ],
        "params": [str(p) for p in (params or [])],
        "note": (note or "").strip(),
        "status": "scheduled",
        "result": None,
        "created_at": _now(),
    }
    _append(_CAMPAIGN_FILE, item)
    return item


def list_campaigns(status: str | None = None, limit: int = 200) -> list[dict]:
    items = _read(_CAMPAIGN_FILE)
    if status:
        items = [i for i in items if i.get("status") == status]
    items.sort(key=lambda i: i.get("date", ""))
    return items[:limit]


def mark_campaign(campaign_id: str, status: str) -> bool:
    items = _read(_CAMPAIGN_FILE)
    hit = False
    for i in items:
        if i.get("id") == campaign_id:
            i["status"] = status
            hit = True
    if hit:
        _write_all(_CAMPAIGN_FILE, items)
    return hit


async def _send_campaign_item(item: dict) -> dict[str, Any]:
    """Send one queued campaign's approved-template messages to opted-in recipients.

    Spaced + daily-capped + suppression-aware via whatsapp_campaign.send_template.
    """
    from app.marketing import whatsapp_campaign as wac

    tmpl = item.get("template_name", "")
    lang = item.get("language", "en")
    summary = {
        "id": item.get("id"),
        "kind": item.get("kind"),
        "template": tmpl,
        "sent": 0,
        "links": 0,
        "skipped": 0,
        "recipients": 0,
        "live": wac.auto_ready(),
    }

    # resolve recipients (explicit, else client customers)
    recips = item.get("recipients") or []
    if not recips and item.get("client_id"):
        recips = _client_customers(item["client_id"])
    recips = [r for r in recips if _opted_in(r.get("phone"))]
    summary["recipients"] = len(recips)

    live = wac.auto_ready()
    # Only auto-send if the template is locally tracked as APPROVED.
    if live and not template_is_approved(tmpl, lang):
        summary["skipped"] = len(recips)
        summary["reason"] = "template_not_approved"
        return summary

    import asyncio

    fallback = item.get("note") or f"{item.get('business_name', '')} update"
    cap = wac.daily_cap()
    sent_today = wac.sent_today_count() if live else 0
    delay = wac.send_spacing_s()
    for i, r in enumerate(recips):
        if live and sent_today >= cap:
            summary["skipped"] += 1
            continue
        # per-recipient params: {{1}} defaults to the customer name when not provided
        params = item.get("params") or ([r.get("name")] if r.get("name") else [])
        res = await wac.send_template(
            r.get("phone", ""), tmpl, params=params, language=lang, fallback_text=fallback
        )
        if res.get("sent"):
            summary["sent"] += 1
            sent_today += 1
            wac._bump_sent_today()  # persist GLOBAL daily counter — else template sends bypass the ban-safety cap across campaigns/runs
        elif res.get("mode") == "suppressed":
            summary["skipped"] += 1
        else:
            summary["links"] += 1
        if live and res.get("sent") and i < len(recips) - 1:
            await asyncio.sleep(delay)
    return summary


async def run_due(limit: int = 20) -> dict[str, Any]:
    """Send campaigns due today or earlier (status=scheduled). Scheduler calls hourly.

    Mirrors content_schedule.run_due(). Never raises. When auto-send is OFF/unconfigured
    it still "prepares" (marks ready, surfaces 1-click link counts) but sends nothing.
    """
    res = {"due": 0, "processed": 0, "sent": 0, "links": 0, "skipped": 0}
    try:
        from app.marketing import whatsapp_campaign as wac

        today = date.today().isoformat()
        items = _read(_CAMPAIGN_FILE)
        due = [i for i in items if i.get("status") == "scheduled" and (i.get("date", "") <= today)]
        res["due"] = len(due)
        res["auto"] = wac.auto_ready()
        if not due:
            return res
        for it in due[: max(1, limit)]:
            try:
                summary = await _send_campaign_item(it)
                it["result"] = summary
                it["status"] = "sent" if wac.auto_ready() else "ready"
                it["ran_at"] = _now()
                res["processed"] += 1
                res["sent"] += summary.get("sent", 0)
                res["links"] += summary.get("links", 0)
                res["skipped"] += summary.get("skipped", 0)
            except Exception as e:
                logger.info("wa campaign item err: %s", e)
        _write_all(_CAMPAIGN_FILE, items)
        try:
            from app.platform.team import log_event

            mode = "auto-sent" if wac.auto_ready() else "prepared (1-click links)"
            log_event(
                "isha",
                "wa_campaign_run",
                f"{res['processed']} campaigns {mode}: {res['sent']} sent",
            )
        except Exception:
            pass
        return res
    except Exception as e:
        logger.info("wa run_due err: %s", e)
        return res


__all__ = [
    # templates
    "register_template",
    "list_templates",
    "get_template",
    "update_template_status",
    "template_is_approved",
    # suppression
    "is_suppressed",
    "suppress",
    "unsuppress",
    "list_suppressed",
    "record_failure",
    # campaigns
    "schedule_campaign",
    "list_campaigns",
    "mark_campaign",
    "run_due",
]
