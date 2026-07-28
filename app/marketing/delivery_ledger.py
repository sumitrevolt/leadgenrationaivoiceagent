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

The ledger APPEND is always-on, additive — it RECORDS what happened,
it does NOT send anything. WhatsApp/social PUSH stays gated in
customer_delivery.py / social_engine (ban-safety). Visible value = this PULL log.

Path resolvers (`_LEDGER_DIR`, `_CONTENT_QUEUE_DIR`) are call-time functions —
test monkeypatch returns a tmp dir string. Unresolvable authority must REPORT
FAILURE (writes return False; reads raise), never silently look empty.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _LEDGER_DIR() -> str:
    """Per-tenant delivery ledger directory — resolved per call, never frozen at import."""
    from app.platform import runtime_data_authority as _auth

    return str(
        _auth.resolve_store_path(
            store_id="delivery.ledger",
            legacy_path=Path("data") / "delivery_ledger",
            target_segments=("delivery", "ledger"),
        )
    )


def _CONTENT_QUEUE_DIR() -> str:
    """Content queue directory (backfill source) — same store id as auto_content/staff."""
    from app.platform import runtime_data_authority as _auth

    return str(
        _auth.resolve_store_path(
            store_id="content.queue",
            legacy_path=Path("data") / "content_queue",
            target_segments=("content", "queue"),
        )
    )


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
    "onboarding_completed": (
        "🎉",
        "Setup poora — business site + content taiyaar",
        "Onboarding completed",
        True,
    ),
    "social_setup_completed": (
        "🌐",
        "Aapne social accounts connect kar diye",
        "Social setup completed",
        True,
    ),
    "marketing_calendar_generated": (
        "🗓️",
        "7-din ka marketing calendar ban gaya",
        "Marketing calendar generated",
        True,
    ),
    "post_draft_created": (
        "📝",
        "Naya post draft ready — approve karein",
        "Post draft created",
        True,
    ),
    "post_approved": ("👍", "Aapne post approve kiya", "Post approved", True),
    "post_published": ("📢", "Post publish ho gaya", "Post published", True),
    "post_failed": (
        "⚠️",
        "Post publish nahi ho paaya — account connect karein",
        "Post publish failed",
        True,
    ),
    "lead_captured": ("📥", "Naya lead aaya", "Lead captured", True),
    "followup_sent": ("💬", "Follow-up message bheja gaya", "Follow-up sent", True),
    "weekly_report_generated": (
        "📊",
        "Is hafte ki report taiyaar",
        "Weekly report generated",
        True,
    ),
    "automation_failed": (
        "🚨",
        "Ek background kaam ruk gaya — team dekh rahi hai",
        "Automation failed",
        False,
    ),
    "admin_manual_action": ("🛠️", "", "Admin manual action", False),
    # Product 1 Customer Deliverability layer (2026-07-08) — Customer Health +
    # Approval Reminder + SLA Recovery agents log through these. Additive only;
    # existing 13 event types + their behaviour are unchanged.
    "approval_reminded": (
        "⏰",
        "Aapka post approval ka wait kar raha hai",
        "Approval reminder raised",
        True,
    ),
    "sla_breached": (
        "🔴",
        "Delivery me deri ho rahi — team ko notify kar diya gaya",
        "Customer delivery SLA breached",
        False,
    ),
    "sla_recovered": (
        "🟢",
        "Delivery wapas track pe aa gayi",
        "Customer delivery SLA recovered",
        False,
    ),
    # Integration Health Agent (2026-07-08) — a PLATFORM integration (SMTP/
    # WhatsApp/Vobiz/Pollinations/scheduler queue) failing enough to impact this
    # specific customer's delivery. Internal-only (customer sees the existing
    # generic "team is on it" note via customer_status_notes, never the raw
    # integration name/error).
    "integration_failed": (
        "🔌",
        "",
        "Platform integration failing — impacts this customer's delivery",
        False,
    ),
    # Video Creative Pipeline (2026-07-10) — Phase 1, generic recipe only.
    "video_render_started": ("🎬", "Aapka video ban raha hai", "Video render started", True),
    "video_qa_failed": ("⚠️", "", "Video QA check failed — not published", False),
    "video_render_failed": ("⚠️", "", "Video render failed", False),
    "video_ready": (
        "🎥",
        "Naya video taiyaar — approve karein",
        "Video render succeeded, pending approval",
        True,
    ),
    # Loop-social-6 (2026-07-11) — canonical social-delivery event enum (Phase 9).
    # Additive only: `social_setup_completed` (existing, per-customer aggregate)
    # kept; `social_account_connected` is the finer-grained per-platform connect
    # event that Loop-social-1's `/social/accounts/connect` route emits. Publish-
    # lifecycle events cover the transitions the queue drain moves through
    # (queued → processing → published/partial/retry/dead/cancelled). Token +
    # customer-action events surface states the admin cockpit + customer
    # timeline must act on. customer_visible=False for pure ops noise.
    "social_account_connected": (
        "🔗",
        "Ek social account connect ho gaya",
        "Social account connected (per-platform)",
        True,
    ),
    "social_account_disconnected": (
        "🔓",
        "Ek social account disconnect ho gaya",
        "Social account disconnected (per-platform)",
        True,
    ),
    "social_account_connection_failed": (
        "🚫",
        "Social account connect nahi hua — dobara try karein",
        "Social account connection failed",
        True,
    ),
    "token_refreshed": ("🔁", "", "Provider token refreshed", False),
    "token_expired": (
        "🕓",
        "Ek social account ka access expire ho gaya — reconnect karein",
        "Provider token expired",
        True,
    ),
    "post_scheduled": ("📅", "Post schedule ho gaya", "Post scheduled for publish", True),
    "post_publish_started": ("🚀", "", "Post publish attempt started", False),
    "post_partially_published": (
        "🟡",
        "Post kuch platforms pe gaya — kuch pending",
        "Post partially published across platforms",
        True,
    ),
    "post_retry_scheduled": ("↩️", "", "Post publish retry scheduled", False),
    "post_cancelled": ("🛑", "Aapne post cancel kar diya", "Post cancelled", True),
    "customer_action_required": (
        "⚠️",
        "Ek kaam aapki attention chahiye",
        "Customer action required",
        True,
    ),
    # Evidence-hygiene loop (2026-07-11 P0). Non-publication audit marker for
    # `content_approval.update_evidence_url` — records that an evidence URL
    # was rewritten (typically retroactive PII cleanup) WITHOUT counting as a
    # fresh publication. customer_visible=False: this is admin/audit-only;
    # customer already saw the original `post_published` event.
    "evidence_amended": (
        "🔧",
        "",
        "Evidence URL amended (audit-only, not a new publication)",
        False,
    ),
    # Delivery gate (2026-07-12) — intentional hold, NOT a failure. Logged when
    # AUTO_DELIVER_VALUE is OFF or phone missing — ops-only, doesn't count toward
    # automation_failed or trigger RED health flags.
    "delivery_gated": ("⏸️", "", "Delivery gated (intentional hold, not a failure)", False),
    # Identity alias link (2026-07-19) — marketing id ↔ billing/login id binding.
    # Internal-only; customer portal already resolves via billing_client_ids.
    "identity_alias_linked": ("🔗", "", "Billing/login alias linked to marketing client", False),
}
EVENT_TYPES: frozenset[str] = frozenset(LABELS.keys())

