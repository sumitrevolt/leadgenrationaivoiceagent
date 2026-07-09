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
_VALID_APPROVAL = ("review", "draft")

_DEFAULTS: dict[str, Any] = {
    "handles": dict.fromkeys(_HANDLE_KEYS, ""),
    "channels": [],
    "cadence": "daily",       # matches daily content engine; saved handles must not downgrade cadence
    "approval_mode": "review",  # review = post se pehle approve; draft = sirf draft ready
    "postiz_integrations": [],  # optional/advanced — Postiz channel ids (admin-assisted)
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

    return {
        "handles": handles,
        "channels": channels,
        "cadence": cadence,
        "approval_mode": approval,
        "postiz_integrations": pz,
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
        for key in ("channels", "cadence", "approval_mode", "postiz_integrations"):
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
