"""
Consent + Opt-out Ledger (TCCCPR/TRAI + DPDP Act 2023) — single source of truth.
================================================================================

Kya karta hai (free-stack, jsonl, never-raise):
  * CONSENT ledger    — timestamped consent records (source/scope/proof/client_id),
                        append-only `data/consent_ledger.jsonl` (DPDP audit trail +
                        "access right" ke liye `ledger_for(phone)`).
  * OPT-OUT           — `record_opt_out()` → instant suppression (`data/voice_suppression.jsonl`)
                        + cross-channel propagate (WA suppression list bhi) — TCCCPR ka
                        4-ghante propagation requirement INSTANT me beat hota hai.
  * SUPPRESSION check — `is_suppressed(phone)` (last-10-digit match). ComplianceGate
                        promotional calls ke liye ise enforce karta hai (wired).
  * RETENTION sweep   — `retention_sweep()` — `data/recordings/` me
                        RECORDING_RETENTION_DAYS (default 90) se purani files report;
                        DELETE sirf `RECORDING_RETENTION=1` flag pe (default = dry-run
                        report only, zero behaviour change).

Design: import-safe, koi function kabhi raise nahi karta. Stores chhote jsonl
(in-memory read per check — call volume low, fine). Empty store = zero change.
"""

from __future__ import annotations

import json
import os
import time as _time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# --------------------------------------------------------------------------- #
# Postgres-backed path (CONSENT_DB=1) — concurrent-safe for multi-worker Celery
# --------------------------------------------------------------------------- #
_CONSENT_DB = os.environ.get("CONSENT_DB", "").strip() in ("1", "true", "yes")

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS consent_records (
    id SERIAL PRIMARY KEY,
    phone_key VARCHAR(10) NOT NULL,
    record_type VARCHAR(20) NOT NULL,
    scope VARCHAR(40),
    source VARCHAR(80),
    proof VARCHAR(160),
    client_id VARCHAR(60),
    channel VARCHAR(20),
    reason VARCHAR(60),
    call_id VARCHAR(60),
    at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_consent_records_phone ON consent_records(phone_key);
CREATE INDEX IF NOT EXISTS ix_consent_records_phone_type ON consent_records(phone_key, record_type);

CREATE TABLE IF NOT EXISTS opt_out_suppression (
    id SERIAL PRIMARY KEY,
    phone_key VARCHAR(10) NOT NULL UNIQUE,
    reason VARCHAR(60),
    channel VARCHAR(20),
    at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_opt_out_suppression_phone ON opt_out_suppression(phone_key);
"""

_DB_READY = False


def _ensure_db_tables() -> bool:
    """One-time table create (idempotent). Returns True if DB available."""
    global _DB_READY
    if _DB_READY:
        return True
    try:
        import psycopg2  # sync driver — init only, no async overhead

        from app.config import settings

        dsn = getattr(settings, "database_url", "") or os.environ.get("DATABASE_URL", "")
        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://").replace(
            "postgresql+psycopg2://", "postgresql://"
        )
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(_CREATE_SQL)
        conn.close()
        _DB_READY = True
        return True
    except Exception as e:
        logger.debug(f"[consent_ledger] DB init skip: {e}")
        return False


def _db_is_suppressed(phone_key: str) -> bool | None:
    """DB suppression check. Returns None if DB unavailable (fall through to JSONL)."""
    if not _CONSENT_DB or not _ensure_db_tables():
        return None
    try:
        import psycopg2

        from app.config import settings

        dsn = getattr(settings, "database_url", "") or os.environ.get("DATABASE_URL", "")
        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://").replace(
            "postgresql+psycopg2://", "postgresql://"
        )
        conn = psycopg2.connect(dsn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM opt_out_suppression WHERE phone_key=%s LIMIT 1", (phone_key,)
            )
            found = cur.fetchone() is not None
        conn.close()
        return found
    except Exception as e:
        logger.debug(f"[consent_ledger] db_is_suppressed error: {e}")
        return None


def _db_add_suppression(phone_key: str, reason: str, channel: str) -> bool:
    """Upsert suppression row. Returns True on success."""
    if not _CONSENT_DB or not _ensure_db_tables():
        return False
    try:
        import psycopg2

        from app.config import settings

        dsn = getattr(settings, "database_url", "") or os.environ.get("DATABASE_URL", "")
        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://").replace(
            "postgresql+psycopg2://", "postgresql://"
        )
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO opt_out_suppression (phone_key, reason, channel)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (phone_key) DO UPDATE
                   SET reason=EXCLUDED.reason, channel=EXCLUDED.channel, at=NOW()""",
                (phone_key, reason[:60], channel[:20]),
            )
        conn.close()
        return True
    except Exception as e:
        logger.error(f"[consent_ledger] db_add_suppression failed: {e}")
        return False


def _db_remove_suppression(phone_key: str) -> bool:
    """Remove suppression row. Returns True on success."""
    if not _CONSENT_DB or not _ensure_db_tables():
        return False
    try:
        import psycopg2

        from app.config import settings

        dsn = getattr(settings, "database_url", "") or os.environ.get("DATABASE_URL", "")
        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://").replace(
            "postgresql+psycopg2://", "postgresql://"
        )
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("DELETE FROM opt_out_suppression WHERE phone_key=%s", (phone_key,))
        conn.close()
        return True
    except Exception as e:
        logger.debug(f"[consent_ledger] db_remove_suppression error: {e}")
        return False


