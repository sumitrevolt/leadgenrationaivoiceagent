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

# Bulk/marketing senders — unknown sender + inme se koi signal = junk skip.
_BULK_LOCALPARTS = {
    "noreply",
    "no-reply",
    "no_reply",
    "donotreply",
    "do-not-reply",
    "notifications",
    "notification",
    "notify",
    "alerts",
    "alert",
    "updates",
    "update",
    "newsletter",
    "newsletters",
    "marketing",
    "mailer",
    "bounce",
    "bounces",
    "postmaster",
    "mailer-daemon",
    "promo",
    "promotions",
    "offers",
    "billing",
    "receipts",
    "hello",
    "support",
    "info",
    "news",
    "team",
    "digest",
    "feedback",
    "survey",
}


def _is_bulk_sender(frm: str, msg: Any) -> bool:
    """Bulk/marketing mail detect — header signals + localpart. Never raises.

    NOTE: yeh SIRF unknown senders pe lagta hai (known prospect kabhi skip nahi
    hota, chahe support@ se hi reply kare).
    """
    try:
        local = (frm.split("@", 1)[0] if "@" in frm else frm).lower()
        if local in _BULK_LOCALPARTS:
            return True
        for h, val in (("List-Unsubscribe", None), ("Auto-Submitted", "no"), ("Precedence", None)):
            v = str(msg.get(h) or "").strip().lower()
            if h == "Auto-Submitted":
                if v and v != "no":
                    return True
            elif h == "Precedence":
                if v in ("bulk", "list", "junk"):
                    return True
            elif v:
                return True
    except Exception:
        pass
    return False


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
        host = (
            smtp_host.replace("smtp.", "imap.")
            if smtp_host.startswith("smtp.")
            else "imap.hostinger.com"
        )
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


