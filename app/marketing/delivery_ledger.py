"""Delivery Ledger — single source-of-truth per-customer VALUE timeline.

WHY: paying customers (jiya makeover, ₹1,999) saw NO visible value because there
was no persistent, customer-facing record of "AI ne aapke liye kya kiya". The one
real event table (`agent_events`) is STAFF-scoped (cross-customer leak risk — do
NOT reuse). This module is the **PULL-first** (dashboard-surfaced, no WhatsApp
dependency) per-customer event log that powers:
  - customer Home  → "AI ne aapke liye kya kiya" timeline
  - customer Reports → weekly benefit summary
  - admin Command Center → paying / stuck / value-receiving rollups
  - admin Customer 360 → full technical + business timeline
  - admin Delivery Queue → who is blocked / what failed / retry

Design (mirrors clients_store.py conventions — jsonl-first, never-raise):
  - Append-only `data/delivery_ledger/<cid>.jsonl`. One line = one event.
  - Canonical EVENT_TYPES (mission Phase 4). Each event has a customer-facing
    Hinglish label + admin-facing technical label + icon (see LABELS).
  - `log_event(cid, event, ...)` — never raises; optional `key` for idempotent
    (dedupe) writes so re-runs / backfills don't double-count.
  - read helpers: `timeline` / `summary` / `customer_view` / `admin_view`.
  - `backfill_from_sources(cid)` — one-time derive from existing stores
    (content_queue, delivery_state, inquiries) so EXISTING customers aren't blank
    on day one. Idempotent (per-event `key` + a marker file).

The ledger APPEND is always-on, additive, never-raise — it RECORDS what happened,
it does NOT send anything. WhatsApp/social PUSH stays gated in
customer_delivery.py / social_engine (ban-safety). Visible value = this PULL log.

Module-level path consts (`_LEDGER_DIR`, `_CONTENT_QUEUE_DIR`) are exposed for
test monkeypatch.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Test-monkeypatchable — always read through these consts (mirror clients_store).
_LEDGER_DIR = os.path.join("data", "delivery_ledger")
_CONTENT_QUEUE_DIR = os.path.join("data", "content_queue")

# --------------------------------------------------------------------------- #
# Canonical event vocabulary (mission Phase 4). event -> (icon, customer_hi,
# admin_en, customer_visible). customer_visible=False = internal/ops-only (raw
# failures + admin actions are NOT shown to the shop owner as jargon; the customer
# instead sees a simple blocked STATE via post_failed / the setup checklist).
# --------------------------------------------------------------------------- #
LABELS: dict[str, tuple[str, str, str, bool]] = {
    "customer_created": ("🆕", "Aapka account ban gaya", "Customer record created", True),
    "plan_activated": ("✅", "Aapka plan activate ho gaya", "Plan activated", True),
    "onboarding_started": ("⚙️", "AI ne aapka setup shuru kiya", "Onboarding started", True),
    "onboarding_completed": ("🎉", "Setup poora — business site + content taiyaar", "Onboarding completed", True),
    "marketing_calendar_generated": ("🗓️", "7-din ka marketing calendar ban gaya", "Marketing calendar generated", True),
    "post_draft_created": ("📝", "Naya post draft ready — approve karein", "Post draft created", True),
    "post_approved": ("👍", "Aapne post approve kiya", "Post approved", True),
    "post_published": ("📢", "Post publish ho gaya", "Post published", True),
    "post_failed": ("⚠️", "Post publish nahi ho paaya — account connect karein", "Post publish failed", True),
    "lead_captured": ("📥", "Naya lead aaya", "Lead captured", True),
    "followup_sent": ("💬", "Follow-up message bheja gaya", "Follow-up sent", True),
    "weekly_report_generated": ("📊", "Is hafte ki report taiyaar", "Weekly report generated", True),
    "automation_failed": ("🚨", "Ek background kaam ruk gaya — team dekh rahi hai", "Automation failed", False),
    "admin_manual_action": ("🛠️", "", "Admin manual action", False),
}
EVENT_TYPES: frozenset[str] = frozenset(LABELS.keys())

# Events that represent published/real marketing OUTPUT (for "value delivered").
_VALUE_EVENTS = {"onboarding_completed", "post_published", "lead_captured", "followup_sent"}


# --------------------------------------------------------------------------- #
# Low-level file helpers (best-effort lock, never raise — mirror clients_store).
# --------------------------------------------------------------------------- #
def _ledger_path(cid: str) -> str:
    return os.path.join(_LEDGER_DIR, f"{cid}.jsonl")


def _marker_path(cid: str) -> str:
    return os.path.join(_LEDGER_DIR, f"{cid}.backfilled")


def _lock(path: str):
    try:
        from filelock import FileLock

        return FileLock(path + ".lock", timeout=5)
    except Exception:
        import contextlib

        return contextlib.nullcontext()


def _read_events(cid: str) -> list[dict[str, Any]]:
    """All raw events for a client (parse-safe; corrupt lines skip). Never raises."""
    path = _ledger_path(str(cid or "").strip())
    out: list[dict[str, Any]] = []
    try:
        if not os.path.isfile(path):
            return out
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if isinstance(rec, dict) and rec.get("event"):
                        out.append(rec)
                except Exception:
                    continue
    except Exception as exc:  # pragma: no cover
        logger.warning("delivery_ledger read err (%s): %s", cid, exc)
    return out


def _existing_keys(cid: str) -> set[str]:
    return {str(r.get("key")) for r in _read_events(cid) if r.get("key")}


# --------------------------------------------------------------------------- #
# WRITE
# --------------------------------------------------------------------------- #
def log_event(
    client_id: str,
    event: str,
    *,
    detail: str = "",
    meta: dict[str, Any] | None = None,
    actor: str = "system",
    key: str | None = None,
) -> bool:
    """Append one ledger event for a customer. Never raises. Returns True if
    written. `key` = idempotency token: if an event with the same key already
    exists for this client, the write is SKIPPED (safe re-runs / backfills).
    Unknown event types are ignored (returns False)."""
    cid = str(client_id or "").strip()
    if not cid or event not in EVENT_TYPES:
        return False
    try:
        os.makedirs(_LEDGER_DIR, exist_ok=True)
        if key and str(key) in _existing_keys(cid):
            return False
        rec: dict[str, Any] = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "client_id": cid,
            "event": event,
            "detail": str(detail or "")[:400],
            "actor": str(actor or "system")[:40],
        }
        if key:
            rec["key"] = str(key)[:160]
        if isinstance(meta, dict) and meta:
            # keep meta small + json-safe
            try:
                rec["meta"] = json.loads(json.dumps(meta, ensure_ascii=False, default=str))
            except Exception:
                pass
        path = _ledger_path(cid)
        try:
            with _lock(path):
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:  # lock timeout etc. — fall back to unlocked append
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception as exc:
        logger.warning("delivery_ledger log_event err (%s/%s): %s", cid, event, exc)
        return False


# --------------------------------------------------------------------------- #
# READ / VIEW
# --------------------------------------------------------------------------- #
def _enrich(rec: dict[str, Any], *, customer: bool) -> dict[str, Any]:
    ev = str(rec.get("event") or "")
    icon, cust_hi, admin_en, visible = LABELS.get(ev, ("•", ev, ev, True))
    label = cust_hi if customer else admin_en
    return {
        "at": rec.get("at"),
        "event": ev,
        "icon": icon,
        "label": label or admin_en or ev,
        "detail": rec.get("detail") or "",
        "actor": rec.get("actor") or "system",
        "customer_visible": visible,
        "meta": rec.get("meta") or {},
    }


def timeline(client_id: str, limit: int = 50, *, customer_only: bool = False) -> list[dict[str, Any]]:
    """Enriched events, newest first. customer_only=True drops internal/ops events
    and uses the Hinglish labels. Never raises."""
    events = _read_events(client_id)
    events.sort(key=lambda r: str(r.get("at") or ""), reverse=True)
    out: list[dict[str, Any]] = []
    for r in events:
        ev = str(r.get("event") or "")
        _, _, _, visible = LABELS.get(ev, ("•", ev, ev, True))
        if customer_only and not visible:
            continue
        out.append(_enrich(r, customer=customer_only))
        if len(out) >= max(1, limit):
            break
    return out


def summary(client_id: str) -> dict[str, Any]:
    """Roll-up counts for a customer (drives Home/Reports/Command Center/360).
    Pulls delivery_state from clients_store best-effort. Never raises."""
    cid = str(client_id or "").strip()
    events = _read_events(cid)
    counts: dict[str, int] = {}
    last_at = ""
    for r in events:
        ev = str(r.get("event") or "")
        counts[ev] = counts.get(ev, 0) + 1
        at = str(r.get("at") or "")
        if at > last_at:
            last_at = at
    delivery_state = ""
    try:
        from app.marketing import clients_store

        c = clients_store.get_client(cid) or {}
        delivery_state = str(c.get("delivery_state") or "")
    except Exception:
        pass
    value_events = sum(counts.get(e, 0) for e in _VALUE_EVENTS)
    return {
        "client_id": cid,
        "events_total": len(events),
        "posts_created": counts.get("post_draft_created", 0),
        "posts_approved": counts.get("post_approved", 0),
        "posts_published": counts.get("post_published", 0),
        "posts_failed": counts.get("post_failed", 0),
        "leads": counts.get("lead_captured", 0),
        "followups": counts.get("followup_sent", 0),
        "reports": counts.get("weekly_report_generated", 0),
        "automation_failures": counts.get("automation_failed", 0),
        "last_event_at": last_at,
        "delivery_state": delivery_state,
        "value_delivered": value_events > 0,
        "counts": counts,
    }


def customer_view(client_id: str, limit: int = 30) -> dict[str, Any]:
    """"AI ne aapke liye kya kiya" — customer-safe timeline + summary. Never raises."""
    return {
        "timeline": timeline(client_id, limit=limit, customer_only=True),
        "summary": summary(client_id),
    }


def admin_view(client_id: str, limit: int = 80) -> dict[str, Any]:
    """Full technical + business timeline for Customer 360. Never raises."""
    return {
        "timeline": timeline(client_id, limit=limit, customer_only=False),
        "summary": summary(client_id),
    }


# --------------------------------------------------------------------------- #
# BACKFILL — derive events for EXISTING customers from already-real stores so the
# timeline isn't blank on day one. Idempotent (per-event `key` + marker file).
# --------------------------------------------------------------------------- #
def _backfill_content_queue(cid: str) -> int:
    """content_queue/<cid>.jsonl -> post_draft_created / post_approved /
    post_published events (keyed by row index so re-runs don't duplicate)."""
    path = os.path.join(_CONTENT_QUEUE_DIR, f"{cid}.jsonl")
    n = 0
    try:
        if not os.path.isfile(path):
            return 0
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    it = json.loads(line)
                except Exception:
                    continue
                if not isinstance(it, dict):
                    continue
                title = str(it.get("title") or it.get("type") or it.get("kind") or "post")[:120]
                status = str(it.get("status") or "").strip().lower()
                if log_event(cid, "post_draft_created", detail=title, actor="backfill", key=f"cq:{i}:draft"):
                    n += 1
                if status in ("approved", "scheduled") and log_event(
                    cid, "post_approved", detail=title, actor="backfill", key=f"cq:{i}:approved"
                ):
                    n += 1
                if status in ("posted", "published", "sent") and log_event(
                    cid, "post_published", detail=title, actor="backfill", key=f"cq:{i}:published"
                ):
                    n += 1
    except Exception as exc:  # pragma: no cover
        logger.warning("backfill content_queue err (%s): %s", cid, exc)
    return n


def _backfill_lifecycle(cid: str, client: dict[str, Any]) -> int:
    """Derive lifecycle events from the client record (created/activated/onboarded/
    delivered). Keyed so idempotent."""
    n = 0
    try:
        created = str(client.get("created_at") or "")
        plan = str(client.get("plan") or "").strip().lower()
        if log_event(cid, "customer_created", detail=str(client.get("business_name") or ""),
                     actor="backfill", key="lc:created"):
            n += 1
        if plan and plan not in ("", "free", "trial", "none", "pending"):
            if log_event(cid, "plan_activated", detail=plan, actor="backfill", key="lc:activated"):
                n += 1
        if client.get("setup_done"):
            if log_event(cid, "onboarding_completed", actor="backfill", key="lc:onboarded"):
                n += 1
        _ = created  # (kept for parity; timestamps use now — backfill order preserved by key)
    except Exception as exc:  # pragma: no cover
        logger.warning("backfill lifecycle err (%s): %s", cid, exc)
    return n


def backfill_from_sources(cid: str, *, force: bool = False) -> dict[str, Any]:
    """One-time derive ledger events for an existing customer from content_queue +
    the client record. Idempotent: skips if the marker exists (unless force). Even
    without the marker, per-event keys make re-runs safe. Never raises."""
    cid = str(cid or "").strip()
    res: dict[str, Any] = {"client_id": cid, "written": 0, "skipped": False}
    if not cid:
        return res
    try:
        marker = _marker_path(cid)
        if not force and os.path.isfile(marker):
            res["skipped"] = True
            return res
        from app.marketing import clients_store

        client = clients_store.get_client(cid) or {}
        written = _backfill_lifecycle(cid, client) + _backfill_content_queue(cid)
        res["written"] = written
        try:
            os.makedirs(_LEDGER_DIR, exist_ok=True)
            with open(marker, "w", encoding="utf-8") as f:
                f.write(datetime.now(timezone.utc).isoformat(timespec="seconds"))
        except Exception:
            pass
    except Exception as exc:
        logger.warning("backfill_from_sources err (%s): %s", cid, exc)
        res["error"] = str(exc)
    return res


def ensure_backfilled(cid: str) -> None:
    """Lazy backfill on first read (safe to call from a dashboard endpoint).
    Never raises."""
    try:
        if not os.path.isfile(_marker_path(str(cid or "").strip())):
            backfill_from_sources(cid)
    except Exception:
        pass


__all__ = [
    "EVENT_TYPES",
    "LABELS",
    "log_event",
    "timeline",
    "summary",
    "customer_view",
    "admin_view",
    "backfill_from_sources",
    "ensure_backfilled",
]