# Stores (tests monkeypatch these module attrs)
def ledger_path() -> Path:
    """Consent ledger — resolved per call, never captured at import.

    DPDP audit trail. A module-level constant froze this path when the module
    was first imported, which is what makes a store impossible to move and
    impossible to redirect from a fixture that runs later.
    """
    from app.platform import runtime_data_authority as _auth

    return _auth.resolve_store_path(
        store_id="compliance.consent_ledger",
        legacy_path=Path("data") / "consent_ledger.jsonl",
        target_segments=("compliance", "consent_ledger.jsonl"),
    )


def suppression_path() -> Path:
    """Voice suppression list — a SEPARATE store from the consent ledger.

    They share this module, not an identity: an opt-out must be able to move,
    be verified and be rolled back independently of the audit trail that
    explains it.
    """
    from app.platform import runtime_data_authority as _auth

    return _auth.resolve_store_path(
        store_id="compliance.voice_suppression",
        legacy_path=Path("data") / "voice_suppression.jsonl",
        target_segments=("compliance", "voice_suppression.jsonl"),
    )


def _suppression_path_or_none() -> Path | None:
    """The resolved suppression path, or None if the authority cannot be resolved.

    Before the runtime-data migration this could not fail: the path was a module
    constant, so the only errors were I/O errors on a file that legitimately may
    not exist yet. `resolve_store_path` introduces a genuinely new failure mode —
    a misconfigured runtime root, an unsafe segment, a path escaping the root, or
    (after cutover) an override pointing somewhere other than the canonical
    target all raise `RuntimeDataError`.

    Callers must therefore distinguish "this number is not on the list" from
    "there is no list I am allowed to trust", because the blanket
    `except Exception: return False` that was safe around a constant would turn
    the second case into the first — answering "not suppressed" for a number
    that may well be. That is TCCCPR fail-OPEN, and this module's own comments
    call it illegal.
    """
    try:
        return suppression_path()
    except Exception as exc:  # noqa: BLE001 — any resolution failure is the same verdict
        logger.error("compliance.voice_suppression authority UNRESOLVABLE: %s", exc)
        return None


def __getattr__(name: str) -> Path:
    """DEPRECATED transitional shim for the old module constants.

    `from consent_ledger import LEDGER_FILE` calls this ONCE and freezes the
    result in the importing module, so this shim cannot deliver operation-time
    resolution to that form. It exists only so an unnoticed external consumer
    fails loudly-late rather than silently, and a test asserts that no code in
    this repository imports these names. Call `ledger_path()` /
    `suppression_path()` instead.

    It logs at ERROR as well as warning. `pyproject.toml` sets
    `filterwarnings = ["ignore::DeprecationWarning", ...]`, so under the test
    suite the warning alone is swallowed — a tripwire nobody can hear is not a
    tripwire, and this store decides whether a person may be contacted.
    """
    import warnings

    if name in ("LEDGER_FILE", "SUPPRESSION_FILE"):
        message = (
            f"consent_ledger.{name} is deprecated and does NOT track later "
            "environment changes; call ledger_path()/suppression_path() instead."
        )
        warnings.warn(message, DeprecationWarning, stacklevel=2)
        logger.error("FROZEN COMPLIANCE PATH: %s", message)
        return ledger_path() if name == "LEDGER_FILE" else suppression_path()
    if name == "RECORDINGS_DIR":
        message = (
            "consent_ledger.RECORDINGS_DIR is deprecated and does NOT track later "
            "environment changes; call recordings_dir() instead."
        )
        warnings.warn(message, DeprecationWarning, stacklevel=2)
        logger.error("FROZEN COMPLIANCE PATH: %s", message)
        return recordings_dir()
    raise AttributeError(name)


