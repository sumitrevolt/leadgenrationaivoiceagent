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
(reuses the SMTP login). Safe email auto-reply can be armed with `REPLY_AUTO_SEND=1`
or the runtime feature flag `reply_auto_send`; it remains known-prospect-only,
suppression/injection gated, bounded and idempotency-claimed. `IMAP_HOST` overrides
(default derived from SMTP).
"""

from __future__ import annotations

import email
import email.utils
import imaplib
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from typing import Any

logger = logging.getLogger(__name__)

# Human-reply intents (LLM vocabulary). Delivery failures (hard_bounce /
# soft_bounce / complaint) are NEVER LLM labels — they are assigned by
# classify_delivery_report() before _classify() runs.
_CATS = ["interested", "question", "objection", "not_interested", "unsubscribe", "ooo", "other"]
_DELIVERY_OUTCOMES = ("hard_bounce", "soft_bounce", "complaint")

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
_COMPLAINT_LOCALPARTS = {"complaint", "abuse", "feedbackloop", "feedback-loop", "fbl"}
# RFC 3464 DSN status codes: 5.x.x = permanent (hard), 4.x.x = transient (soft).
# HARD RULE 2026-07-25: subject text alone is NEVER a classification signal
# (that mistake produced the fake "interested" signal earlier).
_DSN_STATUS_RE = re.compile(
    r"(?:status\s*[:=]\s*|smtp;\s*\d{3}\s+|diagnostic-code\s*[:=][^\n]*?)"
    r"([45]\.\d{1,3}\.\d{1,3})"
    r"|"
    r"\b([45]\.\d{1,3}\.\d{1,3})\b",
    re.IGNORECASE,
)
# Body-level structural NDR markers (RFC 3464 fields) — NOT subject guessing.
_NDR_BODY_STRUCT_RE = re.compile(
    r"final-recipient\s*:|original-recipient\s*:|reporting-mta\s*:|"
    r"diagnostic-code\s*:|action\s*:\s*(failed|delayed)|"
    r"content-type\s*:\s*message/delivery-status|"
    r"this is (an? )?(automatically generated )?delivery status notification",
    re.IGNORECASE,
)
_ARF_BODY_RE = re.compile(
    r"feedback-type\s*:\s*abuse|report-type\s*=\s*feedback-report|"
    r"content-type\s*:\s*message/feedback-report",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _sender_localpart(frm: str) -> str:
    try:
        addr = (frm or "").strip().lower()
        if "<" in addr and ">" in addr:
            addr = email.utils.parseaddr(frm)[1].lower() or addr
        return (addr.split("@", 1)[0] if "@" in addr else addr).strip()
    except Exception:
        return ""


def _dsn_class(body: str) -> str | None:
    """Return '5' (hard) / '4' (soft) from first DSN status in body, else None."""
    try:
        for m in _DSN_STATUS_RE.finditer(body or ""):
            code = (m.group(1) or m.group(2) or "").strip()
            if code.startswith("5"):
                return "5"
            if code.startswith("4"):
                return "4"
    except Exception:
        pass
    return None


def _msg_content_type(msg: Any, content_type: str = "") -> str:
    if content_type:
        return str(content_type).lower()
    try:
        if msg is not None:
            raw = str(msg.get("Content-Type") or msg.get_content_type() or "")
            return raw.lower()
    except Exception:
        pass
    return ""


def _msg_header(msg: Any, name: str, fallback: str = "") -> str:
    if fallback:
        return str(fallback).strip()
    try:
        if msg is not None:
            return str(msg.get(name) or "").strip()
    except Exception:
        pass
    return ""


def classify_delivery_report(
    frm: str = "",
    msg: Any = None,
    subj: str = "",
    body: str = "",
    *,
    content_type: str = "",
    auto_submitted: str = "",
    feedback_type: str = "",
) -> str | None:
    """Classify NDR / FBL mail into hard_bounce | soft_bounce | complaint.

    HARD RULE: never classify from subject text alone. Requires at least one
    structural signal (bounce/complaint sender, RFC 3464 multipart/report,
    Auto-Submitted + DSN body fields, Feedback-Type / ARF, or NDR body structure).

    Returns None when evidence is insufficient. Never raises.
    """
    try:
        local = _sender_localpart(frm)
        ctype = _msg_content_type(msg, content_type)
        auto_sub = (auto_submitted or _msg_header(msg, "Auto-Submitted")).strip().lower()
        fb_type = (
            (
                feedback_type
                or _msg_header(msg, "Feedback-Type")
                or _msg_header(msg, "X-Feedback-Type")
            )
            .strip()
            .lower()
        )
        blob = f"{body or ''}"
        # Also peek report payload when available (multipart/report).
        payload_snip = ""
        try:
            if msg is not None and "report" in ctype:
                payload_snip = str(msg.get_payload() or "")[:4000].lower()
        except Exception:
            payload_snip = ""
        scan = f"{blob}\n{payload_snip}"

        is_bounce_sender = local in _BOUNCE_LOCALPARTS
        is_complaint_sender = local in _COMPLAINT_LOCALPARTS
        is_delivery_report = (
            ("multipart/report" in ctype and "delivery-status" in ctype)
            or ("multipart/report" in ctype and "delivery-status" in scan)
            or ("report-type=delivery-status" in ctype)
        )
        is_feedback_report = (
            "report-type=feedback-report" in ctype
            or "feedback-report" in ctype
            or bool(fb_type and fb_type not in ("", "not-spam"))
            or bool(_ARF_BODY_RE.search(scan))
        )
        has_ndr_body = bool(_NDR_BODY_STRUCT_RE.search(scan))
        auto_with_dsn = bool(auto_sub and auto_sub != "no" and (_dsn_class(scan) or has_ndr_body))

        # Structural gate — subject alone is NEVER enough.
        structural = (
            is_bounce_sender
            or is_complaint_sender
            or is_delivery_report
            or is_feedback_report
            or has_ndr_body
            or auto_with_dsn
        )
        if not structural:
            return None

        # Complaints / feedback-loop first.
        if is_complaint_sender or is_feedback_report:
            return "complaint"

        # Bounce / DSN path.
        if is_bounce_sender or is_delivery_report or has_ndr_body or auto_with_dsn:
            dsn = _dsn_class(scan)
            if dsn == "4":
                return "soft_bounce"
            # 5.x.x OR bounce sender / delivery-status without a 4.x.x → hard.
            return "hard_bounce"

        return None
    except Exception:
        return None


def _is_bounce_message(frm: str, msg: Any, subj: str, body: str = "") -> bool:
    """True when classify_delivery_report finds a bounce/complaint.

    Kept for callers/tests. Subject alone is insufficient (see classify_delivery_report).
    Never raises.
    """
    return classify_delivery_report(frm, msg, subj, body) is not None


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


# CASE-CLOSURE GUARD (2026-07-25): ticketing/CRM auto-responders that CLOSE a
# case were LLM-classifying as "interested" — the exact OPPOSITE of the message.
# Production audit found 292 of 304 all-time "interested" outcomes came from ONE
# adityabirla.com ticketing address, with bodies like "Not related to Birla Opus.
# Hence, closed.", "Not required as of now. Hence, case is closed." and "We
# regret to inform you...". That single sender made the "interested" signal
# worthless: 304 interested outcomes were really ~8 distinct prospects.
#
# _is_auto_ack (07-07) already targets this sender but only matches ACK wording
# ("thank you for your enquiry", "we have received your") and only scans the
# SUBJECT — a closure notice matches neither. This guard reads subject AND body.
#
# Patterns are deliberately narrow: each is an unambiguous refusal/closure that
# cannot appear in a genuine "yes, tell me more" reply. REPLY_CLOSURE_GUARD=0
# disables; REPLY_CLOSURE_EXTRA_TERMS (CSV, literal substrings) lets an operator
# add patterns without a deploy — same ergonomics as the spam guard.
_CLOSURE_RE = re.compile(
    r"hence\s*,?\s*(the\s+)?(case\s+is\s+)?closed|"
    r"case\s+(is\s+)?(now\s+)?closed|closing\s+(this|the)\s+(case|ticket|request)|"
    r"ticket\s+(has\s+been\s+)?closed|"
    r"not\s+required\s+(as\s+of\s+now|at\s+(this|the)\s+(time|moment)|currently)|"
    r"no\s+(further\s+)?requirement|"
    r"we\s+regret\s+to\s+inform|"
    r"not\s+related\s+to\s+",
    re.IGNORECASE,
)


def _is_case_closure(subj: str, body: str) -> bool:
    """Ticketing/CRM case-closure or explicit refusal detect (subject + body).

    Runs for EVERYONE, like the auto-ack guard: a closure notice is not a warm
    reply no matter who sends it. REPLY_CLOSURE_GUARD=0 = guard off.
    Never raises.
    """
    try:
        if (os.getenv("REPLY_CLOSURE_GUARD", "1") or "1").strip().lower() in {
            "0",
            "false",
            "off",
        }:
            return False
        blob = f"{subj or ''}\n{body or ''}"
        if _CLOSURE_RE.search(blob):
            return True
        extra = (os.getenv("REPLY_CLOSURE_EXTRA_TERMS", "") or "").strip()
        if extra:
            low = blob.lower()
            for term in extra.split(","):
                term = term.strip().lower()
                if term and term in low:
                    return True
    except Exception:
        pass
    return False


# SPAM CONTENT GUARD (2026-07-15): betting/gambling spam ("Reddy Anna" cricket-ID
# type mail) LLM se "interested" classify ho ke Hot Queue me draft-ready aa raha
# tha (07-14 audit). _is_bulk_sender headers dekhta hai — yeh CONTENT dekhta hai,
# isliye header-clean spam bhi pakda jaata hai. Patterns deliberately narrow
# (betting/casino vocab only) taaki genuine business reply kabhi false-positive
# na ho. REPLY_SPAM_CONTENT_GUARD=0 disables; REPLY_SPAM_EXTRA_TERMS (CSV,
# literal substrings) se operator naye patterns bina deploy add kar sakta hai.
_SPAM_CONTENT_RE = re.compile(
    r"reddy\s*anna|bett?ing\s*(id|app|site|tips|exchange)|\bcasino\b|\bsatta\b|"
    r"\bmatka\b|teen\s*patti|\bjackpot\b|cricket\s*id\b|book(ie|\s*id)\b|"
    r"\bgambling\b|\bwagering?\b|aviator\s*(game|id)|ipl\s*id\b|lottery\s*(win|ticket|number)",
    re.IGNORECASE,
)


def _is_spam_content(subj: str, body: str) -> bool:
    """Betting/gambling spam detect (subject+body content). Known-prospect pe BHI
    lagta — yeh vocab kisi genuine niche-business reply me nahi aata.
    REPLY_SPAM_CONTENT_GUARD=0 = guard off. Never raises."""
    try:
        if (os.getenv("REPLY_SPAM_CONTENT_GUARD", "1") or "1").strip().lower() in {
            "0",
            "false",
            "off",
            "no",
        }:
            return False
        txt = f"{subj or ''}\n{body or ''}"
        if _SPAM_CONTENT_RE.search(txt):
            return True
        extra = os.getenv("REPLY_SPAM_EXTRA_TERMS", "") or ""
        low = txt.lower()
        for term in (t.strip().lower() for t in extra.split(",")):
            if term and term in low:
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
    "hard_bounce": "dead",
    "soft_bounce": "ready",  # transient — do not kill the prospect
    "complaint": "dead",
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


def _source_received_at(msg: Any, fetch_data: Any = None) -> str:
    """Conservative source time from IMAP INTERNALDATE and bounded RFC Date."""
    candidates: list[datetime] = []
    try:
        dt = email.utils.parsedate_to_datetime(str(msg.get("Date") or ""))
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            candidates.append(dt.astimezone(timezone.utc))
    except Exception:
        pass
    try:
        meta = fetch_data[0][0] if fetch_data and fetch_data[0] else b""
        if isinstance(meta, bytes):
            meta = meta.decode("ascii", "ignore")
        match = re.search(r'INTERNALDATE "([^"\r\n]{1,80})"', str(meta))
        if match:
            candidates.append(
                datetime.strptime(match.group(1), "%d-%b-%Y %H:%M:%S %z").astimezone(timezone.utc)
            )
    except Exception:
        pass
    now = datetime.now(timezone.utc)
    plausible = [dt for dt in candidates if dt <= now + timedelta(minutes=5)]
    return min(plausible).isoformat() if plausible else ""


def _safe_thread_headers(msg: Any) -> tuple[str, str]:
    """Persist only bounded RFC-like message IDs, never arbitrary header text."""
    try:
        token_re = re.compile(r"<[^<>\r\n]{1,200}>")
        message_ids = token_re.findall(str(msg.get("Message-ID") or ""))
        references = token_re.findall(str(msg.get("References") or ""))[-5:]
        return (message_ids[0] if message_ids else "", " ".join(references)[:1000])
    except Exception:
        return "", ""


#: Standalone opt-out commands. Deliberately NARROW and deterministic — this
#: runs before the junk guard, so a loose pattern would suppress real prospects
#: over a passing mention ("stop by the shop"). Each must appear as a whole word
#: in the recipient's OWN text, not inside quoted history.
#: Unambiguous multi-word phrases — safe to match anywhere in the sender's text.
_OPTOUT_PHRASE_RE = re.compile(
    r"(?:^|[\s\W])(unsubscribe|remove\s+me|opt[\s-]?out|do\s+not\s+contact"
    r"|don'?t\s+contact\s+me|take\s+me\s+off)(?:$|[\s\W])",
    re.IGNORECASE,
)

#: Bare single-word commands, matched ONLY as a whole line/subject.
#: "STOP" alone is an opt-out; "please stop by the shop tomorrow" is not — a
#: substring match here would suppress a live, interested prospect, which is a
#: worse failure than missing one opt-out (the phrase list above still catches
#: every conventional wording).
_OPTOUT_BARE_RE = re.compile(r"^\s*(stop|unsubscribe|remove|end|quit)\s*[.!]?\s*$", re.IGNORECASE)

#: Where a quoted reply chain begins. Everything after the first match is the
#: sender quoting US, so an opt-out line in our own footer must not be read as
#: the recipient opting out.
_QUOTE_BOUNDARY_RE = re.compile(
    r"(^\s*>)|(-{2,}\s*original message)|(^\s*on .{0,120}\bwrote:)|(_{5,})|(^\s*from:\s)",
    re.IGNORECASE | re.MULTILINE,
)


def _unquoted_head(body: str, limit: int = 1200) -> str:
    """The sender's own words: text above any quoted reply chain."""
    text = str(body or "")
    m = _QUOTE_BOUNDARY_RE.search(text)
    if m:
        text = text[: m.start()]
    return text[:limit]


