"""Per-number WhatsApp conversation memory — inbound reply ko CONTEXT ke saath samajhne
ke liye.

THE GAP THIS CLOSES
-------------------
``reply_agent.whatsapp_reply()`` har inbound message ko ISOLATED classify/draft karta
tha (subject = "WhatsApp inbound", body = sirf current text — zero history). Isliye jab
customer kisi pichle sawaal ka JAWAAB deta tha, AI ko pata hi nahi hota tha ki kya poocha
gaya — woh phir se generic reply/same sawaal repeat kar deta ("samajh nahi pa raha /
phir se poochh raha hai"). Yeh module har turn (inbound + outbound) ko per-number thread
me persist karta hai, taaki classifier + draft ko pichli baat-cheet ka context mile.

DESIGN
------
- Append-only JSONL at ``data/wa_conversations.jsonl`` (``_CONV_FILE`` — tests override).
- Har row: ``{"from": <digits>, "dir": "in"|"out", "text": ..., "at": iso, "mid": ...}``.
- Per-number thread bounded (``_MAX_TURNS_PER_NUMBER``) taaki file na phoole.
- NEVER raises — memory ek best-effort context layer hai, kabhi reply-path crash na kare.
- Koi PII/secret nahi (numbers already inbound-webhook me aate hain; check_secrets clean).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_CONV_FILE = os.path.join("data", "wa_conversations.jsonl")

# Per-number thread cap — recent turns hi context ke liye chahiye. File-wide compaction
# tab hoti jab ek number ke turns is cap se zyada ho jaayein (append-heavy, prune-light).
_MAX_TURNS_PER_NUMBER = 40
_DEFAULT_CONTEXT_TURNS = 10


def _digits(number: str) -> str:
    """Normalise a WhatsApp id/number to last-10 digits (match across 91-prefix / @c.us)."""
    d = "".join(ch for ch in str(number or "") if ch.isdigit())
    return d[-10:] if len(d) >= 10 else d


def record(from_number: str, text: str, direction: str = "in", message_id: str = "") -> None:
    """Ek conversation turn append karo (inbound ya outbound). Best-effort, never raises."""
    key = _digits(from_number)
    txt = (text or "").strip()
    if not key or not txt:
        return
    row = {
        "from": key,
        "dir": "out" if str(direction).lower().startswith("out") else "in",
        "text": txt[:2000],
        "mid": (message_id or "").strip(),
        "at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        os.makedirs(os.path.dirname(_CONV_FILE) or ".", exist_ok=True)
        with open(_CONV_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("wa_conversation record err: %s", exc)


def _all_rows() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        if os.path.exists(_CONV_FILE):
            with open(_CONV_FILE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        pass
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("wa_conversation read err: %s", exc)
    return out


def thread(from_number: str, limit: int = _DEFAULT_CONTEXT_TURNS) -> list[dict[str, Any]]:
    """Ek number ki recent conversation turns (oldest -> newest). Never raises."""
    key = _digits(from_number)
    if not key:
        return []
    rows = [r for r in _all_rows() if _digits(r.get("from")) == key]
    return rows[-max(1, limit) :]


def history_messages(from_number: str, limit: int = _DEFAULT_CONTEXT_TURNS) -> list[dict[str, str]]:
    """LLM-ready role/content list (in -> 'user', out -> 'assistant'), oldest -> newest.

    reply_agent isko _draft ki PRIOR-turn conversation ke roop me deta hai (current
    message record hone se PEHLE call karke, taaki yeh sirf pichli baat-cheet ho).
    Never raises.
    """
    msgs: list[dict[str, str]] = []
    for r in thread(from_number, limit=limit):
        role = "assistant" if r.get("dir") == "out" else "user"
        content = str(r.get("text") or "").strip()
        if content:
            msgs.append({"role": role, "content": content})
    return msgs


def as_context_text(msgs: list[dict[str, str]] | None) -> str:
    """role/content list -> readable transcript ("Customer: .. / Hum: ..") for the
    classifier prompt. '' jab koi history nahi. Never raises."""
    if not msgs:
        return ""
    lines: list[str] = []
    for m in msgs:
        who = "Hum" if m.get("role") == "assistant" else "Customer"
        c = str(m.get("content") or "").strip()
        if c:
            lines.append(f"{who}: {c[:300]}")
    return "\n".join(lines)


def context_for(from_number: str, limit: int = _DEFAULT_CONTEXT_TURNS) -> str:
    """Convenience: recent thread ka transcript string. Never raises."""
    return as_context_text(history_messages(from_number, limit=limit))


def compact() -> dict[str, Any]:
    """Per-number turns ko ``_MAX_TURNS_PER_NUMBER`` tak trim karo (file-wide rewrite,
    atomic tmp+replace). Scheduler/daily se call ho sakta; never raises."""
    res = {"numbers": 0, "kept": 0, "dropped": 0}
    try:
        rows = _all_rows()
        if not rows:
            return res
        by_num: dict[str, list[dict]] = {}
        for r in rows:
            by_num.setdefault(_digits(r.get("from")), []).append(r)
        kept: list[dict] = []
        for _num, rs in by_num.items():
            res["numbers"] += 1
            trimmed = rs[-_MAX_TURNS_PER_NUMBER:]
            res["dropped"] += len(rs) - len(trimmed)
            kept.extend(trimmed)
        kept.sort(key=lambda x: str(x.get("at") or ""))
        res["kept"] = len(kept)
        tmp = _CONV_FILE + ".compact_tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for r in kept:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, _CONV_FILE)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("wa_conversation compact err: %s", exc)
        res["error"] = str(exc)[:120]
    return res


__all__ = [
    "record",
    "thread",
    "history_messages",
    "as_context_text",
    "context_for",
    "compact",
]