def recordings_dir() -> Path:
    """Retention-governed telephony recordings — resolved per call, never frozen at import.

    Same store as ``voice_launch._recordings_dir`` (telephony.call_recordings /
    RECORDINGS_DIR). Import-time Path constants cannot follow a cutover.
    """
    from app.platform.runtime_recording_paths import telephony_recordings_dir

    return telephony_recordings_dir()


DEFAULT_RETENTION_DAYS = 90  # TRAI/QoS guidance: call recordings 90 din, fir delete

# Re-consent cool-off (TRAI/TCCCPR): once a subscriber opts out, a fresh
# consent / opt-back-in must NOT be honoured for a floor period — this guards
# against a number being scrubbed and immediately re-added (which would defeat
# the opt-out). 90 days mirrors the recording-retention floor. Override window
# via env RECONSENT_COOLOFF_DAYS; admin can still force a re-consent with proof.
DEFAULT_RECONSENT_COOLOFF_DAYS = 90


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _digits(phone: str) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit())


def _key(phone: str) -> str:
    """Compare on last 10 digits (ignore +91/91 prefixes)."""
    d = _digits(phone)
    return d[-10:] if len(d) >= 10 else d


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path) -> list[dict]:
    try:
        if not path.exists():
            return []
        out: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out
    except Exception:
        return []


def _append(path: Path, item: dict) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        # A failed SUPPRESSION write is a compliance event, not a debug note.
        logger.error(f"consent_ledger: append failed ({e})")
        return False


def _write_all(path: Path, items: list[dict]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"consent_ledger: write failed ({e})")


# --------------------------------------------------------------------------- #
# Consent records (DPDP: timestamped, source + proof, queryable per phone)
# --------------------------------------------------------------------------- #
def record_consent(
    phone: str,
    scope: str = "voice_promo",
    source: str = "",
    proof: str = "",
    client_id: str = "",
) -> dict[str, Any]:
    """Timestamped consent record. source = inquiry_form/signup/wa_optin/verbal etc.;
    proof = form-id / message-id / recording ref. Never raises."""
    k = _key(phone)
    if not k:
        return {"error": "bad_phone"}
    rec = {
        "type": "consent",
        "phone": k,
        "scope": (scope or "voice_promo")[:40],
        "source": (source or "")[:80],
        "proof": (proof or "")[:160],
        "client_id": (client_id or "")[:60],
        "at": _now(),
    }
    _append(ledger_path(), rec)
    return rec


def has_consent(phone: str, scope: str = "voice_promo", max_age_days: int | None = None) -> bool:
    """True agar phone ke liye scope-consent on record hai (aur opt-out ne revoke
    nahi kiya). max_age_days set ho to itne din se purana consent invalid
    (digital consent ki validity windows ke liye)."""
    try:
        k = _key(phone)
        if not k or is_suppressed(k):
            return False
        latest: str | None = None
        for it in _read(ledger_path()):
            if it.get("phone") == k and it.get("type") == "consent":
                if it.get("scope") in (scope, "all"):
                    at = str(it.get("at") or "")
                    if latest is None or at > latest:
                        latest = at
        if latest is None:
            return False
        if max_age_days is not None:
            try:
                ts = datetime.fromisoformat(latest)
                age_days = (datetime.now(timezone.utc) - ts).total_seconds() / 86400.0
                if age_days > max_age_days:
                    return False
            except Exception:
                return False
        return True
    except Exception:
        return False