def _is_explicit_optout(subject: str, body: str) -> bool:
    """True for an unambiguous opt-out request. Deterministic, no LLM.

    Only the subject and the UNQUOTED head of the body are considered — every
    outreach mail we send carries "reply REMOVE" in its footer, so scanning the
    quoted history would make every reply look like an opt-out.
    """
    subj = str(subject or "")
    head = _unquoted_head(body)
    if _OPTOUT_PHRASE_RE.search(subj) or _OPTOUT_PHRASE_RE.search(head):
        return True
    # Bare commands: whole subject, or any line standing entirely on its own.
    if _OPTOUT_BARE_RE.match(subj):
        return True
    return any(_OPTOUT_BARE_RE.match(ln) for ln in head.splitlines())


def _record_unresolved_optout(destination: str, subject: str) -> None:
    """Durable compliance exception when an opt-out cannot be tied to a prospect.

    We know the destination but not who they are. Suppressing that exact address
    is supported by the evidence; inventing a broader permanent record is not.
    The exception exists so an admin can reconcile identity later.
    """
    try:
        from app.platform import email_unsub

        # Sits beside the canonical suppression ledger so it moves with it when
        # the runtime-data root is externalized. Call the resolver — the retired
        # ``_STORE`` shim freezes a Path that fixtures can no longer redirect.
        path = email_unsub._store_path().parent / "unresolved_optouts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "kind": "UNRESOLVED_OPTOUT",
                        "destination": destination,
                        "subject": str(subject or "")[:200],
                        "at": datetime.now(timezone.utc).isoformat(),
                        "resolved": False,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception as e:  # never break triage
        logger.warning("[reply_agent] unresolved-optout exception write failed: %s", e)


def _reply_delivery_key(sender: str, message_id: str) -> str:
    """Stable, PII-minimized idempotency key for one inbound email message."""
    import hashlib

    sender = (sender or "").strip().lower()
    message_id = (message_id or "").strip()
    if not sender or not message_id:
        return ""
    return hashlib.sha256(f"{sender}|{message_id}".encode("utf-8", "ignore")).hexdigest()[:32]


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
                "'other' nahi)."
                if history
                else ""
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


