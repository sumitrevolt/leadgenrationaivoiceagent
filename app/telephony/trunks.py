"""Provider-agnostic SIP trunk dispatcher.

Purpose:
- Single source for trunk selection (Tata SmartFlo — sole live provider).
- Vobiz + Jio Mobile SIP removed 2026-09-15 (owner mandate).
- Fail-OPEN: pick_trunk() never raises; returns (provider, caller_id) or
  ("none", "") when nothing is configured.

Usage:
    from app.telephony.trunks import pick_trunk, list_active_trunks
    provider, caller_id = pick_trunk(lead=None)
    if provider == "none":
        raise NoTrunkAvailable()  # caller handles
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Trunk:
    name: str
    enabled: bool
    caller_id: str
    weight: int
    cps_limit: int
    max_concurrent: int
    cost_per_min_inr: float  # for LCR; 0 = flat / unlimited
    notes: str = ""
    # Compliance lanes this trunk MAY carry. TRAI TCCCPR 2018/amended:
    # promotional calls MUST originate from a 140-series CLI (DLT-registered).
    # Transactional/service/reactivation calls don't need a 140 CLI.
    # jio_mobile = ordinary mobile DID (non-140) => transactional-only.
    lanes: frozenset[str] = frozenset({"promotional", "transactional"})


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    return _env(name).lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name) or default)
    except (ValueError, TypeError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name) or default)
    except (ValueError, TypeError):
        return default


def list_active_trunks() -> list[Trunk]:
    """Return all CONFIGURED+ENABLED trunks. Used by readiness + dispatcher.
    Never raises. Order = provider name (stable).

    Vobiz + Jio removed 2026-09-15 — Tata SmartFlo is the sole provider.
    """
    out: list[Trunk] = []
    # --- Tata Tele Smartflo Pro (₹1,250/license/month, unlimited India) ---
    tata_creds = bool(_env("TATA_SMARTFLO_API_TOKEN") and _env("TATA_SMARTFLO_API_KEY"))
    tata_enabled = _env_bool("TATA_SMARTFLO_ENABLED", False)
    if tata_creds and tata_enabled:
        out.append(
            Trunk(
                name="tata_smartflo",
                enabled=True,
                caller_id=_env("TATA_SMARTFLO_DID"),
                weight=_env_int("TATA_SMARTFLO_WEIGHT", 50),
                cps_limit=_env_int("TATA_SMARTFLO_CPS_LIMIT", 2),
                max_concurrent=_env_int("TATA_SMARTFLO_MAX_CONCURRENT", 5),
                cost_per_min_inr=0.0,
                notes=(
                    "Tata Smartflo Pro; ₹1,250/license/mo unlimited India (5000 min FUP/pool). "
                    "₹10,000 one-time. 1 DID bundled. Click-to-Call REST API. "
                    "⚠️ Standard DID — TRAI lanes depend on DLT registration."
                ),
                lanes=frozenset({"promotional", "transactional"}),
            )
        )
    return out


def _lane_for(lead: Any) -> str:
    """Transactional vs promotional lane for this call.

    TRAI TCCCPR: promotional outbound needs a 140-series CLI; transactional/
    service/reactivation calls don't. Unknown lead or no field => treat as
    PROMOTIONAL (fail-CLOSED) — non-140 trunks (jio mobile DID) stay excluded.
    """
    if lead is None:
        return "promotional"
    if isinstance(lead, dict):
        txn = lead.get("transactional") or lead.get("is_transactional")
    else:
        txn = getattr(lead, "transactional", None) or getattr(lead, "is_transactional", None)
    return "transactional" if bool(txn) else "promotional"


def pick_trunk(lead: Any = None) -> tuple[str, str]:
    """Pick a trunk for the next outbound call.
    Strategy: weight-based random (round-robin-ish), FILTERED by the call's
    compliance lane — a trunk that the lane forbids (e.g. non-140 jio_mobile
    on a promotional call) is never chosen, even weighted. Unknown lead =>
    promotional lane (fail-closed).
    Returns (provider_name, caller_id). ("none", "") when no eligible trunk.
    Never raises.
    """
    lane = _lane_for(lead)
    trunks = [
        t
        for t in list_active_trunks()
        if t.enabled and t.caller_id and lane in t.lanes
    ]
    if not trunks:
        return ("none", "")
    if len(trunks) == 1:
        return (trunks[0].name, trunks[0].caller_id)
    # Weighted pick
    total = sum(max(t.weight, 0) for t in trunks) or 1
    r = random.uniform(0, total)
    upto = 0
    for t in trunks:
        upto += max(t.weight, 0)
        if r <= upto:
            return (t.name, t.caller_id)
    # Fallback (shouldn't reach)
    return (trunks[0].name, trunks[0].caller_id)


def freeswitch_gateway_xml(trunk: Trunk) -> str:
    """Render a FreeSWITCH gateway XML for the given trunk.
    Caller writes to sip-gateways/{name}.xml and `reloadxml`.

    Vobiz + Jio removed 2026-09-15 — only Tata SmartFlo remains.
    """
    if trunk.name == "tata_smartflo":
        # Tata Smartflo uses Click-to-Call REST API (not raw SIP gateway).
        # For FreeSWITCH SIP gateway integration (future), configure with:
        #   host = _env("TATA_SMARTFLO_SIP_HOST")
        #   user = _env("TATA_SMARTFLO_SIP_USER")
        #   pass = _env("TATA_SMARTFLO_SIP_PASS")
        host = _env("TATA_SMARTFLO_SIP_HOST") or "api-smartflo.tatateleservices.com"
        user = _env("TATA_SMARTFLO_SIP_USER", "smartflo")
        password = _env("TATA_SMARTFLO_SIP_PASS", "")
        transport = _env("TATA_SMARTFLO_TRANSPORT", "udp").lower()
        params = (
            f'    <param name="realm" value="{host}"/>\n'
            f'    <param name="proxy" value="{host}"/>\n'
            f'    <param name="from-domain" value="leadsgenai.in"/>\n'
        )
        if password:
            params += (
                f'    <param name="register" value="true"/>\n'
                f'    <param name="username" value="{user}"/>\n'
                f'    <param name="password" value="{password}"/>\n'
            )
        else:
            params += '    <param name="register" value="false"/>\n'
        return f"""<include>
  <gateway name="tata_smartflo">
{params}    <param name="caller-id-in-from" value="true"/>
    <param name="contact-params" value=""/>
    <param name="codec-prefs" value="PCMA,PCMU,G729"/>
    <param name="transport" value="{transport}"/>
    <param name="sip-ip" value="$${{local_ip_v4}}"/>
    <param name="rtp-ip" value="$${{local_ip_v4}}"/>
    <param name="expire-seconds" value="600"/>
  </gateway>
</include>
"""
    raise ValueError(f"Unknown trunk: {trunk.name} — Vobiz/Jio removed 2026-09-15")


__all__ = ["Trunk", "list_active_trunks", "pick_trunk", "freeswitch_gateway_xml"]