def ledger_for(phone: str, limit: int = 100) -> list[dict]:
    """DPDP access right: phone ka poora consent/opt-out history (newest first)."""
    try:
        k = _key(phone)
        if not k:
            return []
        items = [it for it in _read(ledger_path()) if it.get("phone") == k]
        return items[-limit:][::-1]
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# Opt-out → suppression (instant, cross-channel)
# --------------------------------------------------------------------------- #
def record_opt_out(
    phone: str, reason: str = "user_request", channel: str = "voice", call_id: str = ""
) -> dict[str, Any]:
    """Opt-out: ledger entry + voice suppression + WA suppression (cross-channel,
    best-effort). Idempotent. Never raises."""
    k = _key(phone)
    if not k:
        return {"error": "bad_phone"}
    rec = {
        "type": "opt_out",
        "phone": k,
        "reason": (reason or "user_request")[:60],
        "channel": (channel or "voice")[:20],
        "call_id": (call_id or "")[:60],
        "at": _now(),
    }
    try:
        _append(ledger_path(), rec)
    except Exception as exc:  # noqa: BLE001 — the audit write must not abort the opt-out
        logger.error(f"opt-out LEDGER write failed for ***{k[-4:]}: {exc}")

    # Guard, then resolve at each call site. Binding the path to a local and
    # reusing it would be better for one property (a cutover landing between the
    # read and the write cannot then split the operation across two authorities)
    # and worse for another: `runtime_data_scan` attributes a finding to the
    # expression it sees, so `_append(local_var, ...)` reports a bare name where
    # `_append(suppression_path(), ...)` reports the resolver, and this store
    # loses its identity in the repo's own debt ledger. The split-brain needs a
    # live cutover to happen at all, and the preflight still says DENIED, so the
    # cheap half is taken now and the rest is deferred to a change that teaches
    # the scanner to follow a locally-bound resolver result first.
    suppressed = True
    if _suppression_path_or_none() is None:
        # Cannot even name the store: do not claim a suppression that has no
        # home. Same fail-CLOSED contract as a failed write, below.
        logger.error(f"opt-out suppression UNRESOLVABLE for ***{k[-4:]} — NOT suppressed")
        suppressed = False
    elif not is_suppressed(k):
        # Dual-write: DB (concurrent-safe) + JSONL (audit trail)
        db_ok = _db_add_suppression(k, rec["reason"], rec["channel"])
        jsonl_ok = _append(
            suppression_path(),
            {"phone": k, "reason": rec["reason"], "channel": rec["channel"], "at": rec["at"]},
        )
        ok = db_ok or jsonl_ok  # either path sufficient
        if not ok:
            # Fail-CLOSED: agar suppression persist NAHI hua to "suppressed"
            # claim mat karo — TCCCPR fail-open = illegal.
            logger.error(f"opt-out suppression WRITE FAILED for ***{k[-4:]} — NOT suppressed")
            suppressed = False
    # Cross-channel propagate (TCCCPR: revocation sab commercial comms pe lagti hai).
    try:
        from app.marketing import wa_campaign_runner

        wa_campaign_runner.suppress(k, reason=f"{channel}_opt_out")
    except Exception:
        pass
    # F.4 bridge — DPDP "right to be forgotten": purge any stored agent memory
    # for this phone too. Fire-and-forget; never blocks the opt-out write. The
    # voice agent stores cross-session lead facts in Qdrant (agent_memory.py);
    # without this hook, opting out of CALLS would still leave personal
    # utterances in memory — a DPDP s.12 violation.
    try:
        import asyncio as _asyncio

        from app.voice_agent import agent_memory as _agm

        try:
            _loop = _asyncio.get_running_loop()
            _loop.create_task(_agm.purge_subject(k, scope="lead"))
        except RuntimeError:
            # No running loop (sync/CLI path) — schedule synchronously via run().
            # Wrapped so a missing dep / disabled flag still never breaks opt-out.
            try:
                _asyncio.run(_agm.purge_subject(k, scope="lead"))
            except Exception:
                pass
    except Exception:
        pass
    logger.info(f"🔕 opt-out recorded ***{k[-4:]} ({channel}/{rec['reason']})")
    return {"phone": k, "suppressed": suppressed, **rec}


