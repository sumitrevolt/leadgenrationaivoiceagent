"""Multi-touch revenue attribution — inquiry UTM → subscription linkage."""

from __future__ import annotations

import json
import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_PATH = os.path.join("data", "revenue_attribution.jsonl")


def _append(rec: dict[str, Any]) -> None:
    try:
        os.makedirs("data", exist_ok=True)
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def record_touch(
    *,
    client_id: str,
    channel: str,
    utm_source: str = "",
    utm_campaign: str = "",
    event: str = "inquiry",
    amount_inr: int = 0,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Log attribution touch (inquiry → signup → payment). Never raises."""
    rec = {
        "client_id": client_id,
        "channel": channel,
        "utm_source": utm_source,
        "utm_campaign": utm_campaign,
        "event": event,
        "amount_inr": amount_inr,
        "meta": meta or {},
    }
    _append(rec)
    try:
        from app.marketing import channel_experiments

        ch = utm_source or channel
        if ch:
            channel_experiments.record_outcome(
                ch, event, 1 if event != "payment" else 2, f"attr:{client_id}"
            )
    except Exception:
        pass
    return {"ok": True, "recorded": rec}


async def link_payment(client_id: str, amount_inr: int, *, utm_source: str = "") -> dict[str, Any]:
    """Hook from billing when subscription activates."""
    return record_touch(
        client_id=client_id,
        channel="billing",
        utm_source=utm_source,
        event="payment",
        amount_inr=amount_inr,
    )


def summary(limit: int = 200) -> dict[str, Any]:
    """Aggregate touches by channel/event."""
    by_channel: dict[str, int] = {}
    by_event: dict[str, int] = {}
    mrr_inr = 0
    try:
        if os.path.isfile(_PATH):
            with open(_PATH, encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i >= limit:
                        break
                    if not line.strip():
                        continue
                    r = json.loads(line)
                    ch = r.get("utm_source") or r.get("channel") or "unknown"
                    ev = r.get("event") or "touch"
                    by_channel[ch] = by_channel.get(ch, 0) + 1
                    by_event[ev] = by_event.get(ev, 0) + 1
                    if ev == "payment":
                        mrr_inr += int(r.get("amount_inr") or 0)
    except Exception:
        pass
    return {
        "by_channel": by_channel,
        "by_event": by_event,
        "attributed_mrr_inr": mrr_inr,
        "touches": sum(by_channel.values()),
    }


__all__ = ["record_touch", "link_payment", "summary"]
