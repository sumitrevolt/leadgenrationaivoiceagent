#!/usr/bin/env python3
"""Lineage-aware app-image retention planner for scripts/deploy_vps.sh.

Rollback artifacts follow *deployment lineage*, not CreatedAt / newest-N.
Same-SHA redeploy preserves durable rollback state outside the git checkout.
Protected current + rollback tags must exist in the local image inventory
before any lineage write or removal plan is emitted.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

EXPECTED_SERVICES: frozenset[str] = frozenset(
    {"app", "worker", "scheduler", "worker-heavy", "worker-video"}
)
_FORBIDDEN_TAGS: frozenset[str] = frozenset({"", "MISSING", "latest", "<none>"})
# Short or full hex SHA tags only (deploy APP_VERSION form).
_TAG_RE = re.compile(r"^[0-9a-f]{7,40}$")

# Host-runtime path — never inside the git worktree (/opt/leadgen).
DEFAULT_LINEAGE_STATE_PATH = "/var/lib/leadgen/deploy_rollback_lineage.json"


@dataclass(frozen=True)
class ImageTag:
    tag: str
    created_at: str  # sortable ISO-ish string from `docker images --format`


@dataclass(frozen=True)
class LineageState:
    current_tag: str
    rollback_tag: str
    verified_sha: str
    updated_at: str


def is_valid_deploy_tag(tag: str) -> bool:
    t = (tag or "").strip()
    if t in _FORBIDDEN_TAGS:
        return False
    return bool(_TAG_RE.fullmatch(t))


def assert_consistent_running_tags(
    service_tags: dict[str, str],
    *,
    required_services: frozenset[str] | None = None,
) -> str:
    """Fail closed when any app-image service tag is missing/bad/skewed."""
    required = required_services or EXPECTED_SERVICES
    if not service_tags:
        raise ValueError("no running service tags provided")

    present = set(service_tags.keys())
    missing = sorted(required - present)
    extra = sorted(present - required)
    if missing or extra:
        raise ValueError(
            "incomplete service mapping: "
            f"missing={missing or []} extra={extra or []} "
            f"required={sorted(required)}"
        )

    bad: list[str] = []
    values: set[str] = set()
    for svc in sorted(required):
        raw = service_tags.get(svc)
        tag = "" if raw is None else str(raw).strip()
        if not is_valid_deploy_tag(tag):
            bad.append(f"{svc}={tag or '<empty>'}")
            continue
        values.add(tag)

    if bad:
        raise ValueError("invalid/missing/malformed service tag(s): " + ", ".join(bad))

    if len(values) != 1:
        min_len = min(len(t) for t in values)
        shortest = min(values, key=len)
        if min_len >= 7 and all(t.startswith(shortest) for t in values):
            return shortest
        raise ValueError(
            "inconsistent pre-deploy app-image tags: "
            + ", ".join(f"{k}={v}" for k, v in sorted(service_tags.items()))
        )
    return next(iter(values))


def load_lineage_state(path: str | Path) -> LineageState | None:
    """Return valid state, or None if absent. Corrupt files are refused as None."""
    p = Path(path)
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    current = str(raw.get("current_tag") or "").strip()
    rollback = str(raw.get("rollback_tag") or "").strip()
    verified = str(raw.get("verified_sha") or "").strip()
    updated = str(raw.get("updated_at") or "").strip()
    if not (
        is_valid_deploy_tag(current)
        and is_valid_deploy_tag(rollback)
        and is_valid_deploy_tag(verified)
        and rollback != current
        and verified == current
    ):
        return None
    return LineageState(
        current_tag=current,
        rollback_tag=rollback,
        verified_sha=verified,
        updated_at=updated or "unknown",
    )


def write_lineage_state(path: str | Path, state: LineageState) -> None:
    """Atomic replace under a host-runtime directory (not the git checkout)."""
    if not is_valid_deploy_tag(state.current_tag):
        raise ValueError(f"refusing to write invalid current_tag={state.current_tag!r}")
    if not is_valid_deploy_tag(state.rollback_tag):
        raise ValueError(f"refusing to write invalid rollback_tag={state.rollback_tag!r}")
    if state.rollback_tag == state.current_tag:
        raise ValueError("refusing to write lineage where rollback_tag == current_tag")
    if state.verified_sha != state.current_tag:
        raise ValueError("verified_sha must equal current_tag after exact-SHA health")

    p = Path(path)
    p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(p.parent, 0o700)
    except OSError:
        pass

    payload = json.dumps(asdict(state), indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=".lineage_", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(tmp_name, 0o640)
        except OSError:
            pass
        os.replace(tmp_name, p)
        try:
            os.chmod(p, 0o640)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def resolve_rollback_tag(
    *,
    current_tag: str,
    running_before_tag: str | None,
    stored_rollback_tag: str | None,
) -> str:
    """Pick durable immediate-previous rollback tag (never CreatedAt)."""
    current = (current_tag or "").strip()
    if not is_valid_deploy_tag(current):
        raise ValueError(f"invalid current_tag={current_tag!r}")

    running = (running_before_tag or "").strip()
    stored = (stored_rollback_tag or "").strip()

    if running and running != current:
        if not is_valid_deploy_tag(running):
            raise ValueError(f"invalid/malformed previous tag: {running!r}")
        return running

    # Same-SHA redeploy (or empty running): require durable stored rollback.
    if not stored or not is_valid_deploy_tag(stored) or stored == current:
        raise ValueError("same-SHA redeploy missing durable rollback lineage — refusing retention")
    return stored


def protected_tags(*, current_tag: str, rollback_tag: str) -> set[str]:
    """Exact new release + exact immediate rollback artifact."""
    current = current_tag.strip()
    rollback = rollback_tag.strip()
    if not is_valid_deploy_tag(current):
        raise ValueError(f"invalid current_tag={current_tag!r}")
    if not is_valid_deploy_tag(rollback):
        raise ValueError(f"invalid/malformed previous tag: {rollback_tag!r}")
    if rollback == current:
        raise ValueError("rollback_tag must differ from current_tag")
    return {current, rollback}


def assert_protected_artifacts_present(
    images: list[ImageTag],
    *,
    current_tag: str,
    rollback_tag: str,
) -> None:
    """Both protected tags must exist in the docker images inventory."""
    protected = protected_tags(current_tag=current_tag, rollback_tag=rollback_tag)
    present = {
        (img.tag or "").strip()
        for img in images
        if (img.tag or "").strip() and (img.tag or "").strip() not in _FORBIDDEN_TAGS
    }
    missing = sorted(t for t in protected if t not in present)
    if missing:
        raise ValueError("protected artifact(s) missing from image inventory: " + ",".join(missing))


def plan_removals(
    images: list[ImageTag],
    *,
    current_tag: str,
    rollback_tag: str,
    keep_images: int = 1,
) -> list[str]:
    """Return tags safe to remove after a verified deploy.

    Protected lineage tags are never removed — even when KEEP_IMAGES=1 and a
    rebuilt older tag has the newest CreatedAt. Creation time is never used as
    a lineage substitute. Callers must assert_protected_artifacts_present first.
    """
    if keep_images < 1:
        raise ValueError("keep_images must be >= 1")
    assert_protected_artifacts_present(images, current_tag=current_tag, rollback_tag=rollback_tag)
    protected = protected_tags(current_tag=current_tag, rollback_tag=rollback_tag)
    keep_floor = max(int(keep_images), len(protected))

    by_tag: dict[str, ImageTag] = {}
    for img in images:
        tag = (img.tag or "").strip()
        if not tag or tag in _FORBIDDEN_TAGS:
            continue
        by_tag[tag] = img

    ordered = sorted(by_tag.values(), key=lambda i: i.created_at, reverse=True)

    keep: set[str] = set(protected)
    for img in ordered:
        if len(keep) >= keep_floor:
            break
        if img.tag not in keep:
            keep.add(img.tag)

    remove: list[str] = []
    for img in ordered:
        if img.tag in protected:
            continue
        if img.tag in keep:
            continue
        if img.tag == current_tag:
            continue
        remove.append(img.tag)
    return remove


def next_lineage_state(
    *,
    verified_sha: str,
    running_before_tag: str,
    previous: LineageState | None,
    now_iso: str | None = None,
) -> LineageState:
    """Compute post-verify lineage. Call only after exact-SHA health OK."""
    ver = verified_sha.strip()
    if not is_valid_deploy_tag(ver):
        raise ValueError(f"invalid verified_sha={verified_sha!r}")
    running = running_before_tag.strip()
    rollback = resolve_rollback_tag(
        current_tag=ver,
        running_before_tag=running,
        stored_rollback_tag=(previous.rollback_tag if previous else None),
    )
    return LineageState(
        current_tag=ver,
        rollback_tag=rollback,
        verified_sha=ver,
        updated_at=now_iso or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plan lineage-aware image retention")
    ap.add_argument("--current", default="")
    ap.add_argument(
        "--previous",
        default="",
        help="Pre-deploy running tag (may equal --current on same-SHA redeploy)",
    )
    ap.add_argument(
        "--stored-rollback",
        default="",
        help="Durable rollback tag from lineage state (required when previous==current)",
    )
    ap.add_argument("--keep-images", type=int, default=1)
    ap.add_argument(
        "--images-json",
        default="",
        help='JSON list of {"tag","created_at"} from docker images',
    )
    ap.add_argument(
        "--running-json",
        default="",
        help="Required in deploy path: JSON object of all five service->tag mappings",
    )
    ap.add_argument(
        "--require-running-json",
        action="store_true",
        help="Fail closed if --running-json is absent/empty",
    )
    ap.add_argument(
        "--lineage-state",
        default="",
        help="Path to durable lineage JSON (read for stored rollback if needed)",
    )
    ap.add_argument(
        "--write-lineage",
        default="",
        help="If set, atomically write next lineage state to this path (post-verify only)",
    )
    ap.add_argument(
        "--assert-running-only",
        action="store_true",
        help="Only validate --running-json (all five services) and print the shared tag",
    )
    args = ap.parse_args(argv)

    if args.assert_running_only:
        if not str(args.running_json or "").strip():
            print("REFUSED: --running-json required for --assert-running-only", file=sys.stderr)
            return 2
        try:
            tag = assert_consistent_running_tags(json.loads(args.running_json))
        except ValueError as e:
            print(f"REFUSED: {e}", file=sys.stderr)
            return 2
        print(tag)
        return 0

    if not str(args.current or "").strip():
        print("REFUSED: --current required for retention planning", file=sys.stderr)
        return 2

    if args.require_running_json and not str(args.running_json or "").strip():
        print("REFUSED: --running-json required but empty", file=sys.stderr)
        return 2

    if args.running_json:
        running = json.loads(args.running_json)
        try:
            assert_consistent_running_tags(running)
        except ValueError as e:
            print(f"REFUSED: {e}", file=sys.stderr)
            return 2

    stored = (args.stored_rollback or "").strip()
    if not stored and args.lineage_state:
        st = load_lineage_state(args.lineage_state)
        if st:
            stored = st.rollback_tag

    if not str(args.images_json or "").strip():
        print("REFUSED: --images-json required for retention planning", file=sys.stderr)
        return 2

    prev = args.previous.strip() or None
    write_path = (args.write_lineage or "").strip()
    before_bytes: bytes | None = None
    if write_path:
        wp = Path(write_path)
        if wp.is_file():
            before_bytes = wp.read_bytes()

    try:
        rollback = resolve_rollback_tag(
            current_tag=args.current,
            running_before_tag=prev,
            stored_rollback_tag=stored or None,
        )
        raw = json.loads(args.images_json)
        images = [
            ImageTag(tag=str(r["tag"]), created_at=str(r.get("created_at") or "")) for r in raw
        ]
        # Inventory presence BEFORE removals plan and BEFORE lineage write.
        assert_protected_artifacts_present(images, current_tag=args.current, rollback_tag=rollback)
        removals = plan_removals(
            images,
            current_tag=args.current,
            rollback_tag=rollback,
            keep_images=args.keep_images,
        )
    except ValueError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2

    protected = sorted(protected_tags(current_tag=args.current, rollback_tag=rollback))
    print("ROLLBACK_TAG=" + rollback)
    print("PROTECTED=" + ",".join(protected))
    for t in removals:
        print(f"REMOVE={t}")
    if not removals:
        print("REMOVE=")

    if write_path:
        try:
            prev_state = load_lineage_state(args.lineage_state) if args.lineage_state else None
            state = next_lineage_state(
                verified_sha=args.current,
                running_before_tag=prev or args.current,
                previous=prev_state,
            )
            state = LineageState(
                current_tag=args.current.strip(),
                rollback_tag=rollback,
                verified_sha=args.current.strip(),
                updated_at=state.updated_at,
            )
            write_lineage_state(write_path, state)
            print(f"LINEAGE_WRITTEN={write_path}")
        except ValueError as e:
            print(f"REFUSED: lineage write failed: {e}", file=sys.stderr)
            # Leave prior bytes untouched on failed write attempts that raise
            # before replace; if file was absent it stays absent.
            if before_bytes is not None:
                wp = Path(write_path)
                if wp.is_file() and wp.read_bytes() != before_bytes:
                    wp.write_bytes(before_bytes)
            return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