def is_suppressed(phone: str) -> bool:
    """True agar number opt-out suppression list par hai. Never raises.
    CONSENT_DB=1 pe Postgres check (concurrent-safe); warna JSONL fallback.

    Returns True when the suppression authority cannot be RESOLVED. "I cannot
    reach the opt-out list" must never be answered as "this person did not opt
    out" — the caller is about to decide whether to contact somebody, and the
    only safe answer without the list is "do not". A missing or empty file is
    different and still reads as not-suppressed: that is an answer, not an
    outage.
    """
    try:
        k = _key(phone)
        if not k:
            return False
        # Read must honor the SAME or-contract as the write (record_opt_out persists if
        # db_ok OR jsonl_ok). So: DB says suppressed -> True; DB says NOT suppressed (or
        # DB unavailable) -> still consult JSONL, else a JSONL-only suppression (DB write
        # failed, or rows written before CONSENT_DB was enabled) reads as callable =
        # TCCCPR fail-OPEN. Fail-CLOSED: suppressed if EITHER store says so.
        db_result = _db_is_suppressed(k)
        if db_result:
            return True
        if _suppression_path_or_none() is None:
            return True  # fail-CLOSED: no trustworthy list => treat as suppressed
        return any(it.get("phone") == k for it in _read(suppression_path()))
    except Exception:
        return False


def _cooloff_days() -> int:
    """Re-consent cool-off window (days). Env-overridable, never raises."""
    try:
        v = (os.environ.get("RECONSENT_COOLOFF_DAYS", "") or "").strip()
        if v:
            n = int(v)
            if n >= 0:
                return n
    except Exception:
        pass
    return DEFAULT_RECONSENT_COOLOFF_DAYS


def last_opt_out_at(phone: str) -> str | None:
    """ISO timestamp of the most-recent opt_out for this number (last-10 match),
    or None. Reads both the suppression store (current opt-out) and the ledger
    opt_out entries (history), returning the latest. Never raises."""
    try:
        k = _key(phone)
        if not k:
            return None
        latest: str | None = None
        for it in _read(suppression_path()):
            if it.get("phone") == k:
                at = str(it.get("at") or "")
                if at and (latest is None or at > latest):
                    latest = at
        for it in _read(ledger_path()):
            if it.get("phone") == k and it.get("type") == "opt_out":
                at = str(it.get("at") or "")
                if at and (latest is None or at > latest):
                    latest = at
        return latest
    except Exception:
        return None


def days_since_opt_out(phone: str) -> float | None:
    """Days elapsed since the last opt_out, or None if never opted out / unknown.
    Never raises."""
    try:
        latest = last_opt_out_at(phone)
        if not latest:
            return None
        ts = datetime.fromisoformat(latest)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds() / 86400.0
    except Exception:
        return None


def blocked_until(phone: str, cooloff_days: int | None = None) -> str | None:
    """ISO timestamp until which a re-consent is blocked (last opt_out + cool-off),
    or None if there is no opt_out on record. Returns the timestamp even if it is
    already in the past (caller compares to now). Never raises."""
    try:
        latest = last_opt_out_at(phone)
        if not latest:
            return None
        days = _cooloff_days() if cooloff_days is None else max(0, int(cooloff_days))
        ts = datetime.fromisoformat(latest)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (ts + timedelta(days=days)).isoformat()
    except Exception:
        return None


def reconsent_blocked(phone: str, cooloff_days: int | None = None) -> bool:
    """True agar number ne haal hi me (cool-off window ke andar) opt-out kiya hai
    — re-consent abhi honour NAHI hona chahiye (TRAI 90-din floor). Never raises."""
    try:
        days = _cooloff_days() if cooloff_days is None else max(0, int(cooloff_days))
        if days <= 0:
            return False
        elapsed = days_since_opt_out(phone)
        if elapsed is None:
            return False
        return elapsed < days
    except Exception:
        return False


