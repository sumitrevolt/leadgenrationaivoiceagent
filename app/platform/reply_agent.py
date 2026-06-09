"""AI reply handling — closes the outreach loop (send → RECEIVE → classify → act).

THE missing automation: cold emails go out daily, but replies sat unread. Every AI
SDR platform's headline feature (Smartlead SmartAgents, 11x, Instantly unibox) is
exactly this — read replies, classify intent, surface hot leads in minutes. Fully
self-hosted on our stack: Hostinger IMAP + free_ai (classify/draft) + prospector store.

Per reply it: classifies intent (interested/question/objection/not_interested/
unsubscribe/ooo/other), updates the matching prospect's status (interested→hot,
unsubscribe→dead), drafts a contextual Hinglish reply, saves it for 1-click human send,
and logs a team event so Rohan/Swara surface it.

OFF by default + never-crash. Enable: `REPLY_AGENT=1` + SMTP/IMAP creds present
(reuses the SMTP login). Auto-send is OFF (ban-safe, 1-click human send) EXCEPT
unsubscribe which is always honoured. `IMAP_HOST` overrides (default derived from SMTP).
"""

from __future__ import annotations

import email
import email.utils
import imaplib
import json
import logging
import os
from datetime import datetime, timezone
from email.header import decode_header
from typing import Any

logger = logging.getLogger(__name__)

_CATS = ["interested", "question", "objection", "not_interested", "unsubscribe", "ooo", "other"]
# intent -> prospect status
_STATUS = {
    "interested": "replied_hot",
    "question": "replied_hot",
    "objection": "replied",
    "not_interested": "dead",
    "unsubscribe": "dead",
    "ooo": "ready",
    "other": "replied",
}
_DRAFTS_FILE = os.path.join("data", "reply_drafts.jsonl")


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _creds() -> tuple[str, str, str]:
    """(imap_host, user, password) reusing SMTP login. ('','','') if unconfigured."""
    user = pw = host = ""
    try:
        from app.config import settings

        user = (getattr(settings, "smtp_user", "") or "").strip()
        pw = (getattr(settings, "smtp_password", "") or "").strip()
        smtp_host = (getattr(settings, "smtp_host", "") or "").strip()
    except Exception:
        smtp_host = ""
    user = user or os.getenv("SMTP_USER", "").strip()
    pw = pw or os.getenv("SMTP_PASSWORD", "").strip()
    host = os.getenv("IMAP_HOST", "").strip()
    if not host:
        host = smtp_host.replace("smtp.", "imap.") if smtp_host.startswith("smtp.") else "imap.hostinger.com"
    return host, user, pw


def _decode(raw: str) -> str:
    try:
        parts = decode_header(raw or "")
        out = ""
        for txt, enc in parts:
            out += txt.decode(enc or "utf-8", "ignore") if isinstance(txt, bytes) else txt
        return out.strip()
    except Exception:
        return (raw or "").strip()


def _body(msg) -> str:
    try:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain" and "attachment" not in str(
                    part.get("Content-Disposition", "")
                ):
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode(part.get_content_charset() or "utf-8", "ignore")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode(msg.get_content_charset() or "utf-8", "ignore")
    except Exception:
        pass
    return ""


async def _classify(subject: str, body: str) -> str:
    try:
        from app.voice_agent import free_ai

        reply, _ = await free_ai.chat(
            system="Classify the email reply into EXACTLY one label: "
            + ", ".join(_CATS)
            + ". Reply with ONLY the label.",
            messages=[{"role": "user", "content": f"Subject: {subject}\n\n{body[:1500]}"}],
            max_tokens=4,
            temperature=0.0,
        )
        lab = (reply or "").strip().lower()
        for c in _CATS:
            if c in lab:
                return c
    except Exception as exc:
        logger.debug("reply classify err: %s", exc)
    return "other"


async def _draft(biz: str, subject: str, body: str, intent: str) -> str:
    try:
        from app.voice_agent import free_ai

        reply, _ = await free_ai.chat(
            system="Tu LeadGen AI ka helpful sales rep hai. Is reply ka chhota, warm, "
            "professional Hinglish jawab likh (max 4 lines). Free Google audit + demo offer "
            "kar; pushy mat ban. Sirf reply text de.",
            messages=[{"role": "user", "content": f"Business: {biz}\nIntent: {intent}\nSubject: {subject}\n\n{body[:1200]}"}],
            max_tokens=160,
            temperature=0.5,
        )
        return (reply or "").strip()
    except Exception:
        return ""


