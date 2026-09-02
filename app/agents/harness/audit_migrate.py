"""Guarded historical-migration CLI for the durable harness audit backend.

    python -m app.agents.harness.audit_migrate            # dry-run (default, ZERO writes)
    python -m app.agents.harness.audit_migrate --apply \
        --approval-token <token> \
        --expected-source-checksum <sha256> \
        --source-app-version <40-char-sha> \
        [--source data/harness_runs.jsonl]

Imports the historical JSONL audit records into the durable Redis backend EXACTLY
ONCE, using the events' ORIGINAL provenance (``--source-app-version``) so their
identities are not re-derived under the migrating process's runtime SHA.

Guarantees / guards:
* dry-run is the default and makes ZERO writes;
* --apply refuses unless approval-token + expected-source-checksum + source-app-
  version are all present and the source file matches (checksum, row count,
  family breakdown);
* an idempotency marker (from source checksum + source app version + target schema
  + namespace) makes re-apply a no-op; a different checksum under the same marker
  is refused;
* the source JSONL is never modified, renamed, truncated, or appended to;
* it NEVER changes .env, restarts containers, sets HARNESS_AUDIT_BACKEND, or
  enables any harness flag. Migration and activation are separate owner ops.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import Any, Optional

from app.agents.harness import audit_backend as ab

_TARGET_SCHEMA = "audit-record-v1"
_EXPECTED_FAMILY = {"dag_engine": 1, "batch_harness": 1}
_EXPECTED_ENFORCEMENT = 0


def _read_source(path: str) -> tuple[bytes, list[dict[str, Any]]]:
    with open(path, "rb") as f:
        raw = f.read()
    rows = []
    for line in raw.decode("utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return raw, rows


def _family(row: dict[str, Any]) -> str:
    return str((row.get("extra") or {}).get("source_loop") or row.get("kind") or "unknown")


def _family_breakdown(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        if r.get("kind") == "shadow":
            out[_family(r)] = out.get(_family(r), 0) + 1
    return out


def _migration_identity(source_checksum: str, source_app_version: str) -> str:
    basis = "|".join([source_checksum, source_app_version, _TARGET_SCHEMA, ab._RECORD_PREFIX])
    return hashlib.sha256(basis.encode()).hexdigest()[:32]


def preview(
    source: str, source_app_version: str | None, backend: ab.AuditBackend | None = None
) -> dict[str, Any]:
    raw, rows = _read_source(source)
    checksum = hashlib.sha256(raw).hexdigest()
    fam = _family_breakdown(rows)
    enf = sum(1 for r in rows if r.get("kind") == "enforce")
    keys: list[str] = []
    if source_app_version:
        keys = [ab.derive_dedup_key(r, source_app_version=source_app_version) for r in rows]
    would_create = already = conflict = None
    if backend is not None and source_app_version and hasattr(backend, "_r"):
        would_create = already = conflict = 0
        for r, dk in zip(rows, keys):
            try:
                existing = backend._r.get(ab._RECORD_PREFIX + dk)  # read-only
            except Exception:
                existing = None
            if existing is None:
                would_create += 1
            else:
                already += 1
    return {
        "source": source,
        "source_checksum": checksum,
        "source_count": len(rows),
        "source_family_breakdown": fam,
        "source_enforcement": enf,
        "source_app_version": source_app_version,
        "target_namespace": ab._RECORD_PREFIX,
        "target_schema": _TARGET_SCHEMA,
        "derived_record_keys": keys,  # hashes only
        "would_create": would_create,
        "already_existing": already,
        "conflict": conflict,
        "backend_config": ab.resolve_backend_config(),
    }


def _validate_source(pv: dict[str, Any], expected_checksum: str) -> list[str]:
    errs = []
    if pv["source_checksum"] != expected_checksum:
        errs.append(f"checksum mismatch: got {pv['source_checksum']} expected {expected_checksum}")
    if pv["source_count"] != sum(_EXPECTED_FAMILY.values()):
        errs.append(f"row count {pv['source_count']} != {sum(_EXPECTED_FAMILY.values())}")
    if pv["source_family_breakdown"] != _EXPECTED_FAMILY:
        errs.append(f"family breakdown {pv['source_family_breakdown']} != {_EXPECTED_FAMILY}")
    if pv["source_enforcement"] != _EXPECTED_ENFORCEMENT:
        errs.append(f"enforcement rows {pv['source_enforcement']} != {_EXPECTED_ENFORCEMENT}")
    return errs


def apply(
    source: str,
    approval_token: str,
    expected_checksum: str,
    source_app_version: str,
    backend: ab.AuditBackend | None = None,
) -> dict[str, Any]:
    if not approval_token:
        raise SystemExit("refused: --approval-token required for --apply")
    if not expected_checksum:
        raise SystemExit("refused: --expected-source-checksum required for --apply")
    if not source_app_version or len(source_app_version) != 40:
        raise SystemExit("refused: --source-app-version must be a 40-char SHA")
    be = backend if backend is not None else ab.get_backend()
    if not isinstance(be, ab.RedisBackend):
        raise SystemExit(f"refused: durable redis backend required, resolved '{be.name}'")
    pv = preview(source, source_app_version, backend=be)
    errs = _validate_source(pv, expected_checksum)
    if errs:
        raise SystemExit("refused: source validation failed: " + "; ".join(errs))
    mig_id = _migration_identity(pv["source_checksum"], source_app_version)
    marker_key = ab._MIGRATION_PREFIX + mig_id
    marker_val = json.dumps(
        {
            "source_checksum": pv["source_checksum"],
            "source_app_version": source_app_version,
            "count": pv["source_count"],
        }
    )
    # Idempotency: same identity + different checksum -> refuse; same -> no-op re-apply.
    try:
        prev = be._r.get(marker_key)
    except Exception as e:
        raise SystemExit(f"refused: cannot read migration marker: {e}")
    if prev is not None:
        try:
            prevd = json.loads(ab._to_str(prev))
        except Exception:
            prevd = {}
        if prevd.get("source_checksum") != pv["source_checksum"]:
            raise SystemExit("refused: migration identity exists with a DIFFERENT source checksum")
    _raw, rows = _read_source(source)
    created = existing = 0
    for r in rows:
        dk = ab.derive_dedup_key(r, source_app_version=source_app_version)
        res = be.record(r, dk, source_app_version=source_app_version)
        if res.get("written"):
            created += 1
        elif res.get("duplicate"):
            existing += 1
    try:
        be._r.set(marker_key, marker_val, px=ab.audit_retention_s() * 1000)
    except Exception:
        pass
    return {
        "applied": True,
        "migration_id": mig_id,
        "records_created": created,
        "already_existing": existing,
        "total": len(rows),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="audit_migrate", description="Guarded harness-audit historical migration"
    )
    p.add_argument("--source", default="data/harness_runs.jsonl")
    p.add_argument("--apply", action="store_true", help="perform writes (default: dry-run)")
    p.add_argument("--approval-token", default="")
    p.add_argument("--expected-source-checksum", default="")
    p.add_argument("--source-app-version", default="")
    args = p.parse_args(argv)

    if not args.apply:
        pv = preview(
            args.source,
            args.source_app_version or None,
            backend=(ab.get_backend() if ab.backend_name() == "redis" else None),
        )
        pv["mode"] = "dry-run"
        pv["writes"] = 0
        print(json.dumps(pv, indent=2, default=str))
        return 0
    result = apply(
        args.source, args.approval_token, args.expected_source_checksum, args.source_app_version
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
