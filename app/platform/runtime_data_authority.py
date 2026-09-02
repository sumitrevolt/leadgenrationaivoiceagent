"""Tri-state store authority — which path is REALLY in charge, right now.

WHY THIS EXISTS
---------------
`runtime_data.py` answers "where is the runtime root". That is not enough to
migrate a live store, because during a cutover there are three legitimate
answers to "where does this ledger live", and picking the wrong one silently is
how a migration becomes split-brain nobody notices for a week:

    LEGACY                 root unset. The in-checkout path (or the store's own
                           explicit override) is the sole read AND write target.
                           Production behaviour is byte-for-byte unchanged, which
                           is what makes the code migration mergeable on its own.

    MIGRATION_VALIDATION   root configured, but the cutover is not active. The
                           canonical target may be created, copied to and
                           inspected by tooling; live writers do NOT move. No
                           automatic dual-write — two writers with no shared lock
                           is a corruption engine, not a safety net.

    CANONICAL              root configured, cutover enabled, marker VALID and
                           this store listed in it. The external target is the
                           only authority: no legacy write, and no silent legacy
                           read fallback. Missing canonical data FAILS CLOSED,
                           because reading a stale checkout copy after cutover
                           would answer a suppression or consent question with
                           data that is no longer authoritative.

The mode is derived at OPERATION TIME. Nothing here may be captured in a
module-level constant: a path frozen at import is exactly what makes a store
impossible to redirect from a fixture that runs later, and that bug is the
reason this workstream exists.

OVERRIDE POLICY
---------------
Per-store overrides (`VOICE_LAUNCH_KILL_FILE`, `PLATFORM_DIAL_CONFIG`, ...)
already exist in production and must not break on the day this merges. So:

  * LEGACY / MIGRATION_VALIDATION — an explicit override remains the authority,
    exactly as today.
  * CANONICAL — an override is accepted ONLY if it resolves to the canonical
    target itself. Anything else fails closed with a non-secret reason, so a
    forgotten `VOICE_LAUNCH_KILL_FILE=data/...` cannot quietly route an
    emergency control back into the checkout after the cutover.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.platform import runtime_data as rd

#: Deploy-time gate. Declared with the same literal the deployment preflight
#: uses; the two are asserted equal by test, because a drifting name would mean
#: the gate and the application disagree about whether a cutover is live.
CUTOVER_GATE_ENV = "RUNTIME_DATA_CUTOVER_ENABLED"

#: Marker location beneath the runtime root.
MARKER_SEGMENTS = ("migration", "cutover.json")


class AuthorityMode(str, Enum):
    LEGACY = "LEGACY"
    MIGRATION_VALIDATION = "MIGRATION_VALIDATION"
    CANONICAL = "CANONICAL"


class AuthoritySource(str, Enum):
    LEGACY_DEFAULT = "LEGACY_DEFAULT"
    EXPLICIT_OVERRIDE = "EXPLICIT_OVERRIDE"
    CANONICAL_TARGET = "CANONICAL_TARGET"


@dataclass(frozen=True)
class StoreAuthority:
    """Immutable answer for ONE store at ONE moment.

    Deliberately not a bare `Path`: a caller that only sees a path cannot tell
    whether it is holding the legacy file or the canonical one, and every
    read/write/lock/temp decision has to agree on that.
    """

    store_id: str
    mode: AuthorityMode
    active_path: Path
    canonical_path: Path | None
    source: AuthoritySource

    @property
    def is_canonical(self) -> bool:
        return self.mode is AuthorityMode.CANONICAL


def _bool_env(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _root_configured() -> bool:
    """Is a runtime root configured at all? Never raises."""
    try:
        return bool(rd._configured())
    except rd.RuntimeDataError:
        # Canonical and legacy keys disagree in production. That is a hard
        # configuration fault; the resolver reports it when actually used.
        return True


def _marker_store_ids() -> frozenset[str]:
    """Store ids a VALID marker declares migrated. Empty set on any doubt.

    Never raises: an unreadable, malformed or stale marker must degrade to
    "not canonical", which keeps the legacy authority in charge, rather than
    exploding inside an unrelated read path.
    """
    try:
        from app.platform import runtime_data_marker as mk

        marker_path = rd.store_path(*MARKER_SEGMENTS)
        if not marker_path.is_file():
            return frozenset()
        if mk.validate_marker_file(marker_path):
            return frozenset()
        import json

        data = json.loads(marker_path.read_text(encoding="utf-8"))
        ids = data.get("migrated_store_ids") or []
        return frozenset(str(i) for i in ids)
    except Exception:
        return frozenset()


def authority_mode(store_id: str | None = None) -> AuthorityMode:
    """Mode for a store (or the deployment as a whole when store_id is None)."""
    if not _root_configured():
        return AuthorityMode.LEGACY
    if not _bool_env(CUTOVER_GATE_ENV):
        return AuthorityMode.MIGRATION_VALIDATION
    migrated = _marker_store_ids()
    if not migrated:
        return AuthorityMode.MIGRATION_VALIDATION
    if store_id is not None and store_id not in migrated:
        # A partially migrated cutover is normal: wave 0 can be canonical while
        # wave 1 has not moved. Per-store granularity is what makes that safe.
        return AuthorityMode.MIGRATION_VALIDATION
    return AuthorityMode.CANONICAL


def _override_value(override_env: str | None) -> str:
    if not override_env:
        return ""
    return (os.environ.get(override_env) or "").strip()


def _same_path(a: Path, b: Path) -> bool:
    try:
        return a.expanduser().resolve() == b.expanduser().resolve()
    except Exception:
        return False


def resolve_store_authority(
    *,
    store_id: str,
    legacy_path: Path | str,
    target_segments: tuple[str, ...],
    override_env: str | None = None,
) -> StoreAuthority:
    """Decide the active authority for one store, at operation time.

    `legacy_path` is the store's current in-checkout path (relative paths stay
    relative, exactly as the module resolves them today, so LEGACY mode is
    byte-for-byte the present behaviour).
    """
    legacy = Path(legacy_path)
    override_raw = _override_value(override_env)
    mode = authority_mode(store_id)

    canonical: Path | None = None
    if mode is not AuthorityMode.LEGACY:
        # Only resolved once a root exists: calling this in LEGACY mode would
        # invent a development root and, in production, raise for a store that
        # is not being migrated yet.
        canonical = rd.store_path(*target_segments)

    if mode is AuthorityMode.CANONICAL:
        assert canonical is not None  # mode implies a configured root
        if override_raw and not _same_path(Path(override_raw), canonical):
            raise rd.RuntimeDataError(
                f"{store_id}: {override_env} points outside the canonical runtime "
                "authority after cutover. Refusing to read or write a store whose "
                "authoritative copy has already moved. Unset the override or point "
                "it at the canonical target."
            )
        return StoreAuthority(
            store_id=store_id,
            mode=mode,
            active_path=canonical,
            canonical_path=canonical,
            source=AuthoritySource.CANONICAL_TARGET,
        )

    if override_raw:
        return StoreAuthority(
            store_id=store_id,
            mode=mode,
            active_path=Path(override_raw).expanduser(),
            canonical_path=canonical,
            source=AuthoritySource.EXPLICIT_OVERRIDE,
        )

    return StoreAuthority(
        store_id=store_id,
        mode=mode,
        active_path=legacy,
        canonical_path=canonical,
        source=AuthoritySource.LEGACY_DEFAULT,
    )


def resolve_store_path(**kwargs: object) -> Path:
    """The active path only — for call sites that genuinely need nothing else."""
    return resolve_store_authority(**kwargs).active_path  # type: ignore[arg-type]


def resolve_lock_path(**kwargs: object) -> Path:
    """Lock beside the ACTIVE target.

    A lock that lives next to the legacy file while the data lives externally
    coordinates nothing — five containers would each take a private lock and
    all write at once.
    """
    active = resolve_store_authority(**kwargs).active_path  # type: ignore[arg-type]
    return active.with_suffix(active.suffix + ".lock")


def resolve_temp_path(*, suffix: str = ".tmp", **kwargs: object) -> Path:
    """Atomic-write companion beside the ACTIVE target.

    `os.replace` is only atomic within one filesystem, so the temp file must
    never be resolved against a different root than its destination.
    """
    active = resolve_store_authority(**kwargs).active_path  # type: ignore[arg-type]
    return active.with_name(active.name + suffix)


def describe_store(**kwargs: object) -> dict[str, object]:
    """Non-secret diagnostic view: paths, modes and sources only."""
    try:
        a = resolve_store_authority(**kwargs)  # type: ignore[arg-type]
        return {
            "store_id": a.store_id,
            "mode": a.mode.value,
            "source": a.source.value,
            "active_path": str(a.active_path),
            "canonical_path": str(a.canonical_path) if a.canonical_path else None,
        }
    except rd.RuntimeDataError as e:
        return {"store_id": kwargs.get("store_id"), "error": str(e)}


__all__ = [
    "CUTOVER_GATE_ENV",
    "AuthorityMode",
    "AuthoritySource",
    "StoreAuthority",
    "authority_mode",
    "resolve_store_authority",
    "resolve_store_path",
    "resolve_lock_path",
    "resolve_temp_path",
    "describe_store",
]
