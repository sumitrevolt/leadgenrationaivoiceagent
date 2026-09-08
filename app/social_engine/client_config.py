"""social_engine.client_config — per-client SOCIAL NETWORKING setup (handles +
posting preferences) for the customer-facing **Social Setup Wizard**.

Yeh sirf ek PREFERENCE/config store hai — actual auto-posting abhi bhi master
gate `SOCIAL_ENGINE` (`engine.enabled()`) + configured providers pe depend karta
hai. Yahan config save karne se KUCH bhi AUTO-POST nahi hota (INERT-by-default
invariant intact rehta hai). Downstream content/publish engines yeh prefs
padh kar (cadence/channels/approval_mode) apna behaviour tune kar sakte hain,
par default me sab draft/approval path pe hi rehta hai.

Store: data/social_config.jsonl (latest (client_id) wins — vault/store jaisa
append-only latest-wins pattern). NEVER raises.

  get(client_id) -> dict                # normalized, defaults-filled
  save(client_id, **partial) -> dict    # merge over current + normalize + persist
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_PATH = os.path.join("data", "social_config.jsonl")

# Handles jo wizard capture karta (str links/handles). instagram/facebook/gbp
# clients_store.socials me bhi mirror hote (mini-site/page-kit unko padhta) —
# youtube/linkedin/twitter sirf yahan. Additive: naya key add karna safe.
_HANDLE_KEYS = ("instagram", "facebook", "gbp", "youtube", "linkedin", "twitter")

# Content-creation target channels (customer in me se choose karta ki AI kis
# channel ke liye content banaye). Sab ban-safe/draft-first; whatsapp = owner ke
# apne number pe 1-to-1 delivery (ban-safe), koi bulk nahi.
_VALID_CHANNELS = ("instagram", "facebook", "gbp", "youtube", "linkedin", "whatsapp")

_VALID_CADENCE = ("daily", "3x_week", "weekly", "off")
# review = human approve pehle; draft = queue only; auto = customer consented
# hands-free publish (SOCIAL_PREFS_HONOR + SOCIAL_ENGINE + own Postiz IDs still required).
_VALID_APPROVAL = ("review", "draft", "auto")

# Loop-social-19 (2026-07-11): Phase-3 Step-1 + Step-4 field completeness.
# Additive — every new field defaults empty/list so existing wizard save calls
# don't break, and the readiness endpoint can score against them.
_VALID_POSTING_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_VALID_LANGUAGES = ("hi", "en", "hinglish", "gu", "mr", "ta", "te", "kn", "ml", "bn", "pa")

_DEFAULTS: dict[str, Any] = {
    "handles": dict.fromkeys(_HANDLE_KEYS, ""),
    "channels": [],
    "cadence": "daily",  # matches daily content engine; saved handles must not downgrade cadence
    "approval_mode": "auto",  # Changed to "auto" natively for SaaS 'set and forget' competitor parity
    "postiz_integrations": [],  # optional/advanced — Postiz channel ids (admin-assisted)
    # Loop-social-19: Step-1 business profile fields — persisted alongside
    # clients_store base profile. Wizard-level source of truth for the
    # social-delivery loop specifically.
    "timezone": "Asia/Kolkata",
    "website": "",
    "brand_tone": "",  # e.g. "friendly", "professional", "playful"
    "target_audience": "",  # freeform 1-liner
    "products_or_services": "",  # freeform, comma-separated
    "preferred_language": "hinglish",
    # Loop-social-19: Step-4 content preferences.
    "posting_days": [],  # ["mon","wed","fri"] etc — empty = every day
    "posting_times": [],  # ["09:00","18:00"] IST — empty = auto
    "content_categories": [],  # ["promo","tips","festivals","testimonials"]
    "prohibited_topics": [],  # ["politics","competitors","medical claims"]
    "brand_safety_instructions": "",  # freeform — passed to LLM system prompt
}


def _read() -> list[dict[str, Any]]:
    try:
        with open(_PATH, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]
    except FileNotFoundError:
        return []
    except Exception as e:  # pragma: no cover
        logger.warning(f"[social_config] read failed: {e}")
        return []


def _latest(client_id: str) -> dict[str, Any]:
    """Us client ka LAST likha record (baad wali line jeet ti)."""
    cid = (client_id or "").strip()
    found: dict[str, Any] = {}
    for rec in _read():
        if str(rec.get("client_id") or "") == cid:
            found = rec  # latest wins
    return found


def _norm(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Defaults-filled + validated config. Kabhi raise nahi — bad values drop."""
    r = raw if isinstance(raw, dict) else {}
    handles_in = r.get("handles") if isinstance(r.get("handles"), dict) else {}
    handles = {k: str((handles_in or {}).get(k) or "").strip()[:300] for k in _HANDLE_KEYS}

    ch_in = r.get("channels")
    channels: list[str] = []
    if isinstance(ch_in, (list, tuple)):
        for c in ch_in:
            c = str(c or "").strip().lower()
            if c in _VALID_CHANNELS and c not in channels:
                channels.append(c)

    cadence = str(r.get("cadence") or "").strip().lower()
    if cadence not in _VALID_CADENCE:
        cadence = _DEFAULTS["cadence"]

    approval = str(r.get("approval_mode") or "").strip().lower()
    if approval not in _VALID_APPROVAL:
        approval = _DEFAULTS["approval_mode"]

    pz_in = r.get("postiz_integrations")
    pz: list[str] = []
    if isinstance(pz_in, (list, tuple)):
        for x in pz_in:
            x = str(x or "").strip()[:80]
            if x and x not in pz:
                pz.append(x)
    elif isinstance(pz_in, str):
        for x in pz_in.split(","):
            x = x.strip()[:80]
            if x and x not in pz:
                pz.append(x)
    pz = pz[:20]

    # Loop-social-19: normalize the extended profile + preference fields.
    tz = str(r.get("timezone") or "").strip()[:64] or _DEFAULTS["timezone"]
    website = str(r.get("website") or "").strip()[:300]
    brand_tone = str(r.get("brand_tone") or "").strip()[:80]
    target_audience = str(r.get("target_audience") or "").strip()[:500]
    products_or_services = str(r.get("products_or_services") or "").strip()[:500]
    preferred_language = str(r.get("preferred_language") or "").strip().lower()[:16]
    if preferred_language and preferred_language not in _VALID_LANGUAGES:
        preferred_language = _DEFAULTS["preferred_language"]
    if not preferred_language:
        preferred_language = _DEFAULTS["preferred_language"]

    def _norm_str_list(raw: Any, cap: int, allowed: tuple | None = None) -> list[str]:
        if isinstance(raw, str):
            items = [x.strip() for x in raw.replace(",", " ").split() if x.strip()]
        elif isinstance(raw, (list, tuple)):
            items = [str(x).strip() for x in raw if str(x).strip()]
        else:
            return []
        out: list[str] = []
        for x in items:
            x_l = x.lower()
            if allowed is not None and x_l not in allowed:
                continue
            if x_l not in out:
                out.append(x_l)
            if len(out) >= cap:
                break
        return out

    posting_days = _norm_str_list(r.get("posting_days"), cap=7, allowed=_VALID_POSTING_DAYS)

    # Posting times: HH:MM (24h). Regex-lite validation.
    import re as _re

    _time_re = _re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")
    pt_raw = r.get("posting_times")
    if isinstance(pt_raw, str):
        pt_items = [x.strip() for x in pt_raw.replace(",", " ").split() if x.strip()]
    elif isinstance(pt_raw, (list, tuple)):
        pt_items = [str(x).strip() for x in pt_raw if str(x).strip()]
    else:
        pt_items = []
    posting_times = [t for t in pt_items if _time_re.match(t)][:8]

    content_categories = _norm_str_list(r.get("content_categories"), cap=20)
    prohibited_topics = _norm_str_list(r.get("prohibited_topics"), cap=20)
    brand_safety_instructions = str(r.get("brand_safety_instructions") or "").strip()[:2000]

    return {
        "handles": handles,
        "channels": channels,
        "cadence": cadence,
        "approval_mode": approval,
        "postiz_integrations": pz,
        # Loop-social-19: Step-1 + Step-4 fields.
        "timezone": tz,
        "website": website,
        "brand_tone": brand_tone,
        "target_audience": target_audience,
        "products_or_services": products_or_services,
        "preferred_language": preferred_language,
        "posting_days": posting_days,
        "posting_times": posting_times,
        "content_categories": content_categories,
        "prohibited_topics": prohibited_topics,
        "brand_safety_instructions": brand_safety_instructions,
    }


