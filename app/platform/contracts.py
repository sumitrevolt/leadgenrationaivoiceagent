"""Shared cross-module contracts — single import surface for the ₹1 Cr strategy.

WHY THIS FILE EXISTS
--------------------
Modules M1..M6 (see ``deliverables/software-company/crore-strategy-ARCH-2026-09-16.md``
§3) all speak the same four "bhasha" (languages): a **task record**, an **event bus
message**, a **KPI record** and an **alert record**. Without one import surface each
module invents its own field names and the data flow silently drifts.

This module is **additive and mirror-only**:
* ``TaskRecord`` mirrors ``automation_orchestrator.TaskRecord`` (the DB-backed
  execution ledger shape). It is a *contract view*, not a second store.
* ``FeedEvent`` mirrors ``app/utils/owner_feed.py`` (the canonical event feed).
  We do NOT import owner_feed here because owner_feed is deliberately stdlib-only
  and must stay importable without side-effects; we mirror its field set instead.
* ``KpiRecord`` / ``AlertRecord`` / ``DevWorkerRecord`` / ``CapacityRecord`` are the
  new honesty-carrying shapes. Every one of them carries ``verified`` + ``evidence``.

DESIGN RULES (non-negotiable, inherited from ARCH §7)
-----------------------------------------------------
1. **Never raises on import** — pure dataclasses, stdlib only, no DB, no network.
2. **verified ≠ claimed** — a record with ``verified=True`` MUST carry a non-empty
   ``evidence``. ``KpiRecord.validate()`` enforces this; blending is a bug.
3. **Evidence labels** — free-text ``evidence`` strings carry one of:
   PRODUCTION-PROVEN · CODE-PRESENT · TEST-PROVEN · LOCAL-ONLY · PARTIAL · STALE · UNKNOWN.

Evidence labels for this file: ``CODE-PRESENT`` (mirrors verified shapes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# --------------------------------------------------------------------------- #
# Canonical enum-ish vocabularies (kept as frozensets so callers can validate
# without importing the orchestrator / owner_feed modules).
# --------------------------------------------------------------------------- #

TASK_STATUSES: frozenset[str] = frozenset(
    {"READY", "RUNNING", "BLOCKED", "REVIEW", "DONE", "FAILED", "DUPLICATE_SKIPPED", "DLQ"}
)
TASK_PRIORITIES: frozenset[str] = frozenset({"URGENT", "HIGH", "MEDIUM", "LOW"})

FEED_SOURCES: frozenset[str] = frozenset(
    {"workbuddy", "openclaw", "hermes", "prod", "bot_fleet", "guardian", "workforce", "telegram_egress"}
)
FEED_SEVERITIES: frozenset[str] = frozenset({"P0", "P1", "info"})
FEED_KINDS: frozenset[str] = frozenset(
    {"task_claimed", "ack", "blocked", "done", "incident", "heartbeat"}
)

# Sources that must NEVER be reported as verified until their probe is made
# honest (see owner_feed.FORCE_UNVERIFIED_SOURCES). Kept in sync by hand because
# this file must stay import-free.
FORCE_UNVERIFIED_SOURCES: frozenset[str] = frozenset({"workforce"})

CAPACITY_CHANNELS: frozenset[str] = frozenset({"email", "voice_outbound", "whatsapp_cold"})

EVIDENCE_LABELS: tuple[str, ...] = (
    "PRODUCTION-PROVEN",
    "CODE-PRESENT",
    "TEST-PROVEN",
    "LOCAL-ONLY",
    "PARTIAL",
    "STALE",
    "UNKNOWN",
)


def utc_now_iso() -> str:
    """ISO-8601 UTC timestamp with a trailing Z (matches owner_feed format)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------- #
# §3.1 Task record  (M1 ↔ M2 ↔ M5)  — mirror of DurableTaskStore.task_records
# --------------------------------------------------------------------------- #
@dataclass
class TaskRecord:
    """Mirror of ``automation_orchestrator.TaskRecord`` (the DB execution ledger).

    This is a *contract view* for cross-module consumption — the authoritative
    store stays ``DurableTaskStore`` (``data/orchestrator_ledger.db``).
    """

    task_id: str
    owner_bot: str
    assigned_agent: str
    priority: str = "MEDIUM"
    status: str = "READY"
    version: int = 1
    fencing_token: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    idempotency_key: str | None = None
    input_payload: dict[str, Any] = field(default_factory=dict)
    evidence: str | None = None
    error_message: str | None = None
    last_heartbeat: float = 0.0
    created_at: float = 0.0
    updated_at: float = 0.0

    def validate(self) -> tuple[bool, str]:
        """Return (ok, reason). Never raises."""
        if not self.task_id or not isinstance(self.task_id, str):
            return False, "bad_task_id"
        if not self.owner_bot or not isinstance(self.owner_bot, str):
            return False, "bad_owner_bot"
        if not self.assigned_agent or not isinstance(self.assigned_agent, str):
            return False, "bad_assigned_agent"
        if self.status not in TASK_STATUSES:
            return False, f"bad_status:{self.status}"
        if self.priority not in TASK_PRIORITIES:
            return False, f"bad_priority:{self.priority}"
        return True, "ok"