# Events that represent published/real marketing OUTPUT (for "value delivered").
_VALUE_EVENTS = {
    "onboarding_completed",
    "social_setup_completed",
    "post_published",
    "lead_captured",
    "followup_sent",
}

# Events that mean "something broke and needs attention" (for at-risk / failures).
_FAILURE_EVENTS = {"post_failed", "automation_failed"}


# --------------------------------------------------------------------------- #
# Low-level file helpers (best-effort lock, never raise — mirror clients_store).
# --------------------------------------------------------------------------- #
def _safe_stem(cid: str) -> str:
    """Refuse a tenant id that would place the file outside its own store.

    The ledger filename IS the tenant boundary: `data/delivery_ledger/<cid>.jsonl`.
    An id of `../email_suppression` resolved to a real compliance file, so this
    guard covers reads as well as writes — a traversal read is a cross-tenant
    leak, not a harmless miss.

    Deliberately REFUSES rather than coercing. `auto_content._safe_id` rewrites
    offending characters, which stops the escape but silently files a tenant's
    rows under a different name; for a customer's delivery history that
    misplacement is itself the bug.
    """
    from app.platform.runtime_data import _safe_segment

    return _safe_segment(cid)


def _ledger_path(cid: str) -> str:
    return os.path.join(_LEDGER_DIR(), f"{_safe_stem(cid)}.jsonl")