def _load_feedback_examples(max_n: int = 8) -> str:
    """Recent feedback corrections -> few-shot examples for classifier (reduces 'other' rate)."""
    _FB = os.path.join("data", "reply_feedback.jsonl")
    if not os.path.exists(_FB):
        return ""
    examples = []
    try:
        with open(_FB, encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
        # Only corrections (old != correct)
        corrections = [r for r in rows if r.get("old_intent") != r.get("correct_intent")][-max_n:]
        for r in corrections:
            snip = str(r.get("body_snippet") or r.get("subject") or "")[:150]
            examples.append(f'  "{snip}" -> {r["correct_intent"]}')
    except Exception:
        pass
    if not examples:
        return ""
    return "\nRecent corrections (sikhne ke liye):\n" + "\n".join(examples)


async def _classify(subject: str, body: str) -> str:
    """Classify email reply intent. Uses few-shot feedback examples to reduce 'other' rate."""
    try:
        from app.voice_agent import free_ai

        examples = _load_feedback_examples()
        system = (
            "Tu ek AI email classifier hai. Reply email ka intent classify karo into EXACTLY one label:\n"
            "  interested  = prospect ne interest dikhaya, demo/meeting/pricing maanga\n"
            "  question    = specific sawal poocha (product/pricing/features ke baare me)\n"
            "  objection   = concern/pushback (pricing zyada, abhi nahi, try kar ke dekha)\n"
            "  not_interested = clearly mana kar diya\n"
            "  unsubscribe = unsubscribe/remove/stop chahta\n"
            "  ooo         = out of office auto-reply\n"
            "  other       = baaki sab (generic ack, spam, irrelevant)\n"
            + examples
            + "\nSIRF ek label reply karo, kuch aur nahi."
        )
        reply, _ = await free_ai.chat(
            system=system,
            messages=[{"role": "user", "content": f"Subject: {subject}\n\n{body[:1500]}"}],
            max_tokens=8,
            temperature=0.0,
        )
        lab = (reply or "").strip().lower()
        for c in _CATS:
            if c in lab:
                return c
    except Exception as exc:
        logger.debug("reply classify err: %s", exc)
    return "other"


async def _draft(
    biz: str, subject: str, body: str, intent: str, *, niche: str = "general"
) -> str:
    try:
        from app.voice_agent import free_ai

        objection_ctx = ""
        if intent in ("objection", "question", "not_interested"):
            try:
                from app.platform import objection_extractor

                hits = await objection_extractor.retrieve_rebuttals(
                    body or subject, niche=niche or "general", k=3
                )
                if hits:
                    objection_ctx = (
                        "\n\nObjection KB (use tone/angles, don't copy verbatim):\n"
                        + "\n".join(f"- {h}" for h in hits)
                    )
            except Exception:
                pass

        reply, _ = await free_ai.chat(
            system="Tu LeadGen AI ka helpful sales rep hai. Is reply ka chhota, warm, "
            "professional Hinglish jawab likh (max 4 lines). Free Google audit + demo offer "
            "kar; pushy mat ban. Objection ho to empathetic + specific jawab do. Sirf reply text de.",
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Business: {biz}\nNiche: {niche}\nIntent: {intent}\n"
                        f"Subject: {subject}\n\n{body[:1200]}{objection_ctx}"
                    ),
                }
            ],
            max_tokens=160,
            temperature=0.5,
        )
        reply = (reply or "").strip()
        if intent == "interested" and reply:
            vpa = os.environ.get("UPI_VPA", "").strip()
            if vpa:
                reply += (
                    "\n\nAage badhne ke liye pricing: https://leadsgenai.in/pricing"
                    f" - UPI se pay: {vpa}"
                )
        return reply
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
                p = pmap.get(frm)
                # JUNK GUARD (2026-06-12): unknown sender + bulk/marketing mail = skip.
                # Pehle PayU/Instamojo newsletters "interested" classify hoke FAKE deals
                # bana rahe the + har newsletter pe LLM classify/draft tokens jalte the.
                if p is None and _is_bulk_sender(frm, msg):
                    res["skipped"] += 1
                    continue
                body = _body(msg)
                intent = await _classify(subj, body)
                res["processed"] += 1
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
                    # Deliverability gate: unsubscribe-reply = recipient negative signal.
                    # Feed spam-complaint-rate tracker (auto-pauses at 0.25% over 7d).
                    try:
                        from app.platform import email_warmup

                        email_warmup.record_complaint(frm or "", "reply_unsubscribe")
                    except Exception:
                        pass
                elif intent in ("interested", "question"):
                    res["interested"] += 1
                    try:
                        from app.platform import revenue_attribution

                        revenue_attribution.record_touch(
                            client_id="",
                            channel="email_reply",
                            utm_source="reply_agent",
                            event=intent,
                            meta={"email": frm, "business": (p or {}).get("business_name")},
                        )
                    except Exception:
                        pass
                    # Phone push: HOT reply — sales moment, turant pata chale (gated ntfy).
                    try:
                        from app.integrations import ntfy

                        await ntfy.push(
                            "🔥 Hot reply!",
                            f"{(p or {}).get('business_name') or frm}: {subj[:80]}",
                            priority="high",
                            tags=["fire"],
                        )
                    except Exception:
                        pass
                    # Sales automation: interested reply -> deal — SIRF known prospect pe
                    # (unknown sender se junk deals bante the: PayU/Instamojo case).
                    if p:
                        try:
                            from app.marketing import sales_pipeline

                            sales_pipeline.upsert_deal(
                                {
                                    "business_name": p.get("business_name"),
                                    "email": frm,
                                    "phone": p.get("phone"),
                                    "niche": p.get("niche"),
                                },
                                stage="interested",
                            )
                        except Exception:
                            pass
                        # Cadence enroll: interested reply -> follow-up sequence (gated CADENCE_ENGINE)
                        try:
                            from app.marketing import cadence as _cadence

                            _cadence.enroll(
                                {
                                    "business_name": p.get("business_name") or "",
                                    "phone": p.get("phone") or "",
                                    "email": frm,
                                    "niche": p.get("niche") or "",
                                    "source": "reply_interested",
                                }
                            )
                        except Exception:
                            pass
                        # Journey: email_reply trigger (gated JOURNEY_ENGINE=1)
                        try:
                            from app.marketing import journeys

                            await journeys.emit_event(
                                "email_reply",
                                {
                                    "business_name": p.get("business_name") or "",
                                    "name": p.get("business_name") or "",
                                    "phone": p.get("phone") or "",
                                    "email": frm,
                                    "niche": p.get("niche") or "",
                                    "intent": intent,
                                },
                            )
                        except Exception:
                            pass

                draft = ""
                if intent in ("interested", "question", "objection"):
                    draft = await _draft(
                        (p or {}).get("business_name", ""),
                        subj,
                        body,
                        intent,
                        niche=str((p or {}).get("niche") or "general"),
                    )
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

                try:
                    from app.platform import interaction_log, objection_extractor

                    await interaction_log.record(
                        channel="email",
                        direction="in",
                        phone=(p or {}).get("phone") or "",
                        email=frm,
                        body_summary=(body or subj or "")[:200],
                        outcome=intent,
                        campaign_variant_id=str((p or {}).get("campaign_variant_id") or ""),
                    )
                    await objection_extractor.extract_from_reply(
                        body or subj or "",
                        niche=(p or {}).get("niche") or "general",
                        intent=intent,
                    )
                except Exception:
                    pass

                try:
                    vid = str((p or {}).get("campaign_variant_id") or "")
                    if vid:
                        from app.platform import campaign_variants

                        await campaign_variants.record_event(
                            vid,
                            reply=True,
                            meeting=intent in ("interested", "question"),
                        )
                        # A/B learning loop: record_reply closes send→reply cycle
                        try:
                            from app.marketing.outreach_variants import record_reply

                            record_reply(vid)
                        except Exception:
                            pass
                except Exception:
                    pass

                # REPLY_AUTO_SEND=1 → interested/question replies auto-send (Smartlead-style)
                # Only for known prospects (p is not None) — safety guard
                _auto_send = os.environ.get("REPLY_AUTO_SEND", "").strip() == "1"
                if _auto_send and draft and intent in ("interested", "question") and p is not None:
                    try:
                        from app.integrations.email_sender import EmailSender

                        sender = EmailSender()
                        re_subj = subj if subj.lower().startswith("re:") else f"Re: {subj}"
                        ok = await sender.send_email(
                            [frm],
                            re_subj,
                            draft,
                            html_body=f"<p>{draft.replace(chr(10), '<br>')}</p>",
                        )
                        if ok:
                            res["auto_sent"] = res.get("auto_sent", 0) + 1
                            logger.info(
                                "[reply_agent] auto-sent reply to %s (intent=%s)", frm, intent
                            )
                    except Exception as _ae:
                        logger.info("[reply_agent] auto_send failed: %s", _ae)

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
