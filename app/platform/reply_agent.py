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
import re
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


_BOUNCE_LOCALPARTS = {"mailer-daemon", "postmaster", "bounce", "bounces"}
_BOUNCE_SUBJECT_RE = re.compile(
    r"undeliver|delivery status notification|delivery has failed|"
    r"returned mail|mail delivery failed|failure notice|"
    r"delivery.{0,10}fail|couldn.t be delivered|permanent.{0,10}error",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _is_bounce_message(frm: str, msg: Any, subj: str) -> bool:
    """Detect bounce/NDR (Non-Delivery-Report) mail. GAP THIS CLOSES: bounce mail
    was previously caught by `_is_bulk_sender` (mailer-daemon/postmaster are junk
    localparts) and silently skipped — so `email_warmup.record_bounce()` was NEVER
    called automatically, meaning bounce_rate_7d always read ~0% no matter how many
    real bounces happened, warmup ramp kept climbing on a false-healthy signal, and
    the outreach_quality funnel (0 replies / 1875 sends) had zero visibility into
    whether mail was actually landing. Never raises."""
    try:
        local = (frm.split("@", 1)[0] if "@" in frm else frm).lower()
        if local in _BOUNCE_LOCALPARTS:
            return True
        ctype = str(msg.get_content_type() or "").lower()
        if "report" in ctype and "delivery-status" in str(msg.get_payload() or "").lower()[:2000]:
            return True
        if _BOUNCE_SUBJECT_RE.search(subj or ""):
            return True
    except Exception:
        pass
    return False


def _extract_bounced_email(body: str, subj: str, pmap: dict) -> str:
    """Bounce body/subject se ORIGINAL recipient (jo bounce hua) nikalo — jo bhi
    embedded email hamare known-prospect pool (pmap) se match kare wahi lo (bounce
    reports me apna hi mailbox bhi mention hota hai, isliye blind first-match nahi,
    pmap-membership match). Never raises."""
    try:
        for m in _EMAIL_RE.findall(f"{subj}\n{body}"):
            e = m.lower()
            if e in pmap:
                return e
    except Exception:
        pass
    return ""


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


# AUTO-ACK GUARD (2026-07-07): "Thank you for your interest in X" / "We have
# received your enquiry" type auto-acknowledgements were LLM-classifying as
# "interested" and flooding reply_drafts + Hot Queue with fake-hot rows (312
# rows from ONE adityabirla.com auto-responder alone — deliverability audit).
# _is_bulk_sender can't catch these: it only runs for UNKNOWN senders (known
# prospects bypass it) and many auto-acks carry no bulk headers. This guard
# runs for EVERYONE — an auto-ack is not a human reply regardless of sender.
_AUTO_ACK_RE = re.compile(
    r"thank(s| you) for (your (interest|enquiry|inquiry|email|message)|contacting|reaching out|writing)|"
    r"we (have )?received your|your (enquiry|inquiry|request|message) (has been|was) received|"
    r"auto[- ]?(reply|response|acknowledg)|automatic reply|acknowledge?ment",
    re.IGNORECASE,
)


def _is_auto_ack(msg: Any, subj: str) -> bool:
    """Auto-acknowledgement detect (subject pattern ya Auto-Submitted header).
    Known-prospect pe BHI lagta — auto-ack kisi se bhi aaye, human reply nahi.
    Never raises."""
    try:
        if _AUTO_ACK_RE.search(subj or ""):
            return True
        v = str((msg.get("Auto-Submitted") if msg is not None else "") or "").strip().lower()
        if v and v != "no":
            return True
    except Exception:
        pass
    return False


# SENDER FLOOD CAP (2026-07-07): ek hi sender se repeat-mail cap — auto-responder
# ping-pong (312x adityabirla loop) har mail pe LLM classify+draft tokens jalata
# tha aur drafts/Hot-Queue ko noise se bhar deta tha. Cap ke baad wale skip
# (pehli `cap` rows hot queue me surface ho hi chuki hoti hain; genuine engaged
# prospect ke liye cap kaafi upar hai). REPLY_SENDER_FLOOD_CAP=0 disables.
def _flood_cap() -> int:
    try:
        return max(0, int(os.getenv("REPLY_SENDER_FLOOD_CAP", "6") or 6))
    except Exception:
        return 6


def _sender_counts(rows: list[dict]) -> dict[str, int]:
    """Recent draft rows -> per-sender row count (flood detect). Never raises."""
    out: dict[str, int] = {}
    try:
        for r in rows:
            f = str((r or {}).get("from") or "").strip().lower()
            if f:
                out[f] = out.get(f, 0) + 1
    except Exception:
        pass
    return out


def _is_blocklisted(frm: str) -> bool:
    """Operator blocklist: REPLY_SENDER_BLOCKLIST env (CSV — full address ya
    domain). Unset = koi block nahi. Never raises."""
    try:
        raw = os.getenv("REPLY_SENDER_BLOCKLIST", "") or ""
        bl = {t.strip().lower() for t in raw.split(",") if t.strip()}
        if not bl:
            return False
        f = (frm or "").strip().lower()
        dom = f.rsplit("@", 1)[1] if "@" in f else f
        return f in bl or dom in bl
    except Exception:
        return False


# intent -> prospect status. NOTE: must use only prospector.VALID_STATUSES
# ("ready","sent","replied","client","dead") — a value outside that set (was
# "replied_hot") makes mark_prospect() silently no-op, so the lead stays "ready"
# and keeps getting auto follow-up emails. The hot/interested distinction is
# preserved separately via the reply_intent field (set_prospect_fields).
_STATUS = {
    "interested": "replied",
    "question": "replied",
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


async def _classify(subject: str, body: str, history: str = "") -> str:
    """Classify email/chat reply intent. Uses few-shot feedback examples to reduce 'other'
    rate. ``history`` (optional): pichli baat-cheet transcript — jab diya jaaye to classifier
    samajhta hai ki message ek pichle sawaal ka JAWAAB ho sakta (chat continuity)."""
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
            + (
                "\nNOTE: message pichle sawaal ka JAWAAB bhi ho sakta — context dekh ke "
                "intent decide karo (jaise naam/area/service ka jawab = 'question'/'interested', "
                "'other' nahi)." if history else ""
            )
            + "\nSIRF ek label reply karo, kuch aur nahi."
        )
        user_content = f"Subject: {subject}\n\n{body[:1500]}"
        if history:
            user_content = (
                f"Pichli baat-cheet (context):\n{history[:1500]}\n\n---\n"
                f"Ab ka message:\n{body[:1500]}"
            )
        reply, _ = await free_ai.chat(
            system=system,
            messages=[{"role": "user", "content": user_content}],
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
    biz: str,
    subject: str,
    body: str,
    intent: str,
    *,
    niche: str = "general",
    history_msgs: list[dict[str, str]] | None = None,
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

        # Daily read-back: second-brain context (past replies/decisions for this niche)
        # — reply-drafts ab brain-aware. to_thread (sync vault scan) + 3s deadline +
        # fail-open; "" jab OBSIDIAN_SYNC off. (local asyncio import = NameError-safe.)
        brain_ctx = ""
        try:
            import asyncio as _aio

            from app.platform import obsidian_sync as _obs

            brain_ctx = await _aio.wait_for(
                _aio.to_thread(_obs.brain_context, f"{niche} {intent} {biz}".strip()),
                timeout=3.0,
            )
            if brain_ctx:
                brain_ctx = "\n\n" + brain_ctx
        except Exception:
            brain_ctx = ""

        # Chat continuity: pichli baat-cheet (WhatsApp thread) ko conversation ke
        # roop me feed karo taaki jawab context-aware ho — same sawaal repeat na ho.
        draft_msgs: list[dict[str, str]] = []
        for _m in history_msgs or []:
            _role = _m.get("role")
            _c = str(_m.get("content") or "").strip()
            if _role in ("user", "assistant") and _c:
                draft_msgs.append({"role": _role, "content": _c[:600]})
        draft_msgs.append(
            {
                "role": "user",
                "content": (
                    f"Business: {biz}\nNiche: {niche}\nIntent: {intent}\n"
                    f"Subject: {subject}\n\n{body[:1200]}{objection_ctx}{brain_ctx}"
                ),
            }
        )
        reply, _ = await free_ai.chat(
            system="Tu LeadGen AI ka helpful sales rep hai. Is reply ka chhota, warm, "
            "professional Hinglish jawab likh (max 4 lines). Free Google audit + demo offer "
            "kar; pushy mat ban. Objection ho to empathetic + specific jawab do. Agar upar "
            "pichli baat-cheet hai to usko dhyaan me rakh — wahi sawaal dobara mat poochh, "
            "aage badha. Sirf reply text de.",
            messages=draft_msgs,
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
        M = imaplib.IMAP4_SSL(host, 993, timeout=20)  # no timeout = worker hangs on a stalled IMAP read
        M.login(user, pw)
        M.select("INBOX")
        typ, data = M.search(None, "UNSEEN")
        ids = (data[0].split() if data and data[0] else [])[: max(1, limit)]
        pmap = _prospect_map()
        # SENDER FLOOD CAP (2026-07-07): recent drafts se per-sender counts ek
        # baar build (per-mail file-read nahi) — loop-sender cap ke liye.
        flood_cap = _flood_cap()
        seen_counts = _sender_counts(list_drafts(limit=4000)) if flood_cap else {}
        for i in ids:
            try:
                typ, md = M.fetch(i, "(RFC822)")
                msg = email.message_from_bytes(md[0][1])
                frm = email.utils.parseaddr(msg.get("From", ""))[1].lower()
                subj = _decode(msg.get("Subject", ""))
                p = pmap.get(frm)
                body = _body(msg)
                # BOUNCE/NDR GUARD (2026-07-04): mailer-daemon/postmaster bounce mail
                # was previously falling into the junk-guard below (unknown sender +
                # bulk localpart) and got silently discarded — email_warmup never
                # learned about it, so bounce_rate_7d stayed ~0% regardless of real
                # deliverability. Detect it FIRST, feed the warmup tracker, then skip
                # (a bounce is not a reply to classify/draft).
                if _is_bounce_message(frm, msg, subj):
                    res["skipped"] += 1
                    res["bounced"] = res.get("bounced", 0) + 1
                    try:
                        from app.platform import email_warmup

                        bounced_email = _extract_bounced_email(body, subj, pmap)
                        wr = email_warmup.record_bounce(bounced_email, subj[:120])
                        bp = pmap.get(bounced_email) if bounced_email else None
                        if bp and (bp.get("id") or bp.get("pid")):
                            from app.platform import prospector

                            _bpid = bp.get("id") or bp.get("pid")
                            prospector.mark_prospect(_bpid, "dead")
                            prospector.set_prospect_fields(
                                _bpid,
                                {
                                    "bounce_reason": subj[:160],
                                    "bounced_at": datetime.now(timezone.utc).isoformat(),
                                },
                            )
                        if wr.get("paused"):
                            _notify(
                                "rohan",
                                "bounce_autopause",
                                f"Bounce rate {wr.get('rate_pct')}% — outreach auto-paused 24h",
                            )
                    except Exception:
                        pass
                    continue
                # AUTO-ACK GUARD (2026-07-07): auto-acknowledgement ≠ human reply —
                # LLM classify se PEHLE drop (fake-"interested" + token-burn fix;
                # known-prospect pe bhi lagta, junk-guard ke ulat).
                if _is_auto_ack(msg, subj):
                    res["skipped"] += 1
                    res["auto_ack"] = res.get("auto_ack", 0) + 1
                    continue
                # Operator blocklist (REPLY_SENDER_BLOCKLIST env CSV) — hard skip.
                if _is_blocklisted(frm):
                    res["skipped"] += 1
                    res["blocklisted"] = res.get("blocklisted", 0) + 1
                    continue
                # JUNK GUARD (2026-06-12): unknown sender + bulk/marketing mail = skip.
                # Pehle PayU/Instamojo newsletters "interested" classify hoke FAKE deals
                # bana rahe the + har newsletter pe LLM classify/draft tokens jalte the.
                if p is None and _is_bulk_sender(frm, msg):
                    res["skipped"] += 1
                    continue
                # SENDER FLOOD CAP (2026-07-07): same sender already `cap`+ draft-rows
                # = auto-responder loop; is run ke repeats bhi count hote (increment niche).
                if flood_cap and seen_counts.get(frm, 0) >= flood_cap:
                    res["skipped"] += 1
                    res["flooded"] = res.get("flooded", 0) + 1
                    continue
                seen_counts[frm] = seen_counts.get(frm, 0) + 1
                intent = await _classify(subj, body)
                # LLM-guard (IFC, observe-only): scan UNTRUSTED inbound for prompt-injection.
                # Never blocks — flags the draft so the human reviewer does NOT act on
                # instructions embedded by a malicious sender. ph18/15-16 (llm-security skill).
                _inj = None
                try:
                    from app.platform import llm_guard

                    _gs = llm_guard.scan(f"{subj}\n{body}", source="inbox")
                    if _gs.get("suspicious"):
                        _inj = _gs.get("signals")
                        if llm_guard.enabled():
                            logger.warning(
                                "[reply_agent] LLM_GUARD: possible prompt-injection from %s "
                                "signals=%s — review draft, do NOT act on embedded instructions",
                                frm, _inj,
                            )
                except Exception:
                    pass
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

                at = datetime.now(timezone.utc).isoformat()
                _save_draft(
                    {
                        "from": frm,
                        "subject": subj,
                        "intent": intent,
                        "draft": draft,
                        "injection_flag": _inj,
                        "at": at,
                    }
                )

                if intent in ("interested", "question"):
                    # Phone push: HOT reply — sales moment, turant pata chale (gated ntfy).
                    # Tap-to-act buttons IN the notification (GTM council 2026-07-03: 344
                    # hot replies accumulated, 0 ever cleared, despite this push already
                    # firing every time — root cause was cost-of-action, not visibility).
                    # Reply = opens mailto prefilled (human's own client sends — same
                    # ban-safe 1-click pattern as the dashboard, no server-side send).
                    # Done = signed-token HTTP action (ntfy can't do interactive login).
                    try:
                        from urllib.parse import quote

                        from app.integrations import ntfy

                        hq_id = _hq_id({"from": frm, "at": at})
                        actions: list[dict] = []
                        if draft and not _inj:
                            re_subj = subj if subj.lower().startswith("re:") else f"Re: {subj}"
                            mailto = f"mailto:{frm}?subject={quote(re_subj)}&body={quote(draft)}"
                            actions.append({"action": "view", "label": "💬 Reply", "url": mailto})
                        actions.append(
                            {
                                "action": "http",
                                "label": "✔ Done",
                                "url": f"{_base_url()}/api/growth/reply/hot-queue/"
                                f"quick-done/{make_hq_done_token(hq_id)}",
                                "method": "POST",
                                "clear": True,
                            }
                        )
                        await ntfy.push(
                            "🔥 Hot reply!",
                            f"{(p or {}).get('business_name') or frm}: {subj[:80]}",
                            priority="high",
                            tags=["fire"],
                            actions=actions,
                        )
                    except Exception:
                        pass

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
    no subject, body = the message text. Uses ``wa_conversation`` per-number thread so
    classify + draft are CONTEXT-aware (samajhta hai reply kis sawaal ka jawab hai —
    wahi baat repeat nahi karta). Writes a draft to ``reply_drafts.jsonl`` with
    ``channel="whatsapp"`` and notifies the team. NEVER raises; returns the saved record
    (``{}`` on empty text). Auto-send OFF by DEFAULT (ban-safe, 1-click human send);
    set ``WHATSAPP_AI_AUTOREPLY=1`` to actually send the contextual reply back (opt-in;
    §5 bulk ``WHATSAPP_AUTO_SEND`` gate is separate + untouched).
    """
    txt = (text or "").strip()
    frm = (from_number or "").strip()
    if not txt:
        return {}
    # STATUS/BROADCAST GUARD (2026-07-07): WhatsApp status updates + broadcast
    # channels webhook se aa ke "interested" tak classify ho rahe the (fake-hot
    # noise in reply_drafts/Hot-Queue — deliverability audit). Ye human 1-1
    # reply nahi hai — drop before classify. Operator blocklist bhi yahin.
    if frm.lower() == "status" or "@broadcast" in frm.lower() or _is_blocklisted(frm):
        return {}

    # Conversation memory (2026-07-07): pichli baat-cheet nikaalo (current message record
    # hone se PEHLE, taaki yeh sirf PRIOR turns ho), phir current inbound turn record karo.
    # Isse classify + draft context-aware ban jaate hain — AI reply ka matlab samajhta hai
    # aur wahi sawaal repeat nahi karta ("samajh nahi pa raha / phir se poochh raha hai" fix).
    prior_msgs: list[dict[str, str]] = []
    ctx = ""
    try:
        from app.platform import wa_conversation

        prior_msgs = wa_conversation.history_messages(frm)
        ctx = wa_conversation.as_context_text(prior_msgs)
        wa_conversation.record(frm, txt, "in", message_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("wa_conversation context err: %s", exc)

    try:
        intent = await _classify("WhatsApp inbound", txt, history=ctx)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("wa classify err: %s", exc)
        intent = "other"

    # Auto-reply (INERT default — OFF). Ban-safe: yeh sirf INBOUND (customer-initiated)
    # 1-to-1 conversation ka reactive jawab hai, NOT bulk cold auto-send (§5 ka
    # WHATSAPP_AUTO_SEND gate alag hai + untouched). WAHA doc bhi "inbound auto-reply +
    # warm 1-to-1" ko safe use bataata hai. Enable: WHATSAPP_AI_AUTOREPLY=1.
    _auto = os.environ.get("WHATSAPP_AI_AUTOREPLY", "").strip().lower() in {"1", "true", "yes", "on"}
    _draft_intents = ("interested", "question", "objection") + (("other",) if _auto else ())
    draft = ""
    if intent in _draft_intents:
        try:
            draft = await _draft(
                business_name or "", "WhatsApp inquiry", txt, intent, history_msgs=prior_msgs
            )
        except Exception:  # pragma: no cover - defensive
            draft = ""
    at = datetime.now(timezone.utc).isoformat()

    # Gated auto-send: customer ko turant conversational jawab (default OFF). Never raises.
    auto_sent = False
    if _auto and draft and intent not in ("unsubscribe", "not_interested", "ooo"):
        try:
            from app.integrations.whatsapp import get_whatsapp_sender

            _res = await get_whatsapp_sender().send_text_message(frm, draft)
            auto_sent = bool(_res) and not (isinstance(_res, dict) and _res.get("error"))
            if auto_sent:
                try:
                    from app.platform import wa_conversation

                    wa_conversation.record(frm, draft, "out")
                except Exception:
                    pass
                logger.info("[reply_agent] WA auto-reply sent to %s (intent=%s)", frm, intent)
        except Exception as _ae:  # pragma: no cover - defensive
            logger.info("[reply_agent] WA auto-reply send failed: %s", _ae)

    rec = {
        "channel": "whatsapp",
        "from": frm,
        "message_id": (message_id or "").strip(),
        "text": txt[:2000],
        "intent": intent,
        "draft": draft,
        "auto_sent": auto_sent,
        "status": _STATUS.get(intent, "replied"),
        "at": at,
    }
    _save_draft(rec)
    member = "swara" if intent in ("interested", "question") else "rohan"
    _notify(member, f"wa_reply_{intent}", f"{frm}: {txt[:60]}")
    if intent in ("interested", "question"):
        # Phone push parity with the email path (2026-07-03 GTM fix) — WA hot
        # replies previously never pushed at all. Reply = opens wa.me prefilled
        # (human's own WhatsApp sends — ban-safe, no server-side send).
        try:
            from urllib.parse import quote

            from app.integrations import ntfy

            hq_id = _hq_id({"from": frm, "at": at})
            wa_num = _india_wa_number(frm)
            actions: list[dict] = []
            if draft and wa_num:
                actions.append(
                    {
                        "action": "view",
                        "label": "💬 Reply",
                        "url": f"https://wa.me/{wa_num}?text={quote(draft)}",
                    }
                )
            actions.append(
                {
                    "action": "http",
                    "label": "✔ Done",
                    "url": f"{_base_url()}/api/growth/reply/hot-queue/"
                    f"quick-done/{make_hq_done_token(hq_id)}",
                    "method": "POST",
                    "clear": True,
                }
            )
            await ntfy.push(
                "🔥 Hot WhatsApp reply!",
                f"{business_name or frm}: {txt[:80]}",
                priority="high",
                tags=["fire"],
                actions=actions,
            )
        except Exception:
            pass
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


# --- Hot Queue (GTM 2026-07-02): interested/question replies = sabse garam
# sales moments. Drafts file me pade rehte the; yeh unhe dedupe + phone-join
# karke ek workable daily queue banata hai (admin /app/inbox "Hot Queue" tab).

_HOT_INTENTS = ("interested", "question")

# --- Quick-action tokens (GTM council 2026-07-03): 344 hot replies accumulated,
# 0 ever cleared, despite the ntfy push already firing every time — root cause
# was cost-of-action (open dashboard, read, decide, click), not visibility. Fix:
# put Reply/Done buttons IN the push notification itself. ntfy action buttons
# can't do interactive login, so "Done" needs a stateless signed token scoped to
# exactly one hq_id — same trust model as email_unsub's one-click tokens.
_HQ_TOKEN_SECRET = (
    os.environ.get("HQ_ACTION_SECRET") or os.environ.get("SECRET_KEY") or "leadsgenai-hq-v1"
).encode()


def _base_url() -> str:
    return (os.environ.get("PUBLIC_BASE_URL") or "https://leadsgenai.in").rstrip("/")


def make_hq_done_token(hq_id: str) -> str:
    """Stateless HMAC token for a 1-tap 'Done' push-notification action. Never raises."""
    import base64
    import hashlib
    import hmac

    sig = hmac.new(_HQ_TOKEN_SECRET, hq_id.encode(), hashlib.sha256).hexdigest()[:24]
    return base64.urlsafe_b64encode(f"{hq_id}|{sig}".encode()).decode().rstrip("=")


def verify_hq_done_token(token: str) -> str | None:
    """Return the hq_id if the token is authentic, else None. Never raises."""
    import base64
    import hashlib
    import hmac

    try:
        pad = "=" * (-len(token or "") % 4)
        raw = base64.urlsafe_b64decode((token + pad).encode()).decode()
        hq_id, sig = raw.rsplit("|", 1)
        good = hmac.new(_HQ_TOKEN_SECRET, hq_id.encode(), hashlib.sha256).hexdigest()[:24]
        return hq_id if hmac.compare_digest(sig, good) else None
    except Exception:
        return None


def _hq_id(row: dict) -> str:
    """Stable id for a draft row (email recs have no id field): sha1(from+at)."""
    import hashlib

    key = f"{row.get('from') or ''}|{row.get('at') or ''}"
    return hashlib.sha1(key.encode("utf-8", "ignore")).hexdigest()[:12]


def _india_wa_number(raw: Any) -> str:
    """Return 91XXXXXXXXXX only for plausible Indian mobile numbers.

    Meta/WA webhooks sometimes surface account/status ids as long numeric strings;
    using their last 10 digits creates bogus wa.me links. Keep this deliberately
    conservative: 10-digit mobile, 91+mobile, or 0+mobile only.
    """
    digits = re.sub(r"\D", "", str(raw or ""))
    d10 = ""
    if len(digits) == 10:
        d10 = digits
    elif len(digits) == 11 and digits.startswith("0"):
        d10 = digits[1:]
    elif len(digits) == 12 and digits.startswith("91"):
        d10 = digits[2:]
    elif len(digits) == 13 and digits.startswith("091"):
        d10 = digits[3:]
    if len(d10) == 10 and d10[0] in "6789":
        return f"91{d10}"
    return ""


def _full_prospect_map() -> dict[str, dict]:
    """email -> prospect over the FULL store (list_prospects newest-cap hides
    old rows — same lesson as auto_outreach pending backlog)."""
    out: dict[str, dict] = {}
    try:
        from app.platform import prospector

        rows = []
        try:
            rows = prospector._read_all()
        except Exception:
            rows = prospector.list_prospects(status=None, limit=2000)
        for p in rows:
            e = str((p or {}).get("email") or "").strip().lower()
            if e:
                out[e] = p
    except Exception as exc:
        logger.debug("full_prospect_map err: %s", exc)
    return out


def hot_queue(limit: int = 50, intents: tuple = _HOT_INTENTS) -> list[dict]:
    """Prioritized reply queue: filter hot intents, drop handled, dedupe by
    sender (latest wins), newest-first, prospect phone/business joined in.
    NEVER raises — [] on any failure."""
    try:
        rows = [r for r in list_drafts(limit=100000) if r.get("intent") in intents]
        rows = [r for r in rows if (r.get("hq_status") or "") != "done"]
        latest: dict[str, dict] = {}
        for r in sorted(rows, key=lambda x: str(x.get("at") or "")):
            sender = str(r.get("from") or "").strip().lower() or _hq_id(r)
            latest[sender] = r
        out = sorted(latest.values(), key=lambda x: str(x.get("at") or ""), reverse=True)[
            : max(1, limit)
        ]
        pmap = _full_prospect_map()
        now = datetime.now(timezone.utc)
        for r in out:
            r["hq_id"] = _hq_id(r)
            p = pmap.get(str(r.get("from") or "").strip().lower()) or {}
            r["phone"] = r.get("phone") or p.get("phone") or ""
            if not r["phone"] and r.get("channel") == "whatsapp":
                r["phone"] = str(r.get("from") or "")  # WA recs: from = phone number
            wa_num = _india_wa_number(r.get("phone") or "")
            if wa_num:
                from urllib.parse import quote

                msg = str(r.get("draft") or "").strip()
                r["wa_link"] = f"https://wa.me/{wa_num}" + (
                    f"?text={quote(msg)}" if msg else ""
                )
            else:
                r["wa_link"] = ""
            r["business_name"] = r.get("business_name") or p.get("business_name") or ""
            r["niche"] = r.get("niche") or p.get("niche") or ""
            r["city"] = r.get("city") or p.get("city") or ""
            try:
                at = datetime.fromisoformat(str(r.get("at") or "").replace("Z", "+00:00"))
                if at.tzinfo is None:
                    at = at.replace(tzinfo=timezone.utc)
                r["age_days"] = max(0, (now - at).days)
            except Exception:
                r["age_days"] = None
        return out
    except Exception as exc:
        logger.debug("hot_queue err: %s", exc)
        return []


def mark_handled(hq_id: str) -> bool:
    """1-click 'Done' — set hq_status=done on the matching draft row (in-place
    rewrite, temp-file + atomic replace). False if id not found / any error."""
    hq_id = (hq_id or "").strip()
    if not hq_id or not os.path.exists(_DRAFTS_FILE):
        return False
    try:
        found = False
        lines: list[str] = []
        with open(_DRAFTS_FILE, encoding="utf-8") as f:
            for line in f:
                raw = line.rstrip("\n")
                if not raw.strip():
                    continue
                try:
                    row = json.loads(raw)
                except Exception:
                    lines.append(raw)
                    continue
                if _hq_id(row) == hq_id and (row.get("hq_status") or "") != "done":
                    row["hq_status"] = "done"
                    row["hq_done_at"] = datetime.now(timezone.utc).isoformat()
                    found = True
                    lines.append(json.dumps(row, ensure_ascii=False))
                else:
                    lines.append(raw)
        if not found:
            return False
        tmp = _DRAFTS_FILE + ".hq_tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(tmp, _DRAFTS_FILE)
        return True
    except Exception as exc:
        logger.debug("mark_handled err: %s", exc)
        return False


__all__ = [
    "run_reply_triage",
    "whatsapp_reply",
    "list_drafts",
    "hot_queue",
    "mark_handled",
    "make_hq_done_token",
    "verify_hq_done_token",
]