def _interested_offer_block(biz: str = "") -> str:
    """Offer + payment footer appended to an ``interested`` reply — the money step.

    1. It resolves the VPA through ``upi_config.get_vpa()`` (env -> settings ->
       ``data/platform_upi.json``), NOT ``os.environ["UPI_VPA"]``. Admins arm UPI
       at runtime via ``POST /api/admin/upi/configure`` with no restart, and every
       other payment surface already reads the canonical resolver
       (``activation._payments_ready``, ``public_site`` pay-info, ``dunning``).
       Scope of that inconsistency, stated precisely: prod probed 2026-08-04 has
       ``upi_config.source() == "env"`` with ``UPI_VPA`` set, so the old env read
       returned the right VPA and **the bug never fired in production**. It WOULD
       fire the moment the documented no-restart admin path is used while env is
       unset — ``/api/public/pay-info`` and ``activation.payments_ready`` would
       both keep reporting healthy off the resolver while this footer went blank.
    2. It ships an NPCI ``upi://pay`` deep-link instead of a bare VPA string, so
       the prospect taps once instead of typing a handle. Same shape as
       ``billing/dunning._ensure_pay_link`` / ``marketing/upi_kit._build_upi_link``.

    **No ``am=`` amount is prefilled, deliberately.** This function has no plan or
    deal binding — ``_draft`` receives only business name, subject, body, intent
    and niche. The catalogue is not single-price (Marketing Main ₹1,999, Combo
    ₹5,999, and Voice bands ₹4,999/₹9,999/₹19,999), so prefilling the Starter
    price would hand a Combo- or Voice-interested prospect a one-tap link that
    underpays their actual plan — a billing-truth break (CLAUDE.md §5), not a UX
    nit. Amount-optional matches ``upi_kit`` (skips ``am`` when empty) and its
    slip's "Amount aap khud enter karein" branch. The prospect picks the plan on
    ``/pricing``. Re-adding ``am=`` requires a real plan binding first.

    ``tn`` carries the business name as **human-readable context only** — it is
    not unique and does NOT by itself guarantee bank reconciliation. No immutable
    prospect/deal/order reference exists at this point in the state machine; that
    remains an open payment-automation gap.

    Gating is unchanged from the original: UPI unarmed -> **empty string**, no
    footer at all. Only the footer's content changes here, never whether it
    appears — the shared ``whatsapp_reply`` path drafts through ``_draft`` too,
    and an unconditional footer would put a pricing line into WhatsApp replies
    that never carried one (caught by ``test_wa_conversation`` in CI). Never raises.
    """
    try:
        from urllib.parse import quote

        from app.platform import upi_config

        vpa = (upi_config.get_vpa() or "").strip()
        if not vpa:
            return ""

        pricing = "\n\nAage badhne ke liye pricing: https://leadsgenai.in/pricing"

        # No `am=` — see docstring. Plan is unknown here and the catalogue is
        # multi-price, so an amount prefill would quote the wrong plan.
        note = f"LeadsGenAI {biz}".strip()[:80]
        parts = [f"pa={quote(vpa, safe='@')}", "pn=LeadsGenAI"]
        if note:
            parts.append(f"tn={quote(note)}")
        parts.append("cu=INR")
        link = "upi://pay?" + "&".join(parts)

        return pricing + f"\n1-tap UPI: {link}\nYa UPI ID: {vpa}"
    except Exception:  # pragma: no cover - defensive, never block the reply
        # Broken/unreadable UPI config behaves exactly like unarmed: no footer.
        # (Must not reference `pricing` here — it is bound after the VPA check,
        # so a raising get_vpa() would UnboundLocalError and lose the whole draft.)
        return ""


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
            reply += _interested_offer_block(biz)
        return reply
    except Exception:
        return ""


def _safe_hot_reply_fallback(intent: str) -> str:
    """Deterministic acknowledgement when every free LLM provider is unavailable.

    It deliberately makes no pricing, timing, or service promise. The normal
    suppression, known-prospect, source-age, scan, claim, and cap gates still
    apply before this text can leave the system.
    """
    if intent not in ("interested", "question"):
        return ""
    return (
        "Namaste, aapke message ke liye dhanyavaad. Humne aapki enquiry receive kar li hai.\n\n"
        "Aap LeadGen AI ka free audit aur demo yahan dekh sakte hain: "
        "https://leadsgenai.in/demo\n\n"
        "Agar aap apna preferred time ya main sawaal reply mein share kar dein, "
        "hum next step email par bhej denge."
    )