def opt_back_in(
    phone: str,
    source: str = "admin",
    proof: str = "",
    force: bool = False,
    cooloff_days: int | None = None,
) -> dict[str, Any]:
    """Re-consent: suppression se hatao + fresh consent record (admin/explicit only).

    TRAI 90-din re-consent cool-off: agar number ne cool-off window ke andar
    opt-out kiya hai to re-consent REJECT hota hai (number callable nahi banta)
    unless ``force=True`` (admin override, audit-logged). Additive — purane
    callers (force default False) ke liye ab cool-off enforce hota hai, jo gate
    ko STRENGTHEN karta hai (number ko turant re-add karke opt-out defeat nahi
    kar sakte)."""
    k = _key(phone)
    if not k:
        return {"error": "bad_phone"}
    # 90-din floor — recent opt-out ko turant reverse mat hone do.
    if not force and reconsent_blocked(k, cooloff_days=cooloff_days):
        until = blocked_until(k, cooloff_days=cooloff_days)
        elapsed = days_since_opt_out(k)
        logger.warning(
            f"🚫 re-consent BLOCKED ***{k[-4:]} — within cool-off "
            f"({elapsed:.1f}d since opt-out, blocked_until={until}). "
            f"Use force=True to override."
        )
        return {
            "phone": k,
            "suppressed": True,
            "reconsent_blocked": True,
            "blocked_until": until,
            "days_since_opt_out": elapsed,
            "cooloff_days": _cooloff_days() if cooloff_days is None else cooloff_days,
            "error": "reconsent_cooloff",
        }
    # Guard first — see record_opt_out for why the resolver is still called at
    # each site rather than bound to a local.
    if _suppression_path_or_none() is None:
        # Refuse. Removing somebody from a suppression list is the one direction
        # that makes a number contactable again; doing it while unable to name
        # the list is how an opt-out silently stops being honoured.
        logger.error(f"re-consent REFUSED ***{k[-4:]} — suppression authority unresolvable")
        return {
            "phone": k,
            "suppressed": True,
            "error": "suppression_authority_unavailable",
        }
    # Remove from DB (concurrent-safe) + JSONL
    _db_remove_suppression(k)
    items = _read(suppression_path())
    keep = [i for i in items if i.get("phone") != k]
    if len(keep) != len(items):
        _write_all(suppression_path(), keep)
    rec = record_consent(k, scope="all", source=source, proof=proof)
    if force and reconsent_blocked(k, cooloff_days=cooloff_days):
        # Override is a compliance event — leave an audit breadcrumb in the ledger.
        try:
            _append(
                ledger_path(),
                {
                    "type": "reconsent_override",
                    "phone": k,
                    "source": (source or "admin")[:80],
                    "proof": (proof or "")[:160],
                    "at": _now(),
                },
            )
        except Exception:
            pass
    return {"phone": k, "suppressed": False, "reconsent_blocked": False, "consent": rec}


def suppression_list(limit: int = 500) -> list[dict]:
    try:
        return _read(suppression_path())[-limit:][::-1]
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# Recording retention (90-din default; delete gated RECORDING_RETENTION=1)
# --------------------------------------------------------------------------- #
def retention_sweep(days: int | None = None) -> dict[str, Any]:
    """`data/recordings/` me retention se purani files: report (hamesha) +
    delete (sirf RECORDING_RETENTION=1). Dir na ho = no-op. Never raises."""
    try:
        if days is None:
            try:
                days = int(os.environ.get("RECORDING_RETENTION_DAYS", "") or DEFAULT_RETENTION_DAYS)
            except Exception:
                days = DEFAULT_RETENTION_DAYS
        delete_on = (os.environ.get("RECORDING_RETENTION", "") or "").strip() in (
            "1",
            "true",
            "yes",
            "on",
        )
        result: dict[str, Any] = {
            "days": days,
            "delete_enabled": delete_on,
            "expired": 0,
            "deleted": 0,
            "errors": 0,
        }
        root = recordings_dir()
        if not root.exists():
            return result
        cutoff = _time.time() - days * 86400
        for p in root.rglob("*"):
            try:
                if not p.is_file():
                    continue
                if p.stat().st_mtime < cutoff:
                    result["expired"] += 1
                    if delete_on:
                        p.unlink()
                        result["deleted"] += 1
            except Exception:
                result["errors"] += 1
        if result["deleted"]:
            logger.info(f"🗑️ recording retention: {result['deleted']} files deleted (>{days}d old)")
        return result
    except Exception as e:
        return {"error": str(e)[:120]}


__all__ = [
    "record_consent",
    "has_consent",
    "ledger_for",
    "record_opt_out",
    "is_suppressed",
    "opt_back_in",
    "last_opt_out_at",
    "days_since_opt_out",
    "blocked_until",
    "reconsent_blocked",
    "suppression_list",
    "retention_sweep",
    "ledger_path",
    "suppression_path",
    "recordings_dir",
]