def get(client_id: str) -> dict[str, Any]:
    """Client ka normalized social-setup config. No record = defaults. Never raises."""
    try:
        rec = _latest(client_id)
        cfg = _norm(rec)
        cfg["configured"] = bool(rec)  # kabhi save hua tha?
        cfg["updated_at"] = str(rec.get("updated_at") or "") if rec else ""
        return cfg
    except Exception as e:  # pragma: no cover
        logger.warning(f"[social_config] get failed: {e}")
        out = dict(_DEFAULTS)
        out.update({"configured": False, "updated_at": ""})
        return out


def save(client_id: str, **partial: Any) -> dict[str, Any]:
    """Config MERGE (current ke upar) + normalize + persist. Returns saved config.
    Never raises (error pe {} return). IDOR: caller client_id JWT se hi de."""
    try:
        cid = (client_id or "").strip()
        if not cid:
            return {}
        current = _norm(_latest(cid))
        # Handles ko merge karo (jo key partial me di gayi wahi update, baaki same).
        merged: dict[str, Any] = dict(current)
        if "handles" in partial and isinstance(partial["handles"], dict):
            merged["handles"] = {**current["handles"], **partial["handles"]}
        for key in (
            "channels",
            "cadence",
            "approval_mode",
            "postiz_integrations",
            # Loop-social-19: Step-1 + Step-4 keys.
            "timezone",
            "website",
            "brand_tone",
            "target_audience",
            "products_or_services",
            "preferred_language",
            "posting_days",
            "posting_times",
            "content_categories",
            "prohibited_topics",
            "brand_safety_instructions",
        ):
            if key in partial and partial[key] is not None:
                merged[key] = partial[key]
        cfg = _norm(merged)
        rec = {
            "client_id": cid,
            **cfg,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        os.makedirs(os.path.dirname(_PATH) or ".", exist_ok=True)
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        cfg["configured"] = True
        cfg["updated_at"] = rec["updated_at"]
        return cfg
    except Exception as e:  # pragma: no cover
        logger.warning(f"[social_config] save failed: {e}")
        return {}


__all__ = [
    "get",
    "save",
    "_HANDLE_KEYS",
    "_VALID_CHANNELS",
    "_VALID_CADENCE",
    "_VALID_APPROVAL",
]
