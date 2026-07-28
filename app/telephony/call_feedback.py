"""call_feedback — call-outcome -> data-quality self-improve loop (ADR-027).

KYUN (council 2026-07-06): scraper FIXED_LINE cloud-IVR DIDs (Livspace/HDFC
blocks) ko "ready" prospects bana raha tha aur system kabhi SEEKHTA nahi tha —
wahi numbers dobara dial ho sakte the. Ab jab bhi call me IVR/bot CONFIRM hota
hai (in-call IVR-strike hangup ya post-call qualifier bot-gate), yeh module:

1. `data/dial_blocklist.json` me exact number likhta hai (dial_gate ise
   consult karta hai — woh number dobara promotional-dial NAHI hoga);
2. usi 6-digit prefix ke DISTINCT confirmed numbers count karta hai — count
   >= LEARNED_BLOCK_THRESHOLD (default 3) hone par dial_gate poora prefix
   block karta hai (Livspace jaisa sequential DID-block auto-catch);
3. prospect store me us phone wale record par `dial_block` tag karta hai
   (status NAHI badalta — email-only route, lead delete nahi hota);
4. `data/dial_blocklist_audit.jsonl` me append-only audit entry (risk-guard:
   over-block reversible + explainable rahe).

Gated CALL_FEEDBACK_LOOP (default ON). Never raises. Import-safe.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def enabled() -> bool:
    """CALL_FEEDBACK_LOOP gate (default ON)."""
    return (os.environ.get("CALL_FEEDBACK_LOOP", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _blocklist_path() -> Path:
    # dial_gate ke saath SAME env/naam AUR same store id — single source.
    # Writer half: `_save()` creates the parent directory, this resolver does
    # not, so a read can never conjure an empty suppression list into existence.
    from app.platform import runtime_data_authority as _auth

    return _auth.resolve_store_path(
        store_id="telephony.dial_suppression",
        legacy_path=Path("data/dial_blocklist.json"),
        target_segments=("telephony", "dial_blocklist.json"),
        override_env="DIAL_BLOCKLIST_FILE",
    )


def _audit_path() -> Path:
    return Path(os.environ.get("DIAL_BLOCKLIST_AUDIT", "data/dial_blocklist_audit.jsonl"))


def _last10(number: str) -> str:
    import re

    return re.sub(r"\D", "", str(number or ""))[-10:]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load() -> dict:
    try:
        data = json.loads(_blocklist_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("numbers", {})
            data.setdefault("prefixes", {})
            return data
    except Exception:
        pass
    return {"numbers": {}, "prefixes": {}}


def _save(data: dict) -> None:
    p = _blocklist_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)  # atomic — half-written file kabhi read na ho


def _audit(entry: dict) -> None:
    try:
        p = _audit_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _tag_prospect(phone10: str, reason: str) -> bool:
    """Prospect store me matching phone par dial_block tag (status untouched —
    email path zinda rehta). Best-effort; store absent => False."""
    try:
        from app.platform import prospector

        for r in prospector._read_all():
            if _last10(r.get("phone") or "") == phone10 and r.get("id"):
                return prospector.set_prospect_fields(
                    str(r["id"]),
                    {"dial_block": reason, "dial_block_at": _now()},
                )
    except Exception as e:
        logger.debug(f"[call_feedback] prospect tag skip: {e}")
    return False


def record_ivr_confirmed(
    phone: str, *, source: str = "in_call_ivr", call_sid: str = "", detail: str = ""
) -> dict:
    """IVR/bot CONFIRMED on this number — learn it. Returns summary dict.

    source: "in_call_ivr" (IVR-strike hangup, ADR-025) | "post_call_bot"
    (call_qualifier bot-gate). Never raises; disabled => {"ok": False}.
    """
    out: dict = {"ok": False, "phone": "", "prefix_hits": 0, "prefix_active": False}
    try:
        if not enabled():
            out["reason"] = "disabled"
            return out
        n = _last10(phone)
        if len(n) != 10:
            out["reason"] = "bad_phone"
            return out
        data = _load()
        reason = f"ivr_confirmed:{source}"
        data["numbers"][n] = {"reason": reason, "at": _now(), "call_sid": call_sid[:40]}
        pref = n[:6]
        rec = data["prefixes"].setdefault(pref, {"numbers": [], "last": ""})
        if n not in (rec.get("numbers") or []):
            rec.setdefault("numbers", []).append(n)
        rec["last"] = _now()
        _save(data)
        tagged = _tag_prospect(n, reason)
        hits = len(set(rec.get("numbers") or []))
        try:
            from app.telephony.dial_gate import _prefix_threshold

            active = hits >= _prefix_threshold()
        except Exception:
            active = hits >= 3
        _audit(
            {
                "at": _now(),
                "phone": n,
                "prefix": pref,
                "prefix_hits": hits,
                "prefix_block_active": active,
                "source": source,
                "call_sid": call_sid[:40],
                "detail": (detail or "")[:120],
                "prospect_tagged": tagged,
            }
        )
        logger.info(
            f"[call_feedback] IVR-confirm {n} (prefix {pref}: {hits} hits, "
            f"prefix-block {'ACTIVE' if active else 'inactive'}, prospect_tagged={tagged})"
        )
        out.update(
            {
                "ok": True,
                "phone": n,
                "prefix_hits": hits,
                "prefix_active": active,
                "prospect_tagged": tagged,
            }
        )
        return out
    except Exception as e:
        logger.warning(f"[call_feedback] record failed: {e}")
        return out


__all__ = ["enabled", "record_ivr_confirmed"]
