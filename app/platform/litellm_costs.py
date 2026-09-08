"""litellm_costs.py — fetch per-key spend from a running LiteLLM gateway.

The 2026-06-16 billionaire-scale audit (F.5) named "per-tenant unit economics"
as a genuine gap: the custom usage meter tracks usage, but there's no
cost-per-customer view to defend gross margin on outcome-based pricing.
LiteLLM gives every customer a virtual key + tracks spend per key — once
activated, this module is what turns that data into a board-room number.

LiteLLM is already on the VPS via deploy/compose/docker-compose.edge.yml (--profile gateway).
This module talks to the gateway's /metrics endpoint (Prometheus exposition
format) and the /spend/calculate proxy endpoint to compute:
- spend per virtual-key in the last N hours / today / month-to-date
- per-customer (alias map: virtual-key -> client_id)
- margin-negative niches (when revenue from a client < cost of LLM calls)

INERT when:
- LITELLM_GATEWAY_URL unset, or
- LiteLLM not reachable / not configured.
All probes return a {"available": False, "reason": ...} payload so dashboards
degrade gracefully rather than 500.

Activation runbook (operator):
1. .env: LITELLM_MASTER_KEY=<random>, LITELLM_GATEWAY_URL=http://litellm:4000
2. docker compose -f deploy/compose/docker-compose.edge.yml --profile gateway up -d
3. Curl http://litellm:4000/health -> should be 200
4. Issue per-tenant virtual keys via the LiteLLM admin UI / API and store
   the (virtual-key -> client_id) mapping in data/litellm_keymap.jsonl
5. Set LITELLM_COSTS=1 in .env to enable the FinOps agent integration.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FLAG = "LITELLM_COSTS"
_GATEWAY_URL_ENV = "LITELLM_GATEWAY_URL"
_MASTER_KEY_ENV = "LITELLM_MASTER_KEY"
_DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
_KEYMAP_PATH = _DATA_DIR / "litellm_keymap.jsonl"

_HTTP_TIMEOUT_S = 5.0


def enabled() -> bool:
    """Master flag + master-key set. Both required for any /spend call."""
    return os.environ.get(_FLAG, "0").strip().lower() in ("1", "true", "yes") and bool(
        os.environ.get(_MASTER_KEY_ENV, "").strip()
    )


def _gateway_url() -> str:
    return os.environ.get(_GATEWAY_URL_ENV, "").strip().rstrip("/")


def _master_key() -> str:
    return os.environ.get(_MASTER_KEY_ENV, "").strip()


# --------------------------------------------------------------------------- #
# Key -> client_id alias map (data/litellm_keymap.jsonl)
# Rows: {"vkey": "sk-xxxx", "client_id": "client_abc", "niche": "salon"}
# --------------------------------------------------------------------------- #
def _read_keymap() -> dict[str, dict[str, Any]]:
    """Returns {virtual_key_prefix: {client_id, niche, ...}}. {} on missing."""
    if not _KEYMAP_PATH.exists():
        return {}
    out: dict[str, dict[str, Any]] = {}
    try:
        for line in _KEYMAP_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                k = str(rec.get("vkey", ""))
                if k:
                    out[k] = rec
            except Exception:
                continue
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------- #
# Gateway probes
# --------------------------------------------------------------------------- #
async def gateway_health() -> dict[str, Any]:
    """Quick reachability probe — no auth, no PII. Used by dashboards."""
    url = _gateway_url()
    if not url:
        return {"available": False, "reason": "LITELLM_GATEWAY_URL unset"}
    try:
        import httpx

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S) as client:
            r = await client.get(f"{url}/health")
            return {
                "available": r.status_code == 200,
                "status_code": r.status_code,
                "url": url,
            }
    except Exception as exc:
        return {"available": False, "reason": f"unreachable: {exc}"}


async def per_key_spend(hours: int = 24) -> dict[str, Any]:
    """Aggregate spend per virtual-key from LiteLLM's /spend endpoint.

    Returns:
      {"available": True, "window_hours": N, "spend": [
         {"vkey": "...", "client_id": "...", "spend_usd": 1.23, "calls": 12},
         ...
      ], "total_usd": ...}
    or {"available": False, "reason": "..."} on probe failure.
    """
    if not enabled():
        return {"available": False, "reason": "LITELLM_COSTS unset or no master key"}
    url = _gateway_url()
    if not url:
        return {"available": False, "reason": "LITELLM_GATEWAY_URL unset"}

    try:
        import httpx

        headers = {"Authorization": f"Bearer {_master_key()}"}
        # LiteLLM exposes /spend/keys (list spend per key over a window).
        # If the endpoint shape changes upstream, this fails closed with
        # a structured error — dashboards stay alive.
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S) as client:
            r = await client.get(
                f"{url}/spend/keys",
                params={"window_hours": int(hours)},
                headers=headers,
            )
            if r.status_code != 200:
                return {"available": False, "reason": f"litellm /spend/keys HTTP {r.status_code}"}
            data = r.json()
    except Exception as exc:
        return {"available": False, "reason": f"unreachable: {exc}"}

    keymap = _read_keymap()
    rows: list[dict[str, Any]] = []
    total = 0.0
    # LiteLLM returns either {"data": [...]} or just a list — handle both.
    items = data.get("data", data) if isinstance(data, dict) else data
    for it in items or []:
        if not isinstance(it, dict):
            continue
        vkey = str(it.get("key") or it.get("token") or it.get("api_key") or "")
        spend = float(it.get("spend") or it.get("spend_usd") or 0.0)
        calls = int(it.get("call_count") or it.get("requests") or 0)
        mapping = keymap.get(vkey, {})
        rows.append(
            {
                "vkey": vkey[:8] + "..." if len(vkey) > 8 else vkey,
                "client_id": mapping.get("client_id"),
                "niche": mapping.get("niche"),
                "spend_usd": round(spend, 4),
                "calls": calls,
            }
        )
        total += spend
    return {
        "available": True,
        "window_hours": int(hours),
        "spend": rows,
        "total_usd": round(total, 4),
        "ts": int(time.time()),
    }


def per_key_spend_sync(hours: int = 24) -> dict[str, Any]:
    """Sync mirror of per_key_spend() for sync call sites (engineer agents).

    Engineer agents are sync functions on the scheduler; this lets them probe
    LiteLLM without spawning an event loop. Shape identical to per_key_spend.
    """
    if not enabled():
        return {"available": False, "reason": "LITELLM_COSTS unset or no master key"}
    url = _gateway_url()
    if not url:
        return {"available": False, "reason": "LITELLM_GATEWAY_URL unset"}
    try:
        import httpx

        headers = {"Authorization": f"Bearer {_master_key()}"}
        with httpx.Client(timeout=_HTTP_TIMEOUT_S) as client:
            r = client.get(
                f"{url}/spend/keys",
                params={"window_hours": int(hours)},
                headers=headers,
            )
            if r.status_code != 200:
                return {"available": False, "reason": f"litellm /spend/keys HTTP {r.status_code}"}
            data = r.json()
    except Exception as exc:
        return {"available": False, "reason": f"unreachable: {exc}"}

    keymap = _read_keymap()
    rows: list[dict[str, Any]] = []
    total = 0.0
    items = data.get("data", data) if isinstance(data, dict) else data
    for it in items or []:
        if not isinstance(it, dict):
            continue
        vkey = str(it.get("key") or it.get("token") or it.get("api_key") or "")
        spend = float(it.get("spend") or it.get("spend_usd") or 0.0)
        calls = int(it.get("call_count") or it.get("requests") or 0)
        mapping = keymap.get(vkey, {})
        rows.append(
            {
                "vkey": vkey[:8] + "..." if len(vkey) > 8 else vkey,
                "client_id": mapping.get("client_id"),
                "niche": mapping.get("niche"),
                "spend_usd": round(spend, 4),
                "calls": calls,
            }
        )
        total += spend
    return {
        "available": True,
        "window_hours": int(hours),
        "spend": rows,
        "total_usd": round(total, 4),
        "ts": int(time.time()),
    }


async def margin_alerts(revenue_per_client_usd: dict[str, float] | None = None) -> dict[str, Any]:
    """Flag clients whose LLM cost > stated revenue (margin-negative).

    `revenue_per_client_usd` should be an op-supplied dict (or built from
    billing tables). For now this is a passive computation; the caller
    decides how to act (ntfy / email).
    """
    spend = await per_key_spend(hours=24 * 30)
    if not spend.get("available"):
        return spend
    revenue = dict(revenue_per_client_usd or {})
    flagged: list[dict[str, Any]] = []
    for row in spend["spend"]:
        cid = row.get("client_id")
        if not cid:
            continue
        rev = float(revenue.get(cid, 0.0))
        if rev > 0 and row["spend_usd"] >= rev:
            flagged.append(
                {
                    "client_id": cid,
                    "revenue_usd": rev,
                    "spend_usd": row["spend_usd"],
                    "ratio": round(row["spend_usd"] / rev, 2),
                    "niche": row.get("niche"),
                }
            )
    return {"available": True, "flagged": flagged, "total_clients_checked": len(spend["spend"])}


__all__ = ["enabled", "gateway_health", "per_key_spend", "per_key_spend_sync", "margin_alerts"]