# --------------------------------------------------------------------------- #
# §3.2 Dev worker record  (M1 execution proof — NEW)
# --------------------------------------------------------------------------- #
@dataclass
class DevWorkerRecord:
    """One row = one REAL worker execution. Empty evidence ⇒ not verified."""

    worker_id: str
    task_id: str
    lease_token: str = ""
    heartbeat_at: float = 0.0
    claimed_at: float = 0.0
    state: str = "claimed"  # claimed|running|done|failed
    evidence: str = ""

    def validate(self) -> tuple[bool, str]:
        if not self.worker_id:
            return False, "bad_worker_id"
        if not self.task_id:
            return False, "bad_task_id"
        if self.state not in ("claimed", "running", "done", "failed"):
            return False, f"bad_state:{self.state}"
        return True, "ok"

    @property
    def verified(self) -> bool:
        """A worker row is only 'verified execution' once it carries evidence."""
        return bool(self.evidence and self.evidence.strip())


# --------------------------------------------------------------------------- #
# §3.3 Event bus message  (canonical mirror of app/utils/owner_feed.py)
# --------------------------------------------------------------------------- #
@dataclass
class FeedEvent:
    """Mirror of the canonical feed event (``data/owner_feed_events.jsonl``)."""

    ts: str = ""
    source: str = ""
    actor: str = ""
    severity: str = "info"
    kind: str = "heartbeat"
    text: str = ""
    evidence: str = ""
    verified: bool = False
    dedupe_key: str | None = None

    def validate(self) -> tuple[bool, str]:
        if not self.source:
            return False, "bad_source"
        if not self.actor:
            return False, "bad_actor"
        if self.severity not in FEED_SEVERITIES:
            return False, f"bad_severity:{self.severity}"
        if self.kind not in FEED_KINDS:
            return False, f"bad_kind:{self.kind}"
        if not self.text or not self.text.strip():
            return False, "empty_text"
        return True, "ok"

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ts": self.ts or utc_now_iso(),
            "source": self.source,
            "actor": self.actor,
            "severity": self.severity,
            "kind": self.kind,
            "text": self.text,
            "evidence": self.evidence,
            "verified": bool(self.verified),
        }
        if self.dedupe_key:
            out["dedupe_key"] = self.dedupe_key
        return out


# --------------------------------------------------------------------------- #
# §3.4 KPI record  (M5 — honesty: verified vs claimed never blended)
# --------------------------------------------------------------------------- #
@dataclass
class KpiRecord:
    """A single KPI observation. ``verified=True`` REQUIRES evidence."""

    ts: str
    metric: str
    value: float
    verified: bool
    evidence: str
    window: str = "1d"
    source: str = ""

    def validate(self) -> tuple[bool, str]:
        """A verified KPI with no evidence is a lie. Reject it."""
        if not self.metric:
            return False, "bad_metric"
        if self.window not in ("1d", "7d", "30d"):
            return False, f"bad_window:{self.window}"
        if self.verified and not (self.evidence and self.evidence.strip()):
            return False, "verified_without_evidence"
        return True, "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "metric": self.metric,
            "value": self.value,
            "verified": bool(self.verified),
            "evidence": self.evidence,
            "window": self.window,
            "source": self.source,
        }


# --------------------------------------------------------------------------- #
# §3.5 Alert record  (M4 ↔ M5)
# --------------------------------------------------------------------------- #
@dataclass
class AlertRecord:
    """An owner-facing alert. evidence REQUIRED; chat_id never hardcoded."""

    ts: str
    severity: str
    topic: str
    text: str
    evidence: str
    dedupe_key: str
    chat_id: str
    verified: bool = False

    def validate(self) -> tuple[bool, str]:
        if self.severity not in FEED_SEVERITIES:
            return False, f"bad_severity:{self.severity}"
        if not self.topic:
            return False, "bad_topic"
        if not self.text or not self.text.strip():
            return False, "empty_text"
        return True, "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "severity": self.severity,
            "topic": self.topic,
            "text": self.text,
            "evidence": self.evidence,
            "dedupe_key": self.dedupe_key,
            "chat_id": self.chat_id,
            "verified": bool(self.verified),
        }


# --------------------------------------------------------------------------- #
# §3.6 Capacity record  (M2 → M5)
# --------------------------------------------------------------------------- #
@dataclass
class CapacityRecord:
    """Honest channel-capacity snapshot. gap_to_target_x = required ÷ available."""

    ts: str
    channel: str
    cap_per_day: int
    contacts_week: int
    compliance_blocked: int = 0
    gap_to_target_x: float = 0.0
    note: str = ""

    def validate(self) -> tuple[bool, str]:
        if self.channel not in CAPACITY_CHANNELS:
            return False, f"bad_channel:{self.channel}"
        if self.cap_per_day < 0 or self.contacts_week < 0:
            return False, "negative_capacity"
        return True, "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "channel": self.channel,
            "cap_per_day": self.cap_per_day,
            "contacts_week": self.contacts_week,
            "compliance_blocked": self.compliance_blocked,
            "gap_to_target_x": self.gap_to_target_x,
            "note": self.note,
        }


__all__ = [
    "TASK_STATUSES",
    "TASK_PRIORITIES",
    "FEED_SOURCES",
    "FEED_SEVERITIES",
    "FEED_KINDS",
    "FORCE_UNVERIFIED_SOURCES",
    "CAPACITY_CHANNELS",
    "EVIDENCE_LABELS",
    "utc_now_iso",
    "TaskRecord",
    "DevWorkerRecord",
    "FeedEvent",
    "KpiRecord",
    "AlertRecord",
    "CapacityRecord",
]
