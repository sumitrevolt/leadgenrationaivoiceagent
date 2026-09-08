"""Unified Conversation Inbox v1 (GHL-signature, hamara drafts-only flavour).

Kyun: replies/chats/inquiries 3 alag jsonl stores me bikhri hain — ek jagah
thread-view chahiye taaki human 1-click follow-up kar sake. Yeh module sirf
AGGREGATE karta hai (read-only over existing stores) + manual reply DRAFTS
likhta hai — KOI auto-send nahi (ban-safe).

Sources (sab defensive — file missing/corrupt = silently empty):
- data/reply_drafts.jsonl        (reply_agent — email/whatsapp replies + AI drafts)
- data/widget_chats.jsonl        (web chat widget — dusra agent aaj bana raha;
                                  schema unknown → multi-key defensive parse)
- data/inquiries.jsonl           (public_site — website/mini-site inquiries)
- data/conversation_replies.jsonl (HAMARE manual reply drafts — yahi ek write)

Thread key = phone digits (last-10) > email > session id. Never raises.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_REPLY_DRAFTS = os.path.join("data", "reply_drafts.jsonl")
_WIDGET_CHATS = os.path.join("data", "widget_chats.jsonl")
_INQUIRIES = os.path.join("data", "inquiries.jsonl")
_OUR_REPLIES = os.path.join("data", "conversation_replies.jsonl")


def _CALL_TRANSCRIPTS_DIR() -> str:
    """Call transcripts dir — resolved per call, never frozen at import."""
    from app.platform.runtime_recording_paths import call_transcripts_dir

    return str(call_transcripts_dir())


_CADENCE_RUNS = os.path.join("data", "cadence_runs.jsonl")
_INTERACTIONS = os.path.join("data", "interactions.jsonl")

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        if not os.path.isfile(path):
            return out
        with open(path, encoding="utf-8") as f:
            for ln in f:
                try:
                    rec = json.loads(ln)
                    if isinstance(rec, dict):
                        out.append(rec)
                except Exception:
                    continue
    except Exception as e:
        logger.debug(f"[conv] read {path} failed: {e}")
    return out


def _phone_digits(raw: Any) -> str:
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else ""


def _email_of(raw: Any) -> str:
    m = _EMAIL_RE.search(str(raw or ""))
    return m.group(0).lower() if m else ""


def thread_key(rec: dict[str, Any]) -> str:
    """Stable thread key — phone > email > session. '' = unkeyable (skip).

    Pure function (tests ke liye)."""
    try:
        for f in ("phone", "from_number", "from", "contact", "to"):
            ph = _phone_digits(rec.get(f))
            if ph:
                return f"p:{ph}"
        for f in ("email", "from", "to", "contact"):
            em = _email_of(rec.get(f))
            if em:
                return f"e:{em}"
        for f in ("session", "session_id", "sid", "visitor_id", "chat_id"):
            v = str(rec.get(f) or "").strip()
            if v:
                return f"s:{v[:60]}"
        return ""
    except Exception:
        return ""


def _msg(
    key: str,
    at: str,
    channel: str,
    direction: str,
    text: str,
    name: str = "",
    intent: str = "",
    draft: str = "",
) -> dict[str, Any]:
    return {
        "key": key,
        "at": str(at or ""),
        "channel": channel,
        "direction": direction,  # in = unse aaya, draft = hamara taiyar jawab
        "text": str(text or "")[:2000],
        "name": str(name or "")[:120],
        "intent": str(intent or ""),
        "draft": str(draft or "")[:2000],
    }


def _collect_messages() -> list[dict[str, Any]]:
    """Saare stores se normalized messages (defensive per-source)."""
    msgs: list[dict[str, Any]] = []

    # 1) reply_agent drafts (email + whatsapp replies, AI draft saath me)
    try:
        # Legacy noise (status/@broadcast, DMARC, auto-ack, case-closure, spam)
        # ko conversation tab me bhi hide karo — same guard jo Hot Queue use
        # karti hai (2026-08-11 retro-hide; drafts write-path pe already drop).
        from app.platform.reply_agent import _is_noise_row

        for r in _read_jsonl(_REPLY_DRAFTS):
            if _is_noise_row(r):
                continue
            k = thread_key(r)
            if not k:
                continue
            channel = r.get("channel") or "email"
            text = r.get("text") or r.get("subject") or ""
            msgs.append(
                _msg(
                    k,
                    r.get("at"),
                    str(channel),
                    "in",
                    str(text),
                    intent=str(r.get("intent") or ""),
                    draft=str(r.get("draft") or ""),
                )
            )
    except Exception as e:
        logger.debug(f"[conv] reply_drafts parse: {e}")

    # 2) web chat widget (schema dusre agent ka — multi-key defensive)
    try:
        for r in _read_jsonl(_WIDGET_CHATS):
            k = thread_key(r)
            if not k:
                continue
            # single-message record ya {messages:[...]} dono handle karo
            inner = r.get("messages")
            if isinstance(inner, list) and inner:
                for m in inner:
                    if not isinstance(m, dict):
                        continue
                    role = str(m.get("role") or m.get("from") or "user")
                    msgs.append(
                        _msg(
                            k,
                            m.get("at") or m.get("ts") or r.get("at") or r.get("ts"),
                            "webchat",
                            "in" if role in ("user", "visitor", "customer") else "draft",
                            str(m.get("text") or m.get("message") or m.get("content") or ""),
                            name=str(r.get("name") or ""),
                        )
                    )
            else:
                txt = r.get("text") or r.get("message") or r.get("question") or ""
                if str(txt).strip():
                    msgs.append(
                        _msg(
                            k,
                            r.get("at") or r.get("ts") or r.get("created_at"),
                            "webchat",
                            "in",
                            str(txt),
                            name=str(r.get("name") or ""),
                            draft=str(r.get("reply") or r.get("answer") or ""),
                        )
                    )
    except Exception as e:
        logger.debug(f"[conv] widget_chats parse: {e}")

    # 3) website inquiries
    try:
        for r in _read_jsonl(_INQUIRIES):
            k = thread_key(r)
            if not k:
                continue
            parts = [str(r.get("message") or "").strip()]
            extra = " · ".join(
                str(r.get(f) or "") for f in ("niche", "city") if str(r.get(f) or "").strip()
            )
            text = (parts[0] or "Website inquiry") + (f" ({extra})" if extra else "")
            msgs.append(_msg(k, r.get("at"), "inquiry", "in", text, name=str(r.get("name") or "")))
    except Exception as e:
        logger.debug(f"[conv] inquiries parse: {e}")

    # 4) hamare manual reply drafts
    try:
        for r in _read_jsonl(_OUR_REPLIES):
            k = str(r.get("key") or "")
            if not k:
                continue
            msgs.append(
                _msg(
                    k,
                    r.get("at"),
                    str(r.get("channel") or "manual"),
                    "draft",
                    str(r.get("text") or ""),
                )
            )
    except Exception as e:
        logger.debug(f"[conv] our replies parse: {e}")

    # 5) voice call transcripts (disposition summary)
    try:
        tdir = _CALL_TRANSCRIPTS_DIR()
        if os.path.isdir(tdir):
            for fn in sorted(os.listdir(tdir), reverse=True)[:40]:
                if not fn.endswith(".jsonl"):
                    continue
                for r in _read_jsonl(os.path.join(tdir, fn))[:5]:
                    k = thread_key(
                        {
                            "phone": r.get("phone") or r.get("to"),
                            "email": r.get("email"),
                        }
                    )
                    if not k:
                        continue
                    outcome = str(r.get("outcome") or r.get("disposition") or "call")
                    summary = str(r.get("summary") or "")[:300]
                    if not summary and r.get("messages"):
                        summary = str((r.get("messages") or [{}])[-1].get("content", ""))[:200]
                    msgs.append(
                        _msg(
                            k,
                            r.get("ended_at") or r.get("at"),
                            "voice",
                            "out",
                            summary or f"Call {outcome}",
                            intent=outcome,
                        )
                    )
    except Exception as e:
        logger.debug(f"[conv] call_transcripts parse: {e}")

    # 6) cadence runs (multi-touch touches)
    try:
        for r in _read_jsonl(_CADENCE_RUNS):
            k = thread_key(r)
            if not k:
                continue
            msgs.append(
                _msg(
                    k,
                    r.get("at"),
                    str(r.get("channel") or "cadence"),
                    "draft",
                    str(r.get("action") or r.get("template") or "cadence step"),
                )
            )
    except Exception as e:
        logger.debug(f"[conv] cadence_runs parse: {e}")

    # 7) interaction log jsonl (enterprise flywheel timeline)
    try:
        for r in _read_jsonl(_INTERACTIONS):
            k = thread_key({"phone": r.get("phone"), "email": r.get("email")})
            if not k:
                continue
            msgs.append(
                _msg(
                    k,
                    r.get("occurred_at"),
                    str(r.get("channel") or "touch"),
                    str(r.get("direction") or "out"),
                    str(r.get("body_summary") or ""),
                    intent=str(r.get("outcome") or ""),
                )
            )
    except Exception as e:
        logger.debug(f"[conv] interactions parse: {e}")

    return msgs


def list_threads(limit: int = 50) -> list[dict[str, Any]]:
    """Threads newest-first: {key, channels, name, last_message, last_at, count}."""
    try:
        threads: dict[str, dict[str, Any]] = {}
        for m in sorted(_collect_messages(), key=lambda x: x.get("at") or ""):
            t = threads.setdefault(
                m["key"],
                {
                    "key": m["key"],
                    "channels": [],
                    "name": "",
                    "last_message": "",
                    "last_at": "",
                    "count": 0,
                },
            )
            t["count"] += 1
            if m["channel"] not in t["channels"]:
                t["channels"].append(m["channel"])
            if m.get("name") and not t["name"]:
                t["name"] = m["name"]
            if (m.get("at") or "") >= (t["last_at"] or ""):
                t["last_at"] = m.get("at") or ""
                t["last_message"] = (m.get("text") or m.get("draft") or "")[:160]
        rows = sorted(threads.values(), key=lambda t: t["last_at"] or "", reverse=True)
        return rows[: max(1, min(int(limit), 200))]
    except Exception as e:
        logger.warning(f"[conv] list_threads failed: {e}")
        return []


def get_thread(key: str) -> dict[str, Any]:
    """Ek thread ke saare messages (oldest-first) + contact info. Never raises."""
    try:
        key = (key or "").strip()
        msgs = [m for m in _collect_messages() if m["key"] == key]
        msgs.sort(key=lambda x: x.get("at") or "")
        contact: dict[str, Any] = {"key": key}
        if key.startswith("p:"):
            contact["phone"] = key[2:]
            contact["wa_link"] = f"https://wa.me/91{key[2:]}"
            contact["tel_link"] = f"tel:+91{key[2:]}"
        elif key.startswith("e:"):
            contact["email"] = key[2:]
            contact["mailto"] = f"mailto:{key[2:]}"
        for m in msgs:
            if m.get("name"):
                contact["name"] = m["name"]
                break
        return {"key": key, "contact": contact, "messages": msgs, "count": len(msgs)}
    except Exception as e:
        logger.warning(f"[conv] get_thread failed: {e}")
        return {"key": key, "contact": {}, "messages": [], "count": 0, "error": str(e)}


def add_manual_reply_draft(key: str, text: str, channel: str = "manual") -> dict[str, Any]:
    """Thread me human ka reply DRAFT save karo (auto-send NAHI — ban-safe).

    Human ise copy / wa.me / mailto se khud bhejta hai. Never raises.
    """
    try:
        key = (key or "").strip()
        text = (text or "").strip()
        if not key or not text:
            return {"error": "key aur text dono chahiye"}
        rec = {
            "key": key,
            "text": text[:2000],
            "channel": (channel or "manual")[:20],
            "at": _now(),
            "status": "draft",
        }
        os.makedirs(os.path.dirname(_OUR_REPLIES) or ".", exist_ok=True)
        with open(_OUR_REPLIES, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return {"ok": True, "reply": rec}
    except Exception as e:
        logger.warning(f"[conv] add_manual_reply_draft failed: {e}")
        return {"error": str(e)}


__all__ = ["thread_key", "list_threads", "get_thread", "add_manual_reply_draft"]
