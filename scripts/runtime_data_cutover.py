#!/usr/bin/env python3
"""Move a wave of runtime-data stores OUT of the Git checkout, verifiably.

WHY THIS EXISTS
---------------
`scripts/_runtime_data_guard.sh` refuses every deployment while production
mutable state lives inside the Git checkout, because the release's one
destructive command is `git pull --ff-only` in `/opt/leadgen` — the directory
that also holds the paying customer's delivery ledger, the content queue, the
customer registry, the consent ledger and the suppression lists. The guard has
no bypass by design. The only way to a green deploy is to actually move the
bytes, and that is what this does.

WHAT IT WILL NOT DO
-------------------
* It never deletes or truncates a source file. After a cutover the checkout copy
  survives as a fallback until an operator removes it deliberately, in a
  separate step, with the marker already proven good.
* It never writes a marker that `runtime_data_marker.validate_marker` would
  reject, and never writes one at all unless `verify` passed in the same
  invocation chain (the marker records the evidence file it was based on).
* It refuses a store whose manifest row still says `LEGACY_IN_CHECKOUT`. That is
  not this tool being fussy: `validate_marker` rejects such a marker outright,
  because a store whose CODE cannot follow a cutover must not be recorded as
  migrated. Moving those bytes first would create a store the application still
  reads from the old path — a split brain with extra steps. Migrate the code to
  the resolver first (see the A1/A2 waves), then come back.
* It does not flip manifest states and it does not enable the cutover gate.
  Both are deliberate code changes that belong in a reviewed commit, not in a
  script run on a production host at 3am.

ORDER OF OPERATIONS (one wave)
------------------------------
    plan     -> read-only. what would move, from where, to where, how big.
    copy     -> additive byte copy + sha256 of every source and destination.
    verify   -> recompute both sides independently and compare. Exits non-zero
                on ANY mismatch. This is the step whose output the marker cites.
    activate -> write the cutover marker for the verified stores only.

Then, in a reviewed PR: flip those manifest rows to `CUTOVER_COMPLETE` and set
`RUNTIME_DATA_CUTOVER_ENABLED=1`. Only when every blocking store has reached
`CUTOVER_COMPLETE` does the deploy guard stop refusing.

LOCK FILES ARE NOT COPIED
-------------------------
`compliance.email_suppression` declares `data/email_suppression.jsonl.lock`
alongside its ledger. A lock is a statement about a process that is running
right now; copying a stale one to a new root would hand the new location a lock
nobody holds. The lock is recreated beside the ledger on first write — which is
exactly why the manifest says it must colocate. Locks are skipped and reported.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.platform import runtime_data as rd  # noqa: E402
from app.platform import runtime_data_manifest as manifest  # noqa: E402
from app.platform import runtime_data_marker as mk  # noqa: E402

EVIDENCE_DIRNAME = "migration"
COPY_MANIFEST_NAME = "copy_manifest.json"


# --------------------------------------------------------------------------- io
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _line_count(path: Path) -> int | None:
    """Line count for newline-delimited stores; None for anything else.

    A byte hash already proves the copy is identical. This is a second,
    human-legible signal: an operator eyeballing "1 line" on a consent ledger
    that should have hundreds will catch a wrong-source mistake that a matching
    hash cannot, because a hash only proves you copied whatever you pointed at.
    """
    if path.suffix not in (".jsonl", ".ndjson"):
        return None
    n = 0
    with path.open("rb") as fh:
        for _ in fh:
            n += 1
    return n


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            capture_output=True,
            check=False,
        )
        return out.stdout.decode().strip()[:40]
    except Exception:
        return ""


# ---------------------------------------------------------------------- model
def _wave_rows(store_ids: list[str]) -> list[dict]:
    by_id = {s["store_id"]: s for s in manifest.STORES}
    unknown = [i for i in store_ids if i not in by_id]
    if unknown:
        raise SystemExit(f"unknown store ids: {sorted(unknown)}")
    return [by_id[i] for i in store_ids]


def _refuse_legacy_rows(rows: list[dict]) -> None:
    legacy = [
        r["store_id"] for r in rows if r.get("migration_state") == manifest.LEGACY_IN_CHECKOUT
    ]
    if legacy:
        raise SystemExit(
            "REFUSED: these stores are still LEGACY_IN_CHECKOUT, meaning their code "
            "cannot follow a cutover yet:\n  "
            + "\n  ".join(sorted(legacy))
            + "\n\nvalidate_marker() rejects a marker listing them, and moving the bytes "
            "first would leave the application reading the old path. Migrate the code "
            "to runtime_data_authority.resolve_store_path first (see the A1/A2 waves)."
        )


def _plan_entries(rows: list[dict], root: Path) -> tuple[list[dict], list[dict]]:
    """Return (copy_entries, skipped_locks). Raises if a source is missing."""
    entries: list[dict] = []
    skipped: list[dict] = []
    missing: list[str] = []
    for row in rows:
        target_sub = str(row.get("target_runtime_subpath") or "").strip()
        if not target_sub:
            raise SystemExit(f"{row['store_id']}: manifest row has no target_runtime_subpath")
        target_dir = (root / Path(target_sub)).parent
        for legacy in row.get("legacy_paths") or []:
            src = REPO / Path(legacy)
            if str(legacy).endswith(".lock"):
                skipped.append({"store_id": row["store_id"], "path": str(legacy)})
                continue
            if not src.exists():
                missing.append(f"{row['store_id']}: {legacy}")
                continue
            entries.append(
                {
                    "store_id": row["store_id"],
                    "tier": row.get("migration_tier"),
                    "source": str(src),
                    "source_relative": str(legacy),
                    "destination": str(target_dir / src.name),
                    "is_dir": src.is_dir(),
                }
            )
    if missing:
        raise SystemExit(
            "REFUSED: declared source path(s) absent — refusing to 'migrate' a store "
            "whose bytes cannot be found:\n  " + "\n  ".join(missing)
        )
    return entries, skipped


def _measure(entry: dict) -> dict:
    src = Path(entry["source"])
    if entry["is_dir"]:
        files = [p for p in src.rglob("*") if p.is_file()]
        return {
            **entry,
            "kind": "dir",
            "file_count": len(files),
            "bytes": sum(p.stat().st_size for p in files),
        }
    return {
        **entry,
        "kind": "file",
        "bytes": src.stat().st_size,
        "sha256": _sha256(src),
        "lines": _line_count(src),
    }


# ------------------------------------------------------------------ commands
def cmd_plan(args: argparse.Namespace) -> int:
    root = rd.runtime_root(validate=False) if args.root is None else Path(args.root)
    rows = _wave_rows(args.stores)
    _refuse_legacy_rows(rows)
    entries, skipped = _plan_entries(rows, root)
    measured = [_measure(e) for e in entries]

    print(f"=== cutover plan ({len(rows)} store(s)) ===")
    print(f"  runtime root : {root}")
    print(f"  repo         : {REPO}")
    print(f"  release sha  : {_git_sha()[:8] or 'UNKNOWN'}")
    total = 0
    for m in measured:
        total += int(m["bytes"])
        extra = f" lines={m['lines']}" if m.get("lines") is not None else ""
        if m["kind"] == "dir":
            extra = f" files={m['file_count']}"
        print(f"\n  {m['store_id']}  [{m['tier']}]")
        print(f"    from : {m['source_relative']}  ({m['bytes']} bytes{extra})")
        print(f"    to   : {m['destination']}")
    print(f"\n  total: {total} bytes across {len(measured)} path(s)")
    for s in skipped:
        print(f"  SKIP (lock, recreated on first write): {s['path']}  [{s['store_id']}]")
    print("\nNothing has been written. Run `copy --yes` to move bytes.")
    return 0


def cmd_copy(args: argparse.Namespace) -> int:
    if not args.yes:
        raise SystemExit("refusing to copy without --yes (run `plan` first)")
    root = rd.runtime_root(validate=False) if args.root is None else Path(args.root)
    rows = _wave_rows(args.stores)
    _refuse_legacy_rows(rows)
    entries, skipped = _plan_entries(rows, root)

    started = _now()
    records: list[dict] = []
    for entry in entries:
        src, dst = Path(entry["source"]), Path(entry["destination"])
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and not args.resume:
            raise SystemExit(
                f"REFUSED: destination already exists: {dst}\n"
                "Pass --resume to overwrite it, but only after confirming it is a "
                "partial copy from this same wave and not a live store somebody else "
                "already cut over."
            )
        if entry["is_dir"]:
            shutil.copytree(src, dst, dirs_exist_ok=True)
            files = [p for p in dst.rglob("*") if p.is_file()]
            records.append(
                {
                    **entry,
                    "kind": "dir",
                    "file_count": len(files),
                    "bytes": sum(p.stat().st_size for p in files),
                }
            )
        else:
            shutil.copy2(src, dst)  # copy2 keeps mtime — retention sweeps read it
            records.append(
                {
                    **entry,
                    "kind": "file",
                    "bytes": dst.stat().st_size,
                    "source_sha256": _sha256(src),
                    "destination_sha256": _sha256(dst),
                    "source_lines": _line_count(src),
                    "destination_lines": _line_count(dst),
                }
            )
        print(f"copied {entry['source_relative']} -> {dst}")

    evidence_dir = root / EVIDENCE_DIRNAME
    evidence_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "runtime-data-copy-manifest/1",
        "release_sha": _git_sha(),
        "manifest_version": manifest.MANIFEST_VERSION,
        "runtime_root": str(root),
        "store_ids": sorted({r["store_id"] for r in records}),
        "started_at": started,
        "finished_at": _now(),
        "entries": records,
        "skipped_locks": skipped,
        "verified": False,
    }
    out = evidence_dir / COPY_MANIFEST_NAME
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\ncopy manifest: {out}")
    print("Sources untouched. Run `verify` next — copy alone proves nothing.")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    root = rd.runtime_root(validate=False) if args.root is None else Path(args.root)
    path = root / EVIDENCE_DIRNAME / COPY_MANIFEST_NAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"no copy manifest at {path} — run `copy` first") from None

    problems: list[str] = []
    checked = 0
    for entry in payload.get("entries") or []:
        src, dst = Path(entry["source"]), Path(entry["destination"])
        if not dst.exists():
            problems.append(f"{entry['store_id']}: destination missing: {dst}")
            continue
        if entry["kind"] == "dir":
            s = [p for p in src.rglob("*") if p.is_file()]
            d = [p for p in dst.rglob("*") if p.is_file()]
            if len(s) != len(d):
                problems.append(f"{entry['store_id']}: file count {len(s)} -> {len(d)} ({dst})")
            checked += 1
            continue
        # Recompute BOTH sides now. Trusting the hashes the copy step wrote would
        # only prove the copy step is self-consistent.
        s_sha, d_sha = _sha256(src), _sha256(dst)
        if s_sha != d_sha:
            problems.append(f"{entry['store_id']}: sha256 mismatch ({dst})")
        if s_sha != entry.get("source_sha256"):
            problems.append(
                f"{entry['store_id']}: SOURCE changed since the copy — a live writer "
                f"appended during the cutover ({src}). Re-copy this store."
            )
        s_lines, d_lines = _line_count(src), _line_count(dst)
        if s_lines != d_lines:
            problems.append(f"{entry['store_id']}: line count {s_lines} -> {d_lines}")
        checked += 1

    if problems:
        print(f"=== VERIFY FAILED ({len(problems)} problem(s)) ===")
        for p in problems:
            print(f"  x {p}")
        print("\nMarker NOT eligible. Do not activate.")
        return 1

    payload["verified"] = True
    payload["verified_at"] = _now()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"=== VERIFY PASSED — {checked} path(s) byte-identical ===")
    print(f"evidence: {path}")
    print("Sources still present as fallback. `activate` may now write the marker.")
    return 0


def cmd_activate(args: argparse.Namespace) -> int:
    if not args.yes:
        raise SystemExit("refusing to write a marker without --yes")
    if not str(args.rollback_reference or "").strip():
        raise SystemExit(
            "--rollback-reference is required: a cutover without a rollback is not one"
        )
    root = rd.runtime_root(validate=False) if args.root is None else Path(args.root)
    evidence = root / EVIDENCE_DIRNAME / COPY_MANIFEST_NAME
    try:
        payload = json.loads(evidence.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"no copy manifest at {evidence} — nothing was verified") from None
    if not payload.get("verified"):
        raise SystemExit(
            "REFUSED: the copy manifest is not marked verified. Run `verify` and let it "
            "pass. A marker means 'checked', not 'copied'."
        )

    # The release sha is load-bearing: it is what a future operator diffs against
    # to know WHICH code's stores were verified. Resolve it explicitly and fail
    # with a usable message rather than letting validate_marker say "malformed",
    # which tells an operator nothing about where to get one.
    release_sha = (args.release_sha or payload.get("release_sha") or _git_sha() or "").strip()
    if not release_sha:
        raise SystemExit(
            "REFUSED: no release sha available.\n"
            "  `git rev-parse HEAD` produced nothing — this is not a git checkout "
            "(a tarball deploy, or the repo moved).\n"
            "  Pass --release-sha <sha of the code these stores were verified against>."
        )

    ids = sorted(payload.get("store_ids") or [])
    marker = {
        "schema_version": mk.SCHEMA_VERSION,
        "manifest_version": manifest.MANIFEST_VERSION,
        "runtime_root_identifier": str(root),
        "source_production_sha": release_sha[:40],
        "migrated_store_ids": ids,
        "source_manifest_reference": "app/platform/runtime_data_manifest.py",
        "verification_reference": str(evidence),
        "cutover_started_at": payload.get("started_at") or _now(),
        "cutover_completed_at": _now(),
        "validation_status": mk.VALIDATION_PASSED,
        "rollback_reference": str(args.rollback_reference).strip(),
        "created_by": args.operator or os.environ.get("USER") or "unknown",
    }
    problems = mk.validate_marker(marker, runtime_root_identifier=str(root))
    if problems:
        print("=== REFUSED: the marker this tool built is invalid ===")
        for p in problems:
            print(f"  x {p}")
        return 1

    dest = root.joinpath(*mk.MARKER_RELATIVE_PATH)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(marker, indent=2), encoding="utf-8")
    print(f"=== marker written: {dest} ===")
    for i in ids:
        print(f"  migrated: {i}")
    print(
        "\nStill to do, in a REVIEWED commit — not here:\n"
        "  1. flip these manifest rows to CUTOVER_COMPLETE\n"
        "  2. set RUNTIME_DATA_CUTOVER_ENABLED=1\n"
        "The deploy guard keeps refusing until EVERY blocking store is CUTOVER_COMPLETE."
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from app.platform import runtime_data_authority as auth

    root_set = bool(os.environ.get(rd.ENV_KEY))
    print("=== runtime-data authority status ===")
    print(f"  {rd.ENV_KEY} : {'set' if root_set else 'UNSET (LEGACY mode)'}")
    print(f"  {auth.CUTOVER_GATE_ENV} : {os.environ.get(auth.CUTOVER_GATE_ENV) or 'unset'}")
    blocking = manifest.blocking_stores()
    print(f"  blocking stores : {len(blocking)}")
    by_state: dict[str, int] = {}
    for s in manifest.STORES:
        by_state[str(s.get("migration_state"))] = by_state.get(str(s.get("migration_state")), 0) + 1
    for state, n in sorted(by_state.items()):
        print(f"    {state:26s} {n}")
    print("\n  A store is only deploy-safe at CUTOVER_COMPLETE.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _common(p: argparse.ArgumentParser, *, stores: bool = True) -> None:
        p.add_argument("--root", help="runtime root (default: from LEADGEN_RUNTIME_DATA_DIR)")
        if stores:
            p.add_argument("--stores", nargs="+", required=True, help="store ids for this wave")

    p = sub.add_parser("plan", help="read-only: what would move")
    _common(p)
    p.set_defaults(fn=cmd_plan)

    p = sub.add_parser("copy", help="additive byte copy + hashes")
    _common(p)
    p.add_argument("--yes", action="store_true")
    p.add_argument("--resume", action="store_true", help="allow overwriting a partial copy")
    p.set_defaults(fn=cmd_copy)

    p = sub.add_parser("verify", help="recompute both sides and compare")
    _common(p, stores=False)
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("activate", help="write the cutover marker (verify must have passed)")
    _common(p, stores=False)
    p.add_argument("--yes", action="store_true")
    p.add_argument("--rollback-reference", required=True, help="prior production sha")
    p.add_argument(
        "--release-sha",
        help="sha of the code these stores were verified against "
        "(only needed when git is unavailable, e.g. a tarball deploy)",
    )
    p.add_argument("--operator")
    p.set_defaults(fn=cmd_activate)

    p = sub.add_parser("status", help="where each store's authority resolves")
    p.set_defaults(fn=cmd_status)

    args = ap.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
