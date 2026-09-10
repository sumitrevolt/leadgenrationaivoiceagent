"""Pure hash-chain primitives for the canonical DevTask ledger (stdlib-only).

Deliberately dependency-free (no SQLAlchemy, no ``app.models``) so the chain
math can be unit-tested under a bare interpreter and reused by any storage
backend. Mirrors the append-only ``prev_hash -> event_hash`` scheme already
used in ``app/agents/harness/session.py`` (ADR-180 dsh pattern steal), with two
differences that make it safe as a DURABLE ledger:

  * full 64-hex SHA-256 digest instead of a 16-char prefix;
  * the chain input is a fixed, ordered material string
    ``prev_hash | canonical_json(payload) | from_state | to_state | seq |
    created_at`` so a verifier that only has the stored row can recompute the
    digest byte-for-byte.

Nothing here mutates state and nothing here touches the network.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

GENESIS_HASH = "0" * 64
_HASH_FIELDS_SEPARATOR = "|"


def canonical_json(payload: Any) -> str:
    """Deterministic JSON encoding: sorted keys, compact separators, UTF-8 safe.

    Non-JSON-native values (datetime, Decimal, ...) degrade to ``str()`` via
    ``default=str`` so a hash never raises on an exotic payload value.
    """
    if payload is None:
        payload = {}
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        ensure_ascii=False,
    )


def normalise_created_at(created_at: Any) -> str:
    """Render a created_at value exactly the way it is hashed (ISO-8601)."""
    if created_at is None:
        return ""
    if isinstance(created_at, datetime):
        return created_at.isoformat()
    return str(created_at)


def compute_event_hash(
    *,
    prev_hash: str,
    payload: Any,
    from_state: Any,
    to_state: Any,
    seq: Any,
    created_at: Any,
) -> str:
    """SHA-256 of the ordered chain material. Returns 64 lowercase hex chars."""
    material = _HASH_FIELDS_SEPARATOR.join(
        (
            str(prev_hash or GENESIS_HASH),
            canonical_json(payload),
            "" if from_state is None else str(from_state),
            "" if to_state is None else str(to_state),
            str(int(seq)),
            normalise_created_at(created_at),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _field(event: Any, name: str, default: Any = None) -> Any:
    """Read ``name`` from a mapping or an ORM row without importing SQLAlchemy."""
    if isinstance(event, dict):
        return event.get(name, default)
    return getattr(event, name, default)


def verify_event_chain(events: list[Any]) -> tuple[bool, str]:
    """Verify one task's event chain. Returns ``(ok, reason)``.

    ``events`` must all belong to the SAME task; they are ordered by ``seq``
    before verification (storage order is never trusted).
    """
    if not events:
        return True, "empty"
    try:
        ordered = sorted(events, key=lambda ev: int(_field(ev, "seq", 0) or 0))
    except (TypeError, ValueError):
        return False, "unorderable seq"

    prev = GENESIS_HASH
    for index, event in enumerate(ordered, start=1):
        seq = _field(event, "seq", None)
        try:
            seq_int = int(seq)
        except (TypeError, ValueError):
            return False, f"non-numeric seq at position {index}"
        if seq_int != index:
            return False, f"seq gap: expected {index} got {seq}"
        if str(_field(event, "prev_hash", "") or "") != prev:
            return False, f"prev_hash mismatch at seq={index}"
        expected = compute_event_hash(
            prev_hash=prev,
            payload=_field(event, "payload", None),
            from_state=_field(event, "from_state", None),
            to_state=_field(event, "to_state", None),
            seq=seq_int,
            created_at=_field(event, "created_at", None),
        )
        if str(_field(event, "event_hash", "") or "") != expected:
            return False, f"event_hash mismatch at seq={index}"
        prev = str(_field(event, "event_hash", ""))
    return True, "ok"


__all__ = [
    "GENESIS_HASH",
    "canonical_json",
    "compute_event_hash",
    "normalise_created_at",
    "verify_event_chain",
]
