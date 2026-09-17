"""L4 owner feed digest — route P0 immediate vs hourly digest (M4 T03).

WHY THIS EXISTS
---------------
ARCH §4(c): P0 → immediate; P1/info → hourly digest (one message). The owner gets
signal, not noise. Digest tail line reports `"verified X / unverified Y"` so the
owner always knows the confidence mix.

DESIGN
------
* Reads the canonical feed (`owner_feed.read_events`) — no second store.
* P0 events are sent **immediately** via `app.utils.owner_notify.send_owner`.
* P1/info accumulate into ONE hourly message, deduped per hour.
* **Never raises.** Every step is guarded.
* Egress-only — Hermes owns the Telegram ingress; this module never reads updates.

Evidence label: CODE-PRESENT (pinned by tests/test_owner_notify.py).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_ROUTING_PATH = Path(__file__).resolve().parents[2] / "config" / "telegram" / "owner_notify_routing.yaml"


def load_routing() -> dict[str, Any]:
    """Load the declarative routing map. Never raises (returns defaults on failure)."""
    defaults: dict[str, Any] = {
        "severity_routing": {"P0": "owner_alerts", "P1": "internal_admin", "info": "internal_admin"},
        "digest": {"enabled": True, "tail_line": "verified {verified} / unverified {unverified}", "max_items": 25},
        "force_unverified_sources": ["workforce"],
    }
    try:
        if _ROUTING_PATH.exists():
            with open(_ROUTING_PATH, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            if isinstance(data, dict):
                return data
    except Exception as e:
        logger.warning("[owner_feed_digest] routing load failed: %s", e)
    return defaults


def route_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Split events into immediate (P0) vs digest (P1/info). Never raises.

    Returns ``{"immediate": [...], "digest": [...], "verified": n, "unverified": n}``.
    """
    immediate: list[dict[str, Any]] = []
    digest: list[dict[str, Any]] = []
    verified = 0
    unverified = 0
    for ev in events or []:
        try:
            sev = str(ev.get("severity") or "info")
            if bool(ev.get("verified")):
                verified += 1
            else:
                unverified += 1
            if sev == "P0":
                immediate.append(ev)
            else:
                digest.append(ev)
        except Exception:
            continue
    return {"immediate": immediate, "digest": digest, "verified": verified, "unverified": unverified}


def format_digest(events: list[dict[str, Any]], *, routing: dict[str, Any] | None = None) -> str:
    """Build the single hourly digest message with the verified/unverified tail."""
    routing = routing or load_routing()
    max_items = int((routing.get("digest") or {}).get("max_items", 25) or 25)
    routed = route_events(events)
    lines: list[str] = ["📊 Owner hourly digest"]
    for ev in routed["digest"][-max_items:]:
        tag = "✅" if ev.get("verified") else "⚠️"
        lines.append(f"{tag} [{ev.get('severity', 'info')}] {ev.get('text', '')}")
    tail_tpl = str((routing.get("digest") or {}).get("tail_line", "verified {verified} / unverified {unverified}"))
    tail = tail_tpl.format(verified=routed["verified"], unverified=routed["unverified"])
    lines.append(f"\n{tail}")
    return "\n".join(lines)


def send_immediate(events: list[dict[str, Any]], *, dry_run: bool = False) -> int:
    """Send P0 events immediately via owner_notify. Returns count sent. Never raises."""
    sent = 0
    try:
        from app.utils.owner_notify import send_owner

        for ev in route_events(events)["immediate"]:
            ok = send_owner(
                str(ev.get("text", "")),
                severity="P0",
                evidence=str(ev.get("evidence", "")) or None,
                dedupe_key=ev.get("dedupe_key") or f"p0:{ev.get('ts', time.time())}",
                source=str(ev.get("source", "owner_notify")),
                actor=str(ev.get("actor", "system")),
                dry_run=dry_run,
            )
            sent += 1 if ok else 0
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("[owner_feed_digest] immediate send failed: %s", e)
    return sent


def run_digest(*, limit: int = 200, dry_run: bool = False) -> dict[str, Any]:
    """One digest pass: read feed → route → immediate P0 + hourly digest. Never raises."""
    result: dict[str, Any] = {"immediate": 0, "digest_sent": False, "total": 0, "verified": 0, "unverified": 0}
    try:
        from app.utils import owner_feed

        events, _corrupt = owner_feed.read_events(limit=limit)
        result["total"] = len(events)
        routed = route_events(events)
        result["verified"] = routed["verified"]
        result["unverified"] = routed["unverified"]
        result["immediate"] = send_immediate(events, dry_run=dry_run)

        if routed["digest"]:
            routing = load_routing()
            digest_text = format_digest(events, routing=routing)
            if dry_run:
                result["digest_sent"] = True
            else:
                from app.utils.owner_notify import send_owner

                group = (routing.get("severity_routing") or {}).get("P1", "internal_admin")
                hour_bucket = int(time.time() // 3600)
                result["digest_sent"] = send_owner(
                    digest_text,
                    severity="P1",
                    evidence="data/owner_feed_events.jsonl",
                    dedupe_key=f"digest:hourly:{hour_bucket}",
                    group=group,
                    source="owner_feed_digest",
                    actor="kavya",
                )
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("[owner_feed_digest] digest pass failed: %s", e)
    return result


__all__ = ["load_routing", "route_events", "format_digest", "send_immediate", "run_digest"]
