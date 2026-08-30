"""Provider-agnostic SIP trunk dispatcher.

Purpose:
- Single source for trunk selection (Vobiz / Jio Mobile SIP / future).
- Round-robin + LCR-lite (cheapest-first) by weight.
- Fail-OPEN: pick_trunk() never raises; returns (provider, caller_id) or
  ("none", "") when nothing is configured.
- INERT by default for new providers — flag must be explicitly set.

Plan doc: docs/coordination/JIO_SIP_SETUP_PLAN.md (2026-08-27).

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
    """
    out: list[Trunk] = []
    # --- Vobiz (PAYG) ---
    vobiz_ok = bool(_env("VOBIZ_AUTH_ID") and _env("VOBIZ_AUTH_TOKEN"))
    if vobiz_ok:
        out.append(
            Trunk(
                name="vobiz",
                enabled=True,  # vobiz is always-on when creds present
                caller_id=_env("VOBIZ_CALLER_ID"),
                weight=50,  # default; tunable later
                cps_limit=2,
                max_concurrent=5,
                cost_per_min_inr=0.45,
                notes="Vobiz India-native SIP; ₹0.45/min PAYG",
            )
        )
    # --- Jio Mobile SIP (Sai Service Centre reseller) ---
    jio_creds = bool(_env("JIO_SIP_HOST") and _env("JIO_SIP_USER") and _env("JIO_SIP_PASS"))
    jio_enabled = _env_bool("JIO_TRUNK_ENABLED", False)
    if jio_creds and jio_enabled:
        out.append(
            Trunk(
                name="jio_mobile",
                enabled=True,
                caller_id=_env("JIO_SIP_DID"),
                weight=_env_int("JIO_TRUNK_WEIGHT", 50),
                cps_limit=_env_int("JIO_SIP_CPS_LIMIT", 2),
                max_concurrent=_env_int("JIO_SIP_MAX_CONCURRENT", 10),
                cost_per_min_inr=0.0,  # flat unlimited
                notes="Jio Mobile SIP (Sai Service Centre); ₹9,990/mo flat 10ch unlimited",
            )
        )
    return out


def pick_trunk(lead: Any = None) -> tuple[str, str]:
    """Pick a trunk for the next outbound call.
    Strategy: weight-based random (round-robin-ish).
    Returns (provider_name, caller_id). ("none", "") when no trunk available.
    Never raises.
    """
    trunks = [t for t in list_active_trunks() if t.enabled and t.caller_id]
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
    """
    if trunk.name == "jio_mobile":
        auth_mode = _env("JIO_SIP_AUTH_MODE", "ip").lower()
        host = _env("JIO_SIP_HOST")
        realm = _env("JIO_SIP_REALM") or host
        user = _env("JIO_SIP_USER")
        password = _env("JIO_SIP_PASS")
        from_domain = _env("JIO_SIP_FROM_DOMAIN", "leadsgenai.in")
        transport = _env("JIO_SIP_TRANSPORT", "udp").lower()
        if auth_mode == "ip":
            # IP-auth: no registration, no creds
            params = f"""    <param name="realm" value="{realm}"/>
    <param name="proxy" value="{host}"/>
    <param name="from-domain" value="{from_domain}"/>
    <param name="register" value="false"/>"""
        else:
            # Registration-based
            params = f"""    <param name="realm" value="{realm}"/>
    <param name="proxy" value="{host}"/>
    <param name="from-domain" value="{from_domain}"/>
    <param name="register" value="true"/>
    <param name="username" value="{user}"/>
    <param name="password" value="{password}"/>"""
        return f"""<include>
  <gateway name="jio_mobile">
{params}
    <param name="caller-id-in-from" value="true"/>
    <param name="contact-params" value=""/>
    <param name="codec-prefs" value="PCMA,PCMU,G729"/>
    <param name="transport" value="{transport}"/>
    <param name="sip-ip" value="$${{local_ip_v4}}"/>
    <param name="rtp-ip" value="$${{local_ip_v4}}"/>
    <param name="expire-seconds" value="600"/>
  </gateway>
</include>
"""
    if trunk.name == "vobiz":
        # Vobiz uses API-mode place_call, not gateway — but if a future
        # migration wants FreeSWITCH-based, here's a skeleton.
        host = _env("VOBIZ_TRUNK_DOMAIN")
        return f"""<!-- Vobiz trunk: prefer API place_call mode. This gateway stub
     is only used if you migrate to FreeSWITCH SIP-to-SIP. -->
<include>
  <gateway name="vobiz_sip">
    <param name="realm" value="{host}"/>
    <param name="proxy" value="{host}"/>
    <param name="register" value="false"/>
  </gateway>
</include>
"""
    raise ValueError(f"Unknown trunk: {trunk.name}")


__all__ = ["Trunk", "list_active_trunks", "pick_trunk", "freeswitch_gateway_xml"]