def _marker_path(cid: str) -> str:
    return os.path.join(_LEDGER_DIR(), f"{_safe_stem(cid)}.backfilled")


def _lock(path: str):
    try:
        from filelock import FileLock

        return FileLock(path + ".lock", timeout=5)
    except Exception:
        import contextlib

        return contextlib.nullcontext()


def _read_events(cid: str) -> list[dict[str, Any]]:
    """All raw events for a client (parse-safe; corrupt lines skip).

    Missing file → []. Unresolvable authority → raises (never looks like
    "customer has no history").
    """
    from app.platform import runtime_data as _rd

    try:
        # Probe then re-resolve at each I/O site — no local bind.
        _LEDGER_DIR()
    except Exception as exc:
        logger.error("delivery_ledger authority UNRESOLVABLE (%s): %s", cid, exc)
        if isinstance(exc, _rd.RuntimeDataError):
            raise
        raise _rd.RuntimeDataError(f"delivery.ledger authority unresolvable: {exc}") from exc
    out: list[dict[str, Any]] = []
    try:
        if not os.path.isfile(_ledger_path(str(cid or "").strip())):
            return out
        with open(_ledger_path(str(cid or "").strip()), encoding="utf-8") as f:
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
    except _rd.RuntimeDataError:
        raise
    except Exception as exc:  # pragma: no cover
        logger.warning("delivery_ledger read err (%s): %s", cid, exc)
    return out


def _existing_keys(cid: str) -> set[str]:
    return {str(r.get("key")) for r in _read_events(cid) if r.get("key")}