def _save_draft(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_DRAFTS_FILE), exist_ok=True)
        with open(_DRAFTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.debug("save_draft err: %s", exc)


def _notify(member: str, kind: str, detail: str) -> None:
    try:
        from app.platform.team import log_event

        log_event(member, kind, detail)
    except Exception:
        pass


def _prospect_map() -> dict[str, dict]:
    out: dict[str, dict] = {}
    try:
        from app.platform import prospector

        for p in prospector.list_prospects(status=None, limit=2000):
            e = str(p.get("email") or "").strip().lower()
            if e:
                out[e] = p
    except Exception as exc:
        logger.debug("prospect_map err: %s", exc)
    return out


async def run_reply_triage(limit: int = 40) -> dict[str, Any]:
    """Read UNSEEN inbox replies, classify, update prospects, draft + notify. Never raises."""
    res = {"processed": 0, "interested": 0, "unsubscribed": 0, "drafted": 0, "skipped": 0}
    if not _flag("REPLY_AGENT"):
        return {"skipped": "REPLY_AGENT off"}
    host, user, pw = _creds()
    if not (host and user and pw):
        return {"skipped": "imap_unconfigured"}
    try:
        M = imaplib.IMAP4_SSL(host, 993)
        M.login(user, pw)
        M.select("INBOX")
        typ, data = M.search(None, "UNSEEN")
        ids = (data[0].split() if data and data[0] else [])[: max(1, limit)]
        pmap = _prospect_map()
        for i in ids:
            try:
                typ, md = M.fetch(i, "(RFC822)")
                msg = email.message_from_bytes(md[0][1])
                frm = email.utils.parseaddr(msg.get("From", ""))[1].lower()
                subj = _decode(msg.get("Subject", ""))
                body = _body(msg)
                intent = await _classify(subj, body)
                res["processed"] += 1

                p = pmap.get(frm)
                pid = (p or {}).get("id") or (p or {}).get("pid")
                if pid:
                    try:
                        from app.platform import prospector

                        prospector.mark_prospect(pid, _STATUS.get(intent, "replied"))
                        prospector.set_prospect_fields(
                            pid,
                            {
                                "reply_intent": intent,
                                "reply_subject": subj,
                                "replied_at": datetime.now(timezone.utc).isoformat(),
                            },
                        )
                    except Exception:
                        pass

                if intent == "unsubscribe":
                    res["unsubscribed"] += 1
                elif intent in ("interested", "question"):
                    res["interested"] += 1
                    # Sales automation: interested reply -> deal (pipeline auto next-action).
                    try:
                        from app.marketing import sales_pipeline

                        sales_pipeline.upsert_deal(
                            {"business_name": (p or {}).get("business_name"), "email": frm,
                             "phone": (p or {}).get("phone"), "niche": (p or {}).get("niche")},
                            stage="interested",
                        )
                    except Exception:
                        pass

                draft = ""
                if intent in ("interested", "question", "objection"):
                    draft = await _draft((p or {}).get("business_name", ""), subj, body, intent)
                    if draft:
                        res["drafted"] += 1

                _save_draft(
                    {
                        "from": frm,
                        "subject": subj,
                        "intent": intent,
                        "draft": draft,
                        "at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                member = "swara" if intent in ("interested", "question") else "rohan"
                _notify(member, f"reply_{intent}", f"{frm}: {subj[:60]}")
            except Exception as exc:
                logger.info("reply item err: %s", exc)
                res["skipped"] += 1
        try:
            M.close()
            M.logout()
        except Exception:
            pass
        return res
    except Exception as exc:
        logger.info("run_reply_triage err: %s", exc)
        return {"error": str(exc), **res}


async def whatsapp_reply(
    from_number: str,
    text: str,
    message_id: str = "",
    business_name: str = "",
) -> dict[str, Any]:
    """Classify an inbound WhatsApp message + draft a Hinglish reply (1-click human send).

    Same brain as the email triage (free_ai classify + draft) but adapted for chat:
    no subject, body = the message text. Writes a draft to ``reply_drafts.jsonl`` with
    ``channel="whatsapp"`` and notifies the team. NEVER raises; returns the saved record
    (``{}`` on empty text). Auto-send OFF (ban-safe) — human sends in 1 click.
    """
    txt = (text or "").strip()
    frm = (from_number or "").strip()
    if not txt:
        return {}
    try:
        intent = await _classify("WhatsApp inbound", txt)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("wa classify err: %s", exc)
        intent = "other"
    draft = ""
    if intent in ("interested", "question", "objection"):
        try:
            draft = await _draft(business_name or "", "WhatsApp inquiry", txt, intent)
        except Exception:  # pragma: no cover - defensive
            draft = ""
    rec = {
        "channel": "whatsapp",
        "from": frm,
        "message_id": (message_id or "").strip(),
        "text": txt[:2000],
        "intent": intent,
        "draft": draft,
        "status": _STATUS.get(intent, "replied"),
        "at": datetime.now(timezone.utc).isoformat(),
    }
    _save_draft(rec)
    member = "swara" if intent in ("interested", "question") else "rohan"
    _notify(member, f"wa_reply_{intent}", f"{frm}: {txt[:60]}")
    return rec


def list_drafts(limit: int = 50) -> list[dict]:
    """Recent reply drafts for the dashboard (1-click human send)."""
    out: list[dict] = []
    try:
        if os.path.exists(_DRAFTS_FILE):
            with open(_DRAFTS_FILE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            out.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return out[-limit:][::-1]


__all__ = ["run_reply_triage", "whatsapp_reply", "list_drafts"]
