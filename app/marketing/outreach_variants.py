"""
outreach_variants.py — cold-email SPINTAX + A/B variants (Smartlead parity).
=============================================================================

Ek hi template ko {Hi|Hello|Namaste} jaisi spintax se har recipient ke liye
thoda alag render karo (spam-filter pattern-match kam) + 2+ subject variants
ka stable A/B assign + reply-rate tracking (Laplace winner).

Public API (sab never-raise, pure stdlib):
  - render(template, seed)                  -> spintax resolved (deterministic-by-seed)
  - pick_variant(variants, phone_or_email)  -> {"index","id","variant"} stable hash assign
  - record_send(variant_id, recipient)      -> data/outreach_variants.jsonl
  - record_reply(variant_id)                -> same store
  - stats()                                 -> per-variant sends/replies/reply_rate + Laplace winner
  - apply_ab(prospect, subject, text, html) -> auto_outreach hook (GATED caller-side
        `OUTREACH_AB=1`): 2-variant subject pick + spintax render + record_send.
        Staged rollout: `OUTREACH_AB_PCT` (0-100, default 100) — set to a small
        slice (e.g. 5) to canary-test before widening (council rec 2026-07-04).
  - next_mailbox() / rotate_sender(sender)  -> MAILBOX ROTATION: env
        `OUTREACH_MAILBOXES` = JSON list [{email,password,host?,port?}] ho to
        round-robin SMTP creds (cursor data/mailbox_cursor.json); absent = None
        (existing single-SMTP path bilkul untouched).

Wiring (auto_outreach.py, additive + gated, default OFF = zero change):
  - subject compose spot: OUTREACH_AB=1 par apply_ab()
  - send loop: rotate_sender(sender) — env absent = no-op

NOTE: EmailSender pehle email-API (Resend/Brevo) try karta hai — API path par
mailbox rotation moot hai (rotation sirf SMTP path ko affect karti hai).
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_PATH = os.path.join("data", "outreach_variants.jsonl")
_CURSOR_PATH = os.path.join("data", "mailbox_cursor.json")

# Spintax group = braces ke andar kam-se-kam ek pipe (taaki .format-style {name}
# placeholders untouched rahein).
_SPIN_RE = re.compile(r"\{([^{}]*\|[^{}]*)\}")

# Default 2 subject variants (Hinglish, spintax) — apply_ab inhe use karta hai.
# {name} = business name placeholder (render ke BAAD .format hota hai).
DEFAULT_SUBJECT_VARIANTS: list[str] = [
    "{name} — ek sawaal",
    "quick question — {name}",
    "{name} ke baare mein",
    "idea for {name}",
]


# --------------------------------------------------------------------------- #
# Spintax render (deterministic by seed)
# --------------------------------------------------------------------------- #
def render(template: str, seed: Any = 0) -> str:
    """Spintax `{Hi|Hello|Namaste}` resolve karo — SAME seed = SAME output
    (deterministic; recipient email seed banao to har baar wahi mile).
    Non-spintax braces ({name} jaise) untouched. Never raises."""
    try:
        out = str(template or "")
        rnd = random.Random(str(seed))
        for _ in range(50):  # bounded — nested/multiple groups
            m = _SPIN_RE.search(out)
            if not m:
                break
            choice = rnd.choice(m.group(1).split("|"))
            out = out[: m.start()] + choice + out[m.end() :]
        return out
    except Exception as e:
        logger.debug(f"[outreach_variants] render failed: {e}")
        return str(template or "")


def pick_variant(variants: list[Any], phone_or_email: str) -> dict[str, Any]:
    """Recipient ke liye STABLE variant assign (md5 hash % n) — same recipient
    hamesha same variant (clean A/B split). Never raises."""
    try:
        vs = list(variants or [])
        if not vs:
            return {"index": 0, "id": "A", "variant": ""}
        key = str(phone_or_email or "").strip().lower()
        idx = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16) % len(vs)
        vid = chr(65 + idx) if idx < 26 else str(idx)
        return {"index": idx, "id": vid, "variant": vs[idx]}
    except Exception as e:
        logger.debug(f"[outreach_variants] pick failed: {e}")
        return {"index": 0, "id": "A", "variant": (variants or [""])[0]}


# --------------------------------------------------------------------------- #
# Tracking store (jsonl append-only)
# --------------------------------------------------------------------------- #
def _append(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_PATH) or ".", exist_ok=True)
        rec["ts"] = datetime.now(timezone.utc).isoformat()
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"[outreach_variants] append failed: {e}")


def record_send(variant_id: str, recipient: str = "") -> None:
    """Variant send hua — track karo. Never raises."""
    _append(
        {"type": "send", "variant": str(variant_id or "A"), "recipient": str(recipient or "")[:120]}
    )


def record_reply(variant_id: str) -> None:
    """Variant pe reply aaya — track karo (reply_agent yahan hook kar sakta). Never raises."""
    _append({"type": "reply", "variant": str(variant_id or "A")})


def stats() -> dict[str, Any]:
    """Per-variant sends/replies/reply_rate + Laplace ((r+1)/(s+2)) winner. Never raises."""
    out: dict[str, Any] = {"variants": {}, "winner": None, "total_sends": 0, "total_replies": 0}
    try:
        if not os.path.isfile(_PATH):
            return out
        per: dict[str, dict[str, int]] = {}
        with open(_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                v = str(r.get("variant") or "A")
                d = per.setdefault(v, {"sends": 0, "replies": 0})
                if r.get("type") == "send":
                    d["sends"] += 1
                elif r.get("type") == "reply":
                    d["replies"] += 1
        best_v, best_score = None, -1.0
        for v, d in per.items():
            s, rp = d["sends"], d["replies"]
            rate = (rp / s) if s else 0.0
            laplace = (rp + 1) / (s + 2)
            out["variants"][v] = {
                "sends": s,
                "replies": rp,
                "reply_rate": round(rate, 4),
                "laplace": round(laplace, 4),
            }
            out["total_sends"] += s
            out["total_replies"] += rp
            if laplace > best_score:
                best_v, best_score = v, laplace
        out["winner"] = best_v
        if best_v:
            out["note"] = f"Variant {best_v} abhi aage hai (Laplace {round(best_score, 3)})."
    except Exception as e:
        logger.debug(f"[outreach_variants] stats failed: {e}")
    return out


# --------------------------------------------------------------------------- #
# Staged rollout gate (2026-07-04, LLM-council recommendation): OUTREACH_AB=1
# pehle sabko A/B karta tha (0 -> 100% overnight). Council-verdict: naya content
# variation ko turant 100% pe mat daalo — pehle chhoti slice (e.g. 5%) pe test
# karo, bounce_rate_7d/reply-rate dekho, phir widen karo. OUTREACH_AB_PCT env
# (0-100, default 100 = purana behavior unchanged) yeh enforce karta hai.
# --------------------------------------------------------------------------- #
def _ab_rollout_pct() -> int:
    """% of recipients that get the A/B variant when OUTREACH_AB=1. Default 100
    (apply to everyone, backward-compatible). Set lower (e.g. OUTREACH_AB_PCT=5)
    for a staged canary. Never raises."""
    try:
        v = int(os.environ.get("OUTREACH_AB_PCT", "100") or 100)
        return max(0, min(100, v))
    except Exception:
        return 100


def _in_rollout(key: str, pct: int) -> bool:
    """Stable per-recipient bucket (md5 % 100) < pct -> True. Same recipient
    always lands in the same bucket (no flip-flopping across follow-ups)."""
    try:
        if pct >= 100:
            return True
        if pct <= 0:
            return False
        bucket = int(hashlib.md5((key or "").encode("utf-8")).hexdigest(), 16) % 100
        return bucket < pct
    except Exception:
        return True


# --------------------------------------------------------------------------- #
# auto_outreach hook — A/B subject (caller gate: OUTREACH_AB=1)
# --------------------------------------------------------------------------- #
def apply_ab(
    prospect: dict[str, Any], subject: str, text: str, html_body: str
) -> tuple[str, str, str]:
    """Cold-email subject pe 2-variant A/B: recipient-stable pick + spintax render
    + record_send. Body untouched (safe). Fail = original tuple. Never raises.

    Staged rollout: OUTREACH_AB_PCT (default 100) se kam bucket wale recipients
    original subject hi paate — A/B sirf rollout-% slice pe apply hota."""
    try:
        email = str((prospect or {}).get("email") or "").strip().lower()
        name = str((prospect or {}).get("business_name") or "").strip() or "aapke business"
        if not _in_rollout(email or name, _ab_rollout_pct()):
            return subject, text, html_body
        picked = pick_variant(DEFAULT_SUBJECT_VARIANTS, email or name)
        tpl = render(str(picked.get("variant") or ""), seed=email or name)
        new_subject = tpl.replace("{name}", name).strip()
        if not new_subject:
            return subject, text, html_body
        record_send(str(picked.get("id") or "A"), email)
        return new_subject, text, html_body
    except Exception as e:
        logger.debug(f"[outreach_variants] apply_ab failed: {e}")
        return subject, text, html_body


# --------------------------------------------------------------------------- #
# Mailbox rotation (env OUTREACH_MAILBOXES JSON; absent = zero change)
# --------------------------------------------------------------------------- #
def _load_mailboxes() -> list[dict[str, Any]]:
    raw = (os.getenv("OUTREACH_MAILBOXES") or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        out = []
        for m in data:
            if isinstance(m, dict) and str(m.get("email") or "").strip() and m.get("password"):
                out.append(m)
        return out
    except Exception as e:
        logger.warning(f"[outreach_variants] OUTREACH_MAILBOXES JSON parse failed: {e}")
        return []


def next_mailbox() -> dict[str, Any] | None:
    """Round-robin agla mailbox (cursor data/mailbox_cursor.json). Env unset/
    invalid = None (caller existing single-SMTP path use kare). Never raises."""
    try:
        boxes = _load_mailboxes()
        if not boxes:
            return None
        cursor = 0
        try:
            if os.path.isfile(_CURSOR_PATH):
                with open(_CURSOR_PATH, encoding="utf-8") as f:
                    cursor = int((json.load(f) or {}).get("cursor") or 0)
        except Exception:
            cursor = 0
        mb = boxes[cursor % len(boxes)]
        try:
            os.makedirs(os.path.dirname(_CURSOR_PATH) or ".", exist_ok=True)
            with open(_CURSOR_PATH, "w", encoding="utf-8") as f:
                json.dump({"cursor": (cursor + 1) % len(boxes)}, f)
        except Exception:
            pass
        return mb
    except Exception as e:
        logger.debug(f"[outreach_variants] next_mailbox failed: {e}")
        return None


def rotate_sender(sender: Any) -> bool:
    """EmailSender instance pe agle mailbox ke SMTP creds set karo (send-time
    rotation). Env absent = False + sender UNTOUCHED. Never raises."""
    try:
        mb = next_mailbox()
        if not mb or sender is None:
            return False
        sender.user = str(mb.get("email") or "").strip()
        sender.password = str(mb.get("password") or "")
        sender.from_email = sender.user
        if mb.get("host"):
            sender.host = str(mb["host"]).strip()
        if mb.get("port"):
            try:
                sender.port = int(mb["port"])
            except Exception:
                pass
        return True
    except Exception as e:
        logger.debug(f"[outreach_variants] rotate_sender failed: {e}")
        return False


__all__ = [
    "render",
    "pick_variant",
    "record_send",
    "record_reply",
    "stats",
    "apply_ab",
    "next_mailbox",
    "rotate_sender",
    "DEFAULT_SUBJECT_VARIANTS",
]
