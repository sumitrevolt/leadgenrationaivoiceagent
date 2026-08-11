#!/usr/bin/env python3
"""Lineage-aware app-image retention planner for scripts/deploy_vps.sh.

Rollback artifacts must follow *deployment lineage*, not CreatedAt / newest-N.
A rebuilt older SHA can have a newer CreatedAt and must never displace the
immediate previous production tag. KEEP_IMAGES=1 must not silently delete the
sole rollback artifact.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class ImageTag:
    tag: str
    created_at: str  # sortable ISO-ish string from `docker images --format`


def assert_consistent_running_tags(service_tags: dict[str, str]) -> str:
    """Fail closed when app-image services disagree on the running tag."""
    if not service_tags:
        raise ValueError("no running service tags provided")
    values = {str(v).strip() for v in service_tags.values() if str(v).strip()}
    values.discard("")
    values.discard("MISSING")
    if len(values) != 1:
        raise ValueError(
            "inconsistent pre-deploy app-image tags: "
            + ", ".join(f"{k}={v}" for k, v in sorted(service_tags.items()))
        )
    return next(iter(values))


def protected_tags(*, current_tag: str, previous_tag: str | None) -> set[str]:
    """Exact new release + exact immediate previous production tag."""
    out = {current_tag.strip()}
    if previous_tag and previous_tag.strip() and previous_tag.strip() != current_tag.strip():
        out.add(previous_tag.strip())
    out.discard("")
    out.discard("<none>")
    out.discard("latest")
    return out


def plan_removals(
    images: list[ImageTag],
    *,
    current_tag: str,
    previous_tag: str | None,
    keep_images: int = 1,
) -> list[str]:
    """Return tags safe to remove after a verified deploy.

    Protected lineage tags are never removed — even when KEEP_IMAGES=1 and a
    rebuilt older tag has the newest CreatedAt.
    """
    if keep_images < 1:
        raise ValueError("keep_images must be >= 1")
    protected = protected_tags(current_tag=current_tag, previous_tag=previous_tag)
    # Effective keep floor is at least the protected lineage set size.
    keep_floor = max(int(keep_images), len(protected))

    # Unique by tag (last write wins for created_at if duplicates).
    by_tag: dict[str, ImageTag] = {}
    for img in images:
        tag = (img.tag or "").strip()
        if not tag or tag in {"<none>", "latest"}:
            continue
        by_tag[tag] = img

    # Newest-first for deciding which *unprotected* extras to keep.
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plan lineage-aware image retention")
    ap.add_argument("--current", required=True)
    ap.add_argument("--previous", default="")
    ap.add_argument("--keep-images", type=int, default=1)
    ap.add_argument(
        "--images-json",
        required=True,
        help='JSON list of {"tag","created_at"} from docker images',
    )
    ap.add_argument(
        "--running-json",
        default="",
        help="Optional JSON object service->tag; if set, must be consistent",
    )
    args = ap.parse_args(argv)

    if args.running_json:
        running = json.loads(args.running_json)
        try:
            assert_consistent_running_tags(running)
        except ValueError as e:
            print(f"REFUSED: {e}", file=sys.stderr)
            return 2

    raw = json.loads(args.images_json)
    images = [ImageTag(tag=str(r["tag"]), created_at=str(r.get("created_at") or "")) for r in raw]
    prev = args.previous.strip() or None
    try:
        removals = plan_removals(
            images,
            current_tag=args.current,
            previous_tag=prev,
            keep_images=args.keep_images,
        )
    except ValueError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2

    protected = sorted(protected_tags(current_tag=args.current, previous_tag=prev))
    print("PROTECTED=" + ",".join(protected))
    for t in removals:
        print(f"REMOVE={t}")
    if not removals:
        print("REMOVE=")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