def _parse_at(at: Any) -> datetime | None:
    """Parse a ledger event `at` ISO timestamp to an aware-UTC datetime.

    Handles both the module's own `+00:00` isoformat and a trailing-`Z` form,
    and coerces naive stamps to UTC. Never raises (returns None on garbage)."""
    s = str(at or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


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
        # Probe then re-resolve at each I/O site — no local bind.
        _LEDGER_DIR()
        os.makedirs(_LEDGER_DIR(), exist_ok=True)
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
        try:
            with _lock(_ledger_path(cid)):
                with open(_ledger_path(cid), "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:  # lock timeout etc. — fall back to unlocked append
            with open(_ledger_path(cid), "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception as exc:
        from app.platform import runtime_data as _rd

        if isinstance(exc, _rd.RuntimeDataError):
            logger.error("delivery_ledger authority UNRESOLVABLE (%s/%s): %s", cid, event, exc)
        else:
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


def timeline(
    client_id: str, limit: int = 50, *, customer_only: bool = False
) -> list[dict[str, Any]]:
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


def recent_counts(client_id: str, hours: int = 168) -> dict[str, Any]:
    """Time-WINDOWED event roll-up (additive to summary(), which is all-time).

    Drives the admin Command Center's delivery-health / at-risk detection:
      - `events_in_window` / `counts` — events whose `at` falls in the last
        `hours` (default 168h = 7 days).
      - `value_events_in_window` — True if any _VALUE_EVENTS landed in that
        window ("value delivered in last 7d").
      - `failures_24h` — count of post_failed/automation_failed in the last 24h
        (fixed 24h regardless of `hours` — this is the at-risk failure signal).

    Never raises — summary()'s existing fields are untouched; this is purely
    additive so callers can ask "recently" instead of "ever"."""
    cid = str(client_id or "").strip()
    now = datetime.now(timezone.utc)
    win_start = now - timedelta(hours=max(1, int(hours or 168)))
    day_start = now - timedelta(hours=24)
    counts: dict[str, int] = {}
    value_in_window = False
    failures_24h = 0
    try:
        for r in _read_events(cid):
            ev = str(r.get("event") or "")
            dt = _parse_at(r.get("at"))
            if dt is None:
                continue
            if dt >= win_start:
                counts[ev] = counts.get(ev, 0) + 1
                if ev in _VALUE_EVENTS:
                    value_in_window = True
            if dt >= day_start and ev in _FAILURE_EVENTS:
                failures_24h += 1
    except Exception as exc:  # pragma: no cover
        logger.warning("delivery_ledger recent_counts err (%s): %s", cid, exc)
    return {
        "client_id": cid,
        "window_hours": int(hours or 168),
        "events_in_window": sum(counts.values()),
        "counts": counts,
        "value_events_in_window": value_in_window,
        "failures_24h": failures_24h,
    }


def customer_view(client_id: str, limit: int = 30) -> dict[str, Any]:
    """ "AI ne aapke liye kya kiya" — customer-safe timeline + summary. Never raises."""
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
    n = 0
    try:
        _CONTENT_QUEUE_DIR()
        if not os.path.isfile(os.path.join(_CONTENT_QUEUE_DIR(), f"{cid}.jsonl")):
            return 0
        with open(os.path.join(_CONTENT_QUEUE_DIR(), f"{cid}.jsonl"), encoding="utf-8") as f:
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
                if log_event(
                    cid, "post_draft_created", detail=title, actor="backfill", key=f"cq:{i}:draft"
                ):
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
        from app.platform import runtime_data as _rd

        if isinstance(exc, _rd.RuntimeDataError):
            logger.error("backfill content_queue authority UNRESOLVABLE (%s): %s", cid, exc)
        else:
            logger.warning("backfill content_queue err (%s): %s", cid, exc)
    return n


def _backfill_lifecycle(cid: str, client: dict[str, Any]) -> int:
    """Derive lifecycle events from the client record (created/activated/onboarded/
    delivered). Keyed so idempotent."""
    n = 0
    try:
        created = str(client.get("created_at") or "")
        plan = str(client.get("plan") or "").strip().lower()
        if log_event(
            cid,
            "customer_created",
            detail=str(client.get("business_name") or ""),
            actor="backfill",
            key="lc:created",
        ):
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
        _LEDGER_DIR()
        if not force and os.path.isfile(_marker_path(cid)):
            res["skipped"] = True
            return res
        from app.marketing import clients_store

        client = clients_store.get_client(cid) or {}
        written = _backfill_lifecycle(cid, client) + _backfill_content_queue(cid)
        res["written"] = written
        try:
            os.makedirs(_LEDGER_DIR(), exist_ok=True)
            with open(_marker_path(cid), "w", encoding="utf-8") as f:
                f.write(datetime.now(timezone.utc).isoformat(timespec="seconds"))
        except Exception:
            pass
    except Exception as exc:
        from app.platform import runtime_data as _rd

        if isinstance(exc, _rd.RuntimeDataError):
            logger.error("backfill_from_sources authority UNRESOLVABLE (%s): %s", cid, exc)
            res["error"] = "delivery_ledger_authority_unavailable"
        else:
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
    "recent_counts",
    "customer_view",
    "admin_view",
    "backfill_from_sources",
    "ensure_backfilled",
]