def _save_draft(rec: dict[str, Any]) -> bool:
    try:
        from app.utils.file_lock import file_lock

        with file_lock(_DRAFTS_FILE) as locked:
            if not locked:
                logger.warning("save_draft skipped: strict lock unavailable")
                return False
            os.makedirs(os.path.dirname(_DRAFTS_FILE), exist_ok=True)
            with open(_DRAFTS_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            return True
    except Exception as exc:
        logger.debug("save_draft err: %s", exc)
        return False


def _mark_imap_seen(mailbox: Any, message_id: Any) -> bool:
    """Mark handled mail seen only after its durable side effect succeeded."""
    try:
        mailbox.store(message_id, "+FLAGS", "\\Seen")
        return True
    except Exception:
        return False


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
        auto_mode = await _reply_auto_send_enabled()
        M = imaplib.IMAP4_SSL(
            host, 993, timeout=20
        )  # no timeout = worker hangs on a stalled IMAP read
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
                typ, md = M.fetch(i, "(BODY.PEEK[] INTERNALDATE)")
                msg = email.message_from_bytes(md[0][1])
                frm = email.utils.parseaddr(msg.get("From", ""))[1].lower()
                subj = _decode(msg.get("Subject", ""))
                p = pmap.get(frm)
                body = _body(msg)
                # BOUNCE / COMPLAINT GUARD (2026-07-04, hardened 2026-07-25):
                # mailer-daemon NDRs + FBL complaints must NEVER reach the LLM and
                # must NEVER count as engagement. Classify structurally (DSN /
                # multipart/report / bounce sender / Feedback-Type) — subject
                # text alone is insufficient. Wire outcome into interactions so
                # hard/soft/complaint rates are measurable.
                delivery_kind = classify_delivery_report(frm, msg, subj, body)
                if delivery_kind:
                    res["skipped"] += 1
                    res[delivery_kind] = res.get(delivery_kind, 0) + 1
                    bounced_email = ""
                    try:
                        from app.platform import email_warmup

                        bounced_email = _extract_bounced_email(body, subj, pmap)
                        if delivery_kind == "complaint":
                            wr = email_warmup.record_complaint(
                                bounced_email or frm or "", f"fbl_{subj[:80]}"
                            )
                        else:
                            wr = email_warmup.record_bounce(
                                bounced_email, f"{delivery_kind}:{subj[:100]}"
                            )
                        bp = pmap.get(bounced_email) if bounced_email else None
                        # Hard bounce + complaint → dead. Soft bounce stays ready.
                        if (
                            delivery_kind in ("hard_bounce", "complaint")
                            and bp
                            and (bp.get("id") or bp.get("pid"))
                        ):
                            from app.platform import prospector

                            _bpid = bp.get("id") or bp.get("pid")
                            prospector.mark_prospect(_bpid, "dead")
                            prospector.set_prospect_fields(
                                _bpid,
                                {
                                    "bounce_reason": f"{delivery_kind}:{subj[:140]}",
                                    "bounced_at": datetime.now(timezone.utc).isoformat(),
                                },
                            )
                        # Durable address-level suppression. Marking the prospect
                        # row dead left the ADDRESS mailable from every other row,
                        # so the same dead mailbox kept getting mail and kept
                        # damaging deliverability.
                        #
                        # Scope is deliberately NOT global: a hard bounce says the
                        # mailbox is dead, not that the person opted out, so the
                        # contact's WhatsApp number must stay reachable. Only an
                        # explicit opt-out reply escalates to ALL_OUTREACH.
                        if delivery_kind in ("hard_bounce", "complaint") and bounced_email:
                            try:
                                from app.platform import email_unsub

                                email_unsub.suppress(
                                    bounced_email,
                                    reason=delivery_kind,
                                    scope=email_unsub.SCOPE_EMAIL_ADDRESS,
                                    channel="email",
                                    prospect_id=str(
                                        (bp or {}).get("id") or (bp or {}).get("pid") or ""
                                    ),
                                    event_id=_reply_delivery_key(
                                        bounced_email, _safe_thread_headers(msg)[0]
                                    ),
                                    source="delivery_report",
                                )
                            except Exception as _bsup_err:
                                logger.warning(
                                    "[reply_agent] bounce suppression failed: %s", _bsup_err
                                )
                        if wr.get("paused"):
                            _notify(
                                "rohan",
                                "bounce_autopause",
                                f"Deliverability pause {wr.get('rate_pct')}% — outreach auto-paused 24h",
                            )
                    except Exception:
                        pass
                    try:
                        from app.platform import interaction_log

                        # Intentionally synchronous-await in async triage: same
                        # pattern as the human-reply path below. outcome is the
                        # measurable vocabulary (hard_bounce/soft_bounce/complaint).
                        await interaction_log.record(
                            channel="email",
                            direction="in",
                            phone="",
                            email=bounced_email or frm or "",
                            body_summary=(body or subj or "")[:200],
                            outcome=delivery_kind,
                            meta={
                                "delivery_report": True,
                                "from": frm,
                                "kind": delivery_kind,
                            },
                        )
                    except Exception:
                        pass
                    _mark_imap_seen(M, i)
                    continue
                # AUTO-ACK GUARD (2026-07-07): auto-acknowledgement ≠ human reply —
                # LLM classify se PEHLE drop (fake-"interested" + token-burn fix;
                # known-prospect pe bhi lagta, junk-guard ke ulat).
                if _is_auto_ack(msg, subj):
                    res["skipped"] += 1
                    res["auto_ack"] = res.get("auto_ack", 0) + 1
                    _mark_imap_seen(M, i)
                    continue
                # CASE-CLOSURE GUARD (2026-07-25): ticketing auto-responder that
                # CLOSES a case ("Not required as of now. Hence, case is closed.")
                # was classifying as "interested" — the opposite of the message.
                # 292 of 304 all-time "interested" rows came from one such sender.
                # LLM classify se PEHLE drop.
                if _is_case_closure(subj, body):
                    res["skipped"] += 1
                    res["case_closure"] = res.get("case_closure", 0) + 1
                    _mark_imap_seen(M, i)
                    continue
                # SPAM CONTENT GUARD (2026-07-15): betting/gambling vocab in
                # subject/body = spam, LLM classify se PEHLE drop (Reddy Anna
                # "interested" fake-hot fix — 07-14 audit).
                if _is_spam_content(subj, body):
                    res["skipped"] += 1
                    res["spam_content"] = res.get("spam_content", 0) + 1
                    _mark_imap_seen(M, i)
                    continue
                # Operator blocklist (REPLY_SENDER_BLOCKLIST env CSV) — hard skip.
                if _is_blocklisted(frm):
                    res["skipped"] += 1
                    res["blocklisted"] = res.get("blocklisted", 0) + 1
                    _mark_imap_seen(M, i)
                    continue
                # ── COMPLIANCE-FIRST OPT-OUT (2026-07-25) ───────────────────────
                # MUST run before the junk/bulk guard. That guard drops on
                # `p is None and _is_bulk_sender(...)` — so an explicit STOP /
                # REMOVE / UNSUBSCRIBE from anyone we do not already hold as a
                # prospect was discarded before classification ever ran, and no
                # suppression was written. An opt-out request is legally binding
                # whether or not the sender is in our database.
                #
                # Deterministic recognizer only — no LLM. Junk mail is still junk;
                # we merely refuse to throw away the compliance signal inside it.
                if _is_explicit_optout(subj, body):
                    _optout_email = (frm or "").strip().lower()
                    if _optout_email:
                        try:
                            from app.platform import email_unsub

                            _pid = str((p or {}).get("id") or (p or {}).get("pid") or "")
                            # Scope discipline: with a known prospect we have the
                            # identity needed for a cross-channel opt-out. Without
                            # one we know ONLY the address, so we suppress that
                            # exact destination and record an exception — we do NOT
                            # invent a broader permanent record the evidence does
                            # not support.
                            # Known prospect -> settled cross-channel opt-out.
                            # Unknown -> QUARANTINE: it blocks sending just as
                            # hard, but stays visibly unresolved so an admin is
                            # prompted to reconcile identity. Writing a permanent
                            # record here would make an unreviewed guess look
                            # like a verified decision.
                            _scope = (
                                email_unsub.SCOPE_ALL_OUTREACH
                                if _pid
                                else email_unsub.SCOPE_QUARANTINE
                            )
                            email_unsub.suppress(
                                _optout_email,
                                reason="reply_unsubscribe",
                                scope=_scope,
                                prospect_id=_pid,
                                event_id=_reply_delivery_key(frm, _safe_thread_headers(msg)[0]),
                                source="reply_agent_precheck",
                            )
                            if not _pid:
                                _record_unresolved_optout(_optout_email, subj)
                        except Exception as _oe:
                            logger.warning("[reply_agent] pre-guard opt-out failed: %s", _oe)
                    res["unsubscribed"] = res.get("unsubscribed", 0) + 1
                    res["optout_precheck"] = res.get("optout_precheck", 0) + 1
                    _mark_imap_seen(M, i)
                    continue
                # JUNK GUARD (2026-06-12): unknown sender + bulk/marketing mail = skip.
                # Pehle PayU/Instamojo newsletters "interested" classify hoke FAKE deals
                # bana rahe the + har newsletter pe LLM classify/draft tokens jalte the.
                if p is None and _is_bulk_sender(frm, msg):
                    res["skipped"] += 1
                    _mark_imap_seen(M, i)
                    continue
                # SENDER FLOOD CAP (2026-07-07): same sender already `cap`+ draft-rows
                # = auto-responder loop; is run ke repeats bhi count hote (increment niche).
                if flood_cap and seen_counts.get(frm, 0) >= flood_cap:
                    res["skipped"] += 1
                    res["flooded"] = res.get("flooded", 0) + 1
                    _mark_imap_seen(M, i)
                    continue
                seen_counts[frm] = seen_counts.get(frm, 0) + 1
                intent = await _classify(subj, body)
                # LLM-guard (IFC, observe-only): scan UNTRUSTED inbound for prompt-injection.
                # Never blocks — flags the draft so the human reviewer does NOT act on
                # instructions embedded by a malicious sender. ph18/15-16 (llm-security skill).
                _inj = None
                _scan_status = "error"
                try:
                    from app.platform import llm_guard

                    _gs = llm_guard.scan(f"{subj}\n{body}", source="inbox")
                    if _gs.get("suspicious"):
                        _inj = _gs.get("signals")
                        _scan_status = "suspicious"
                        if llm_guard.enabled():
                            logger.warning(
                                "[reply_agent] LLM_GUARD: possible prompt-injection from %s "
                                "signals=%s — review draft, do NOT act on embedded instructions",
                                frm,
                                _inj,
                            )
                    else:
                        _scan_status = "clean"
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
                    # DURABLE CROSS-CHANNEL SUPPRESSION. Every outreach mail tells
                    # the recipient to "reply REMOVE" — but until now that reply
                    # only marked the prospect row dead. The address stayed
                    # mailable from any other prospect row and WhatsApp was
                    # untouched, so the opt-out mechanism we advertise did not
                    # actually work at the list level. Write the canonical
                    # ALL_OUTREACH row; `event_id` makes reprocessing the same
                    # message idempotent.
                    try:
                        from app.platform import email_unsub

                        _mid = _safe_thread_headers(msg)[0]
                        email_unsub.suppress(
                            frm or "",
                            reason="reply_unsubscribe",
                            scope=email_unsub.SCOPE_ALL_OUTREACH,
                            prospect_id=str(pid or ""),
                            event_id=(_reply_delivery_key(frm or "", _mid) if _mid else ""),
                            source="reply_agent",
                        )
                    except Exception as _sup_err:  # never break triage
                        # No address in the log line — this path handles PII.
                        logger.warning("[reply_agent] suppression write failed: %s", _sup_err)
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
                draft_source = "none"
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
                        draft_source = "llm"
                    elif intent in _HOT_INTENTS:
                        # Zero-manual mode: a transient free-LLM outage must not
                        # strand a qualified inbound message after IMAP is marked
                        # Seen. This bounded, promise-free acknowledgement is still
                        # subject to every delivery/compliance gate in the backlog.
                        draft = _safe_hot_reply_fallback(intent)
                        draft_source = "deterministic_fallback"
                        if draft:
                            res["drafted"] += 1

                at = datetime.now(timezone.utc).isoformat()
                message_id, references = _safe_thread_headers(msg)
                saved = _save_draft(
                    {
                        "from": frm,
                        "subject": subj,
                        "intent": intent,
                        "draft": draft,
                        "draft_source": draft_source,
                        "injection_flag": _inj,
                        "scan_status": _scan_status,
                        "channel": "email",
                        "message_id": message_id,
                        "references": references,
                        "delivery_key": _reply_delivery_key(frm, message_id),
                        "source_at": _source_received_at(msg, md),
                        "at": at,
                    }
                )
                if not saved:
                    raise RuntimeError("reply_draft_persist_failed")

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
                        if draft and not _inj and not auto_mode:
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
                        if auto_mode:
                            actions = []
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

                # Safe auto-send runs after IMAP processing so fresh and persisted
                # rows share one bounded, claimed, compliance-gated path.
                member = "swara" if intent in ("interested", "question") else "rohan"
                _notify(member, f"reply_{intent}", f"{frm}: {subj[:60]}")
                _mark_imap_seen(M, i)
            except Exception as exc:
                logger.info("reply item err: %s", exc)
                res["skipped"] += 1
        try:
            M.close()
            M.logout()
        except Exception:
            pass
        auto_result = await run_auto_reply_backlog()
        res["auto_send"] = auto_result
        res["auto_sent"] = int(auto_result.get("sent") or 0)
        return res
    except Exception as exc:
        logger.info("run_reply_triage err: %s", exc)
        try:
            auto_result = await run_auto_reply_backlog()
            res["auto_send"] = auto_result
            res["auto_sent"] = int(auto_result.get("sent") or 0)
        except Exception:
            pass
        return {"error": str(exc), **res}


# ---------------------------------------------------------------------------
# AUTO-FORWARD POSITIVE REPLIES → CALLING QUEUE
# ---------------------------------------------------------------------------
# Enterprise-grade: interested/question replies ko calling queue me flag
# karta hai + WhatsApp follow-up link generate karta hai.
# NEVER raises — har step ka apna try/except.
# ---------------------------------------------------------------------------

import urllib.parse as _urlparse_reply


def auto_forward_positive_replies(limit: int = 10) -> dict[str, Any]:
    """Interested/question replies ko calling queue me flag karo.

    Gated: REPLY_AGENT (must be ON).  KABHI raise nahi karta.

    Returns: {"flagged_for_calling": n, "wa_links_generated": x, "skipped": y}
    """
    result: dict[str, Any] = {
        "flagged_for_calling": 0,
        "wa_links_generated": 0,
        "skipped": 0,
    }
    try:
        if not _flag("REPLY_AGENT"):
            return {"skipped": "REPLY_AGENT off"}

        from app.platform import prospector

        rows = prospector._read_all()
        # Interested/question replies with phone — calling candidates
        candidates = [
            r
            for r in rows
            if r.get("reply_intent") in ("interested", "question")
            and r.get("phone")
            and len("".join(c for c in str(r["phone"]) if c.isdigit())) >= 10
            and not r.get("calling_flagged")
        ]
        candidates.sort(key=lambda r: str(r.get("replied_at") or r.get("found_at") or ""))
        batch = candidates[:limit]

        for p in batch:
            try:
                pid = str(p.get("id"))
                phone10 = "".join(c for c in str(p["phone"]) if c.isdigit())[-10:]
                if len(phone10) < 10:
                    continue
                biz = str(p.get("business_name") or "Business").strip()
                niche = str(p.get("niche") or "business").replace("_", " ")
                intent = str(p.get("reply_intent") or "interested")

                # Flag for calling
                prospector.set_prospect_fields(
                    pid,
                    {
                        "calling_flagged": True,
                        "calling_priority": "high" if intent == "interested" else "medium",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                result["flagged_for_calling"] += 1

                # Generate WhatsApp follow-up link (1-click, ban-safe)
                wa_msg = (
                    f"Namaste {biz} ji 🙏 Aapne email pe interest dikhaya — "
                    f"shukriya! Agar baat karni ho to yahan se shuru karein: "
                    f"leadsgenai.in/audit"
                )
                wa_link = f"https://wa.me/91{phone10}?text={_urlparse_reply.quote(wa_msg)}"
                prospector.set_prospect_fields(
                    pid,
                    {
                        "wa_followup_generated": True,
                        "wa_followup_link": wa_link,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                result["wa_links_generated"] += 1

            except Exception as e:
                logger.debug(f"[reply_agent] auto_forward item failed: {e}")
                result["skipped"] += 1

        try:
            from app.platform.team import log_event

            log_event(
                "swara",
                "auto_forward_replies",
                (
                    f"{result['flagged_for_calling']} flagged for calling, "
                    f"{result['wa_links_generated']} WA links generated"
                ),
                status="ok",
                meta=result,
            )
        except Exception:
            pass

        logger.info(f"[reply_agent] auto_forward_positive_replies done: {result}")
        return result
    except Exception as e:
        logger.warning(f"[reply_agent] auto_forward_positive_replies failed: {e}")
        result["error"] = str(e)
        return result


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
    # SPAM CONTENT GUARD (2026-07-15): betting/gambling spam WhatsApp se bhi aata
    # hai — email path jaisa hi content-level drop before classify.
    if _is_spam_content("", txt):
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
    _auto = os.environ.get("WHATSAPP_AI_AUTOREPLY", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
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


def enqueue_action_card(rec: dict[str, Any]) -> bool:
    """Append a Hot Queue / inbox action card (inquiry, chase, etc.). Never raises."""
    try:
        if not isinstance(rec, dict):
            return False
        row = dict(rec)
        row.setdefault("at", datetime.now(timezone.utc).isoformat())
        return _save_draft(row)
    except Exception as e:
        logger.debug("enqueue_action_card err: %s", e)
        return False


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
    return hashlib.sha1(key.encode("utf-8", "ignore"), usedforsecurity=False).hexdigest()[:12]


def hq_id_for(row: dict) -> str:
    """Public wrapper for Hot Queue card ids (inquiry bridge / chase cards)."""
    return _hq_id(row or {})


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


async def _reply_auto_send_enabled() -> bool:
    """Env kill-switch OR audited Redis runtime flag. Fail-closed on doubt.

    ``REPLY_AUTO_SEND_HARD_OFF`` defaults ON (unset = blocked) so a live
    ``REPLY_AUTO_SEND=1`` cannot silently auto-mail when the hard-off env
    was never written. Owner must set HARD_OFF=0 to arm.
    """
    hard_off = os.getenv("REPLY_AUTO_SEND_HARD_OFF", "1").strip().lower()
    if hard_off not in {"0", "false", "no", "off"}:
        return False
    if _flag("REPLY_AUTO_SEND"):
        return True
    try:
        from app.infrastructure.feature_flags import feature_flags

        return bool(await feature_flags.is_enabled("reply_auto_send"))
    except Exception:
        return False


def _reply_agent_interaction_log_enabled() -> bool:
    """Auto-reply OUT interaction row — default ON (observability).

    Opt-out only: ``REPLY_AGENT_INTERACTION_LOG=0``. Same shape as
    ``ROUTINE_TASK_LEDGER`` — a default-OFF gate here would leave the
    operator-view blind again on the common path.
    """
    return os.environ.get("REPLY_AGENT_INTERACTION_LOG", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


async def _record_auto_reply_interaction(
    *,
    frm: str,
    body: str,
    intent: str,
    delivery_key: str,
    reason: str,
    prospect: dict | None = None,
) -> None:
    """Write outbound auto-reply to interaction_log after a successful send.

    Never raises. Never affects send / ``out["sent"]``. Failures log with
    ``exc_info`` — silent ``pass`` is what made interactions blind before.

    Also warns when ``interaction_log.record`` returns ``skipped`` (e.g.
    ``INTERACTION_LOG=0``) — that path does not raise, so without this check
    the operator-view stays blind with a green send counter.
    """
    if not _reply_agent_interaction_log_enabled():
        return
    if not delivery_key:
        return
    try:
        from app.platform import interaction_log

        p = prospect or {}
        # Only pass an explicit lead_id — never fall back to prospect ``id``.
        # Prospect ids are not always rows in ``leads`` (no-phone / dedupe miss);
        # stuffing them here recreates the dual-identity trap. Email resolution
        # inside interaction_log.record can still attach a real lead.
        lead_id = str(p.get("lead_id") or "").strip()
        prospect_id = str(p.get("id") or "").strip()
        meta: dict[str, Any] = {
            "source": "reply_agent",
            "delivery_key": delivery_key,
            "auto_send_reason": reason,
        }
        if prospect_id and prospect_id != lead_id:
            meta["prospect_id"] = prospect_id
        res = await interaction_log.record(
            channel="email",
            direction="out",
            phone=str(p.get("phone") or ""),
            email=frm,
            body_summary=(body or "")[:200],
            outcome=str(intent or "auto_reply")[:50],
            campaign_variant_id=str(p.get("campaign_variant_id") or ""),
            lead_id=lead_id,
            meta=meta,
        )
        if isinstance(res, dict) and res.get("skipped"):
            logger.warning(
                "[reply_agent] auto-reply interaction_log skipped (%s) delivery_key=%s",
                res.get("skipped"),
                delivery_key[:16],
            )
    except Exception:
        logger.warning(
            "[reply_agent] auto-reply interaction_log failed (delivery_key=%s)",
            delivery_key[:16],
            exc_info=True,
        )


async def _claim_reply_auto_send(key: str, daily_cap: int) -> int:
    """Atomically reserve message + daily attempt slot on REAL Redis only.

    Returns 1=claimed, 0=duplicate/unavailable, -1=daily cap reached.
    """
    try:
        from app.cache import InMemoryCache, get_redis_client

        redis = await get_redis_client()
        if redis is None or isinstance(redis, InMemoryCache):
            return 0
        if not await redis.ping():
            return 0
        day = datetime.now(timezone.utc).date().isoformat()
        script = """
        if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
        local used = tonumber(redis.call('GET', KEYS[2]) or '0')
        if used >= tonumber(ARGV[1]) then return -1 end
        redis.call('SET', KEYS[1], 'attempted', 'EX', ARGV[2], 'NX')
        redis.call('INCR', KEYS[2])
        redis.call('EXPIRE', KEYS[2], ARGV[3])
        return 1
        """
        return int(
            await redis.eval(
                script,
                2,
                f"reply:auto-send:{key}",
                f"reply:auto-send:attempts:{day}",
                int(daily_cap),
                7776000,
                129600,
            )
        )
    except Exception:
        return 0


async def _release_unattempted_reply_claim(key: str) -> bool:
    """Undo reservation only before provider invocation (therefore definitely safe)."""
    try:
        from app.cache import InMemoryCache, get_redis_client

        redis = await get_redis_client()
        if redis is None or isinstance(redis, InMemoryCache) or not await redis.ping():
            return False
        day = datetime.now(timezone.utc).date().isoformat()
        script = """
        if redis.call('GET', KEYS[1]) ~= 'attempted' then return 0 end
        redis.call('DEL', KEYS[1])
        local used = tonumber(redis.call('GET', KEYS[2]) or '0')
        if used > 0 then redis.call('DECR', KEYS[2]) end
        return 1
        """
        return bool(
            await redis.eval(
                script,
                2,
                f"reply:auto-send:{key}",
                f"reply:auto-send:attempts:{day}",
            )
        )
    except Exception:
        return False


def _update_draft_fields(hq_id: str, updates: dict[str, Any]) -> bool:
    """Lock + atomic targeted rewrite, preserving malformed/unknown JSONL lines."""
    if not hq_id or not os.path.exists(_DRAFTS_FILE):
        return False
    try:
        from app.utils.file_lock import file_lock

        with file_lock(_DRAFTS_FILE) as locked:
            if not locked:
                return False
            changed = False
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
                    if _hq_id(row) == hq_id:
                        row.update(updates)
                        lines.append(json.dumps(row, ensure_ascii=False))
                        changed = True
                    else:
                        lines.append(raw)
            if not changed:
                return False
            tmp = f"{_DRAFTS_FILE}.tmp.{os.getpid()}"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            os.replace(tmp, _DRAFTS_FILE)
            return True
    except Exception as exc:
        logger.debug("auto-send state update err: %s", exc)
        return False


def _reply_age_days(row: dict[str, Any]) -> int | None:
    try:
        raw = str(row.get("source_at") or row.get("at") or "")
        at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - at).days)
    except Exception:
        return None


def _stale_reengagement_body() -> str:
    return (
        "Namaste, aapka reply time par pick nahi ho paya — delay ke liye sorry.\n\n"
        "Agar AI marketing audit ya demo abhi bhi relevant hai, main details yahin share "
        "kar sakta hoon. Agar ab relevant nahi hai, bas ‘no’ reply karein; hum aage "
        "follow-up nahi karenge."
    )


async def _send_reply_email(
    to_email: str, subject: str, body: str, headers: dict[str, str]
) -> bool:
    import html

    from app.integrations.email_sender import EmailSender

    safe_html = html.escape(body).replace("\n", "<br>")
    return bool(
        await EmailSender().send_email(
            [to_email], subject, body, html_body=f"<p>{safe_html}</p>", extra_headers=headers
        )
    )


async def run_auto_reply_backlog(
    *,
    limit: int | None = None,
    send_fn=None,
    claim_fn=None,
    release_unattempted_fn=None,
) -> dict[str, Any]:
    """Send safe known-prospect email replies and close their Hot Queue rows."""
    out: dict[str, Any] = {
        "enabled": False,
        "seen": 0,
        "sent": 0,
        "failed": 0,
        "claimed_elsewhere": 0,
        "blocked_injection": 0,
        "blocked_suppressed": 0,
        "blocked_unverified": 0,
        "skipped_unknown": 0,
        "expired": 0,
        "stale_reengagement": 0,
    }
    try:
        is_enabled = await _reply_auto_send_enabled()
        out["enabled"] = is_enabled
        if not is_enabled:
            return out
        send_fn = send_fn or _send_reply_email
        claim_fn = claim_fn or _claim_reply_auto_send
        release_unattempted_fn = release_unattempted_fn or _release_unattempted_reply_claim
        try:
            cap = max(1, min(int(os.getenv("REPLY_AUTO_SEND_DAILY_CAP", "5") or 5), 25))
            batch = max(1, min(int(limit or os.getenv("REPLY_AUTO_SEND_BATCH", "3") or 3), 5))
        except Exception:
            cap, batch = 5, 3
        # list_drafts is newest-first; first row per sender is the only eligible one.
        rows = list_drafts(limit=100000)
        today = datetime.now(timezone.utc).date().isoformat()
        sent_today = sum(1 for row in rows if str(row.get("auto_sent_at") or "").startswith(today))
        remaining = batch
        out.update({"daily_cap": cap, "sent_today": sent_today})
        if remaining <= 0:
            out["skipped"] = "daily_cap"
            return out
        pmap = _full_prospect_map()
        handled_senders: set[str] = set()
        for row in rows:
            if remaining <= 0:
                break
            if not await _reply_auto_send_enabled():
                out["skipped"] = "hard_off_or_disabled"
                break
            frm = str(row.get("from") or "").strip().lower()
            if not frm or frm in handled_senders:
                continue
            handled_senders.add(frm)
            if row.get("channel") not in (None, "", "email"):
                continue
            if row.get("intent") not in _HOT_INTENTS or not str(row.get("draft") or "").strip():
                continue
            if row.get("hq_status") == "done" or row.get("auto_send_status") in {
                "sent",
                "blocked",
                "expired",
                "attempting",
                "ambiguous",
            }:
                continue
            out["seen"] += 1
            hq_id = _hq_id(row)
            prospect = pmap.get(frm) or {}
            if not prospect.get("emailed_at"):
                out["skipped_unknown"] += 1
                continue
            if row.get("injection_flag"):
                out["blocked_injection"] += 1
                _update_draft_fields(
                    hq_id,
                    {
                        "auto_send_status": "blocked",
                        "auto_send_reason": "injection",
                        "hq_status": "done",
                    },
                )
                continue
            try:
                from app.platform import email_unsub

                suppressed = bool(email_unsub.is_suppressed(frm))
            except Exception:
                suppressed = True
            if suppressed:
                out["blocked_suppressed"] += 1
                _update_draft_fields(
                    hq_id,
                    {
                        "auto_send_status": "blocked",
                        "auto_send_reason": "suppressed",
                        "hq_status": "done",
                    },
                )
                continue
            age_days = _reply_age_days(row)
            if age_days is None or age_days > 30:
                out["expired"] += 1
                _update_draft_fields(
                    hq_id,
                    {"auto_send_status": "expired", "auto_send_reason": "age", "hq_status": "done"},
                )
                continue
            stale = age_days >= 7
            delivery_key = str(row.get("delivery_key") or "").strip()
            if not delivery_key:
                delivery_key = _reply_delivery_key(frm, str(row.get("message_id") or ""))
            if stale and not delivery_key:
                # Historic rows predate Message-ID persistence. Fixed-copy re-engagement
                # is limited to one stable sender claim, never one claim per processing row.
                delivery_key = _reply_delivery_key(frm, "<stale-reengagement>")
            if not stale and (
                not row.get("source_at") or row.get("scan_status") != "clean" or not delivery_key
            ):
                out["blocked_unverified"] += 1
                _update_draft_fields(
                    hq_id,
                    {
                        "auto_send_status": "blocked",
                        "auto_send_reason": "unverified_source_or_scan",
                        "hq_status": "done",
                    },
                )
                continue
            claim = int(await claim_fn(delivery_key, cap))
            if claim == -1:
                out["skipped"] = "daily_cap"
                break
            if claim != 1:
                out["claimed_elsewhere"] += 1
                continue
            remaining -= 1
            body = _stale_reengagement_body() if stale else str(row.get("draft") or "").strip()
            subject = str(row.get("subject") or "Quick follow-up").strip()
            if not subject.lower().startswith("re:"):
                subject = f"Re: {subject}"
            message_id = str(row.get("message_id") or "").strip()
            references = str(row.get("references") or "").strip()
            headers: dict[str, str] = {}
            if message_id:
                headers["In-Reply-To"] = message_id
                headers["References"] = f"{references} {message_id}".strip()
            headers["Message-ID"] = f"<reply-{delivery_key}@leadsgenai.in>"
            attempts = int(row.get("auto_send_attempts") or 0) + 1
            if not _update_draft_fields(
                hq_id,
                {
                    "auto_send_status": "attempting",
                    "auto_send_attempts": attempts,
                    "auto_send_attempted_at": datetime.now(timezone.utc).isoformat(),
                    "delivery_key": delivery_key,
                },
            ):
                out["failed"] += 1
                await release_unattempted_fn(delivery_key)
                out["skipped"] = "state_lock"
                break
            try:
                ok = bool(await send_fn(frm, subject, body, headers))
            except Exception:
                ok = False
            if ok:
                sent_at = datetime.now(timezone.utc).isoformat()
                _reason = "stale_reengagement" if stale else "fresh_reply"
                _update_draft_fields(
                    hq_id,
                    {
                        "auto_send_status": "sent",
                        "auto_sent_at": sent_at,
                        "auto_send_attempts": attempts,
                        "auto_send_reason": _reason,
                        "hq_status": "done",
                        "hq_done_at": sent_at,
                    },
                )
                out["sent"] += 1
                out["stale_reengagement"] += int(stale)
                logger.info("[reply_agent] safe auto-reply sent (intent=%s)", row.get("intent"))
                # Observability (WI-CP2-AUTO-REPLY): inbound already records via
                # interaction_log; outbound auto-send must too — same chokepoint
                # as auto_sent_at so draft truth and operator-view cannot drift.
                await _record_auto_reply_interaction(
                    frm=frm,
                    body=body,
                    intent=str(row.get("intent") or ""),
                    delivery_key=delivery_key,
                    reason=_reason,
                    prospect=prospect,
                )
            else:
                _update_draft_fields(
                    hq_id,
                    {
                        "auto_send_status": "ambiguous",
                        "auto_send_attempts": attempts,
                        "auto_send_last_failure_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                out["failed"] += 1
        return out
    except Exception as exc:
        logger.info("auto reply backlog err: %s", exc)
        out["error"] = type(exc).__name__
        return out


# STRUCTURAL SENDER NOISE (read-path): WhatsApp status/broadcast + DMARC
# report senders kabhi human reply nahi hote. Draft rows in-sa se saal mein
# nahi aate (drop classify se pehle hota hai) — yeh legacy rows ke liye hai.
_SENDER_NOISE = {"status", "@broadcast", "noreply-dmarc-support@google.com"}


def _is_noise_row(r: dict) -> bool:
    """Historic draft read-path noise guard. Never raises."""
    try:
        frm = str((r or {}).get("from") or "").strip().lower()
        if frm == "status" or "@broadcast" in frm:
            return True
        if frm in _SENDER_NOISE:
            return True
        if _is_blocklisted(frm):
            return True
        # Legacy drafts body ko `draft` key me rakhte hain (text/body_snippet
        # nahi) — woh bhi scan karo warna closure/spam patterns miss hote hain.
        subj_body = (
            f"{(r or {}).get('subject') or ''}\n"
            f"{(r or {}).get('text') or (r or {}).get('body_snippet') or (r or {}).get('draft') or ''}"
        )
        if _AUTO_ACK_RE.search(subj_body):
            return True
        # CASE-CLOSURE retro-hide (2026-08-11): closure guard classify-time pe
        # hai, par 2026-07-25 se PEHLE saved adityabirla ticketing rows
        # ("Not related to Birla Opus. Hence, closed." etc.) read-path pe bhi
        # Hot Queue me fake-hot dikhti rehti thin. Same regex = read-path hide.
        if _is_case_closure(str((r or {}).get("subject") or ""), subj_body):
            return True
        # SPAM CONTENT (2026-07-15): pehle se saved betting-spam drafts bhi
        # read-path pe hide ho jaayein (Hot Queue retro-clean).
        if _is_spam_content("", subj_body):
            return True
    except Exception:
        pass
    return False


def _calling_flagged_cards(
    limit: int,
    *,
    seen_from: set[str],
    seen_phone: set[str],
) -> list[dict]:
    """Synthetic Hot Queue cards from prospector calling_flagged / high-intent.

    These are NOT draft rows. Done/Park persist on the prospect via
    ``auto_outreach.mark_hot_queue_candidate``. Never raises.
    """
    out: list[dict] = []
    try:
        from app.platform import auto_outreach

        for cand in auto_outreach.hot_queue_candidates(limit=max(1, int(limit) * 2)):
            email = str(cand.get("email") or "").strip().lower()
            phone = str(cand.get("phone") or "")
            digits = "".join(c for c in phone if c.isdigit())
            phone10 = digits[-10:] if len(digits) >= 10 else ""
            if email and email in seen_from:
                continue
            if phone10 and phone10 in seen_phone:
                continue
            pid = str(cand.get("id") or "").strip()
            if not pid:
                continue
            biz = str(cand.get("business_name") or "ji").strip() or "ji"
            # BLK-01 (2026-08-22): high-intent card me PAYMENT PATH embed karo.
            # Sirf audit pitch dena adhoora tha — warm lead ko UPI link bhi chahiye.
            # _interested_offer_block fail-open hai (UPI unarmed -> ""); jab empty
            # ho to link BILKUL pehle jaisa rehta hai (zero behaviour change).
            offer = ""
            try:
                offer = _interested_offer_block(biz)
            except Exception:
                offer = ""
            wa = str(cand.get("wa_followup_link") or "")
            if not wa and phone10:
                from urllib.parse import quote

                msg = (
                    f"Namaste {biz} ji — LeadGen AI se baat karni ho to yahan "
                    "reply karein."
                )
                if offer:
                    msg = f"{msg}{offer}"
                wa = f"https://wa.me/91{phone10}?text=" + quote(msg)
            elif wa and offer and phone10:
                # Pre-computed follow-up link (audit pitch) me bhi payment path
                # jodo: text= param decode -> append -> re-encode. Koi bhi issue
                # par original link hi rehta hai (fail-open, never raise).
                try:
                    from urllib.parse import quote_plus, unquote_plus

                    base, sep, qs = wa.partition("?")
                    if sep:
                        kept: list[str] = []
                        txt: str | None = None
                        for part in qs.split("&"):
                            if part.startswith("text="):
                                txt = unquote_plus(part[5:])
                            else:
                                kept.append(part)
                        if txt is None:
                            # NOTE: urlencode() yahan TypeError deta hai (single
                            # string valid input nahi) — quote_plus hi sahi hai.
                            kept.append("text=" + quote_plus(offer.strip()))
                        elif offer not in txt:
                            kept.append("text=" + quote_plus(txt + offer))
                        if kept:
                            wa = f"{base}?{'&'.join(kept)}"
                except Exception:
                    pass
            out.append(
                {
                    "hq_id": f"callflag:{pid}",
                    "channel": "calling_flagged",
                    "intent": "interested",
                    "from": email or phone,
                    "phone": phone,
                    "business_name": cand.get("business_name") or "",
                    "niche": cand.get("niche") or "",
                    "city": cand.get("city") or "",
                    "text": f"calling_flagged reason={cand.get('reason') or '-'}",
                    "draft": (
                        "High-intent prospect (reply/calling-flag) — owner: Call ya 1-click WA. "
                        "Cold auto-WA OFF. Done dabao after action."
                    ),
                    "wa_link": wa,
                    "hq_source": "calling_flagged",
                    "owner_action": "call_or_wa_draft_then_done",
                    "sla_state": "n/a",
                    "at": "",
                    "prospect_id": pid,
                }
            )
            if email:
                seen_from.add(email)
            if phone10:
                seen_phone.add(phone10)
            if len(out) >= max(1, int(limit)):
                break
    except Exception as exc:
        logger.debug("calling_flagged cards err: %s", exc)
    return out


def hot_queue(
    limit: int = 50,
    intents: tuple = _HOT_INTENTS,
    scope: str = "boss",
) -> list[dict]:
    """Prioritized outreach-reply queue: filter hot intents, drop handled/noise,
    require email senders to match an actually-emailed prospect, dedupe by sender
    (latest wins), then join prospect context. NEVER raises — [] on failure.

    scope:
      boss  — default: hide done + admin_pending (boss actionable queue)
      admin — only admin_pending (parked for human admin)
      all   — everything except done (council lookup / full review)
    """
    try:
        scope_n = str(scope or "boss").strip().lower()
        if scope_n not in ("boss", "admin", "all"):
            scope_n = "boss"
        rows = [r for r in list_drafts(limit=100000) if r.get("intent") in intents]
        rows = [r for r in rows if (r.get("hq_status") or "") != "done"]
        if scope_n == "boss":
            rows = [r for r in rows if (r.get("hq_status") or "") != "admin_pending"]
        elif scope_n == "admin":
            rows = [r for r in rows if (r.get("hq_status") or "") == "admin_pending"]
        rows = [r for r in rows if not _is_noise_row(r)]
        pmap = _full_prospect_map()
        # IMAP triage also sees vendor onboarding, billing and system alerts. An
        # LLM may label those interested/question, but they are not replies to
        # our outreach. Keep genuine 1:1 WhatsApp messages; email enters this
        # revenue queue only when the sender maps to a prospect we actually
        # emailed. Other drafts remain visible in the general Reply Drafts tab.
        rows = [
            r
            for r in rows
            if r.get("channel") in ("whatsapp", "inquiry", "payment_chase")
            or bool((pmap.get(str(r.get("from") or "").strip().lower()) or {}).get("emailed_at"))
        ]
        latest: dict[str, dict] = {}
        for r in sorted(rows, key=lambda x: str(x.get("at") or "")):
            sender = str(r.get("from") or "").strip().lower() or _hq_id(r)
            latest[sender] = r
        out = sorted(latest.values(), key=lambda x: str(x.get("at") or ""), reverse=True)
        now = datetime.now(timezone.utc)
        final: list[dict] = []
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
                r["wa_link"] = f"https://wa.me/{wa_num}" + (f"?text={quote(msg)}" if msg else "")
            else:
                r["wa_link"] = ""
            if r.get("channel") == "whatsapp" and not r["wa_link"]:
                continue
            r["business_name"] = r.get("business_name") or p.get("business_name") or ""
            r["niche"] = r.get("niche") or p.get("niche") or ""
            r["city"] = r.get("city") or p.get("city") or ""
            try:
                at = datetime.fromisoformat(str(r.get("at") or "").replace("Z", "+00:00"))
                if at.tzinfo is None:
                    at = at.replace(tzinfo=timezone.utc)
                age_s = max(0, int((now - at).total_seconds()))
                r["age_days"] = age_s // 86400
                r["age_minutes"] = age_s // 60
            except Exception:
                r["age_days"] = None
                r["age_minutes"] = None
            ch = str(r.get("channel") or "")
            # Inquiry 5-min owner SLA (inquiry_hq_bridge._TARGET_5MIN); others informational only.
            if ch == "inquiry" and r.get("age_minutes") is not None:
                r["sla_target_min"] = 5
                r["sla_state"] = "breach" if int(r["age_minutes"]) > 5 else "ok"
            elif ch == "payment_chase":
                r["sla_target_min"] = None
                r["sla_state"] = "payment_truth"
            else:
                r["sla_target_min"] = None
                r["sla_state"] = "n/a"
            if ch == "payment_chase":
                r["owner_action"] = "chase_payment_upi_proof"
            elif ch == "inquiry":
                r["owner_action"] = "call_or_wa_draft_then_done"
            else:
                r["owner_action"] = "reply_or_call_then_done"
            final.append(r)
            if len(final) >= max(1, limit):
                break
        # Pay-truth chase cards (converted without ledger) — owner action, ban-safe wa.me.
        if scope_n in ("boss", "all") and len(final) < max(1, limit):
            try:
                from app.platform.sales_autopilot import pay_truth as _pt

                for card in _pt.unpaid_chase_cards(limit=max(1, limit) - len(final)):
                    card.setdefault("sla_state", "payment_truth")
                    card.setdefault("owner_action", "chase_payment_upi_proof")
                    final.append(card)
            except Exception:
                pass
        # Calling-flagged / high-intent prospects that never got a draft row —
        # otherwise auto_forward_positive_replies writes a flag nobody sees.
        if scope_n in ("boss", "all") and len(final) < max(1, limit):
            try:
                final.extend(
                    _calling_flagged_cards(
                        limit=max(1, limit) - len(final),
                        seen_from={str(r.get("from") or "").strip().lower() for r in final},
                        seen_phone={
                            "".join(c for c in str(r.get("phone") or "") if c.isdigit())[-10:]
                            for r in final
                            if len("".join(c for c in str(r.get("phone") or "") if c.isdigit()))
                            >= 10
                        },
                    )
                )
            except Exception:
                pass
        return final[: max(1, limit)]
    except Exception as exc:
        logger.debug("hot_queue err: %s", exc)
        return []


def hot_queue_summary(items: list[dict] | None, scope: str = "boss") -> dict:
    """Operator-facing envelope for /app/inbox — idle reason + SLA counts. Never raises."""
    rows = list(items or [])
    scope_n = str(scope or "boss").strip().lower()
    inquiry_n = sum(1 for r in rows if str(r.get("channel") or "") == "inquiry")
    chase_n = sum(1 for r in rows if str(r.get("channel") or "") == "payment_chase")
    breach_n = sum(1 for r in rows if str(r.get("sla_state") or "") == "breach")
    ages = [int(r["age_minutes"]) for r in rows if r.get("age_minutes") is not None]
    out: dict = {
        "count": len(rows),
        "scope": scope_n,
        "inquiry_count": inquiry_n,
        "payment_chase_count": chase_n,
        "sla_breach_count": breach_n,
        "oldest_age_minutes": max(ages) if ages else None,
        "idle_reason": None,
        "next_owner_hint": None,
    }
    if rows:
        if breach_n:
            out["next_owner_hint"] = f"{breach_n} inquiry SLA >5min — pehle unhe Call/WA karo"
        elif chase_n:
            out["next_owner_hint"] = "Payment-truth chase cards — UPI proof ke bina PAID mat bolo"
        else:
            out["next_owner_hint"] = "Top card se Call/WA draft → Done"
        return out
    if scope_n == "admin":
        out["idle_reason"] = "admin_pending_empty"
        out["next_owner_hint"] = "Koi parked card nahi — Boss queue check karo"
    else:
        out["idle_reason"] = "queue_empty_no_hot_drafts"
        out["next_owner_hint"] = (
            "Koi unhandled interested/inquiry/chase nahi — "
            "reply_triage + website inquiry bridge + autopilot refill observe karo"
        )
    return out


def mark_handled(hq_id: str) -> bool:
    """1-click 'Done' — set hq_status=done on the matching draft row (in-place
    rewrite, temp-file + atomic replace). False if id not found / any error.

    Synthetic pay-chase cards (``paychase:<prospect_id>``) clear via sales_autopilot
    store steps — they are not draft rows.
    """
    hq_id = (hq_id or "").strip()
    if not hq_id:
        return False
    if hq_id.startswith("paychase:"):
        try:
            from app.platform.sales_autopilot import pay_truth

            return bool(pay_truth.mark_paychase_done(hq_id))
        except Exception as exc:
            logger.debug("mark_handled paychase err: %s", exc)
            return False
    if hq_id.startswith("callflag:"):
        try:
            from app.platform import auto_outreach

            return bool(auto_outreach.mark_hot_queue_candidate(hq_id.split(":", 1)[1], done=True))
        except Exception as exc:
            logger.debug("mark_handled callflag err: %s", exc)
            return False
    if not os.path.exists(_DRAFTS_FILE):
        return False
    try:
        row = next(
            (
                item
                for item in list_drafts(limit=100000)
                if _hq_id(item) == hq_id and (item.get("hq_status") or "") != "done"
            ),
            None,
        )
        if row is None:
            return False
        return _update_draft_fields(
            hq_id,
            {
                "hq_status": "done",
                "hq_done_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as exc:
        logger.debug("mark_handled err: %s", exc)
        return False


def park_for_admin(hq_id: str, note: str = "") -> bool:
    """Boss unclear / council PARK_ADMIN — queue se boss view hatao, admin scope me rakho."""
    hq_id = (hq_id or "").strip()
    if not hq_id:
        return False
    if hq_id.startswith("paychase:"):
        try:
            from app.platform.sales_autopilot import pay_truth

            return bool(pay_truth.mark_paychase_parked(hq_id))
        except Exception as exc:
            logger.debug("park_for_admin paychase err: %s", exc)
            return False
    if hq_id.startswith("callflag:"):
        try:
            from app.platform import auto_outreach

            return bool(auto_outreach.mark_hot_queue_candidate(hq_id.split(":", 1)[1], parked=True))
        except Exception as exc:
            logger.debug("park_for_admin callflag err: %s", exc)
            return False
    if not os.path.exists(_DRAFTS_FILE):
        return False
    try:
        row = next(
            (
                item
                for item in list_drafts(limit=100000)
                if _hq_id(item) == hq_id and (item.get("hq_status") or "") != "done"
            ),
            None,
        )
        if row is None:
            return False
        return _update_draft_fields(
            hq_id,
            {
                "hq_status": "admin_pending",
                "hq_admin_note": str(note or "").strip()[:300],
                "hq_parked_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as exc:
        logger.debug("park_for_admin err: %s", exc)
        return False


__all__ = [
    "run_reply_triage",
    "run_auto_reply_backlog",
    "whatsapp_reply",
    "list_drafts",
    "hot_queue",
    "mark_handled",
    "park_for_admin",
    "make_hq_done_token",
    "verify_hq_done_token",
    "classify_delivery_report",
    "_DELIVERY_OUTCOMES",
]
