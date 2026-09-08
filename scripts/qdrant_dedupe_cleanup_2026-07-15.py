"""ADR-104 Qdrant scoped duplicate cleanup — 2026-07-15.

Executes ONLY the exact 8-point deletion approved against
docs/QDRANT_DUPLICATE_CLEANUP_DRYRUN_2026-07-15.md. Revalidates the live
candidate set against the approved fingerprint/ID list before deleting
anything; aborts with no changes if the live state has drifted from what
was approved. Explicit point-ID deletion only (qmodels.PointIdsList) --
never a filter-based or namespace-wide delete.

Run inside the app container (has qdrant-client + network access to
qdrant:6333):
    docker exec leadgen_app python /tmp/qdrant_dedupe_cleanup_2026-07-15.py
"""

from __future__ import annotations

import hashlib
import sys

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

COLLECTION = "kb_main"

# Exact approved scope from the 2026-07-15 dry-run report -- keep (canonical)
# and drop (duplicate) point IDs, paired by fingerprint. Only DROP_IDS are
# ever deleted; KEEP_IDS are verified to still exist afterward.
APPROVED_PAIRS = [
    (
        "df07a21be4ad",
        "0c54070c-361a-5be4-ab3c-af2a00ebbb6b",
        ["e6a6e099-2164-4d48-832b-9190c3e6c4fd"],
    ),
    (
        "ea3a0cfb889b",
        "111b3ab5-9a90-518f-a107-b64d112c2358",
        ["450f4c6f-fb5a-4c9c-9e9e-7805a134758d", "a870bf1f-1685-4205-a6ea-18de6b57adc7"],
    ),
    (
        "f49bc13997ca",
        "357291d2-c89a-4c81-ab5e-1dc72e0008e1",
        ["9ff5d624-9a21-534b-a0e5-25c7a85d2c21"],
    ),
    (
        "1df386f90e64",
        "4d012ae5-858b-5ae9-be6b-cfd18cf7e3e1",
        ["51da46e5-011c-4cda-8154-bc5571b039eb"],
    ),
    (
        "5b7a96305ca9",
        "531c04e8-4a79-5a1b-a215-336f63c004b5",
        ["7ac06641-a726-4ecc-ae83-8e386c728920"],
    ),
    (
        "759ce6691241",
        "5bcad415-4b13-56b7-83c7-7ee7bf72c994",
        ["e54603b0-4df8-4eab-bdae-e21a65425703"],
    ),
    (
        "4877dc02a5d7",
        "617fd6f4-2027-5c94-aafc-0e8324ff1b7d",
        ["d401da52-a431-4067-bd66-03a0e0d2f336"],
    ),
]
KEEP_IDS = sorted({p[1] for p in APPROVED_PAIRS})
DROP_IDS = sorted({d for p in APPROVED_PAIRS for d in p[2]})
assert len(DROP_IDS) == 8, f"expected 8 drop ids, got {len(DROP_IDS)}"

APPROVED_NAMESPACES = {"ab:ragquality", "ab:ragtest"}


def fingerprint(namespace: str, source: str, text: str) -> str:
    raw = f"{namespace}|{source}|{text}".encode("utf-8", "ignore")
    return hashlib.sha1(raw).hexdigest()


def scan_duplicates(client: QdrantClient) -> tuple[dict[str, list[str]], dict[str, int]]:
    """Full scroll of kb_main; returns {fingerprint: [point_ids in encounter order]}
    and a namespace -> point-count map (for before/after namespace-count checks)."""
    seen: dict[str, list[str]] = {}
    ns_counts: dict[str, int] = {}
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for p in points:
            payload = p.payload or {}
            ns = str(payload.get("namespace", ""))
            source = str(payload.get("source", ""))
            text = str(payload.get("text", ""))
            fp = fingerprint(ns, source, text)
            seen.setdefault(fp, []).append(str(p.id))
            ns_counts[ns] = ns_counts.get(ns, 0) + 1
        if offset is None:
            break
    return seen, ns_counts


def main() -> int:
    client = QdrantClient(url="http://qdrant:6333", timeout=15)

    info_before = client.get_collection(COLLECTION)
    count_before = info_before.points_count
    print(f"[before] {COLLECTION}.points_count = {count_before}")
    print(f"[before] {COLLECTION}.status = {info_before.status}")

    seen, ns_counts_before = scan_duplicates(client)
    live_drop_ids: list[str] = []
    live_extra_fp_count = 0
    offending_namespaces: set[str] = set()
    for fp, ids in seen.items():
        if len(ids) <= 1:
            continue
        live_extra_fp_count += 1
        canonical, *dupes = ids
        live_drop_ids.extend(dupes)

    live_drop_set = set(live_drop_ids)
    approved_drop_set = set(DROP_IDS)

    print(f"[revalidate] live duplicate fingerprints: {live_extra_fp_count} (approved: 7)")
    print(f"[revalidate] live extra/duplicate point count: {len(live_drop_set)} (approved: 8)")
    print(
        f"[revalidate] live drop-id set == approved drop-id set: {live_drop_set == approved_drop_set}"
    )

    if live_drop_set != approved_drop_set:
        print(
            "ABORT: live candidate set does not match the approved 8-point scope. "
            "No deletion performed.",
            file=sys.stderr,
        )
        print(f"  live only : {sorted(live_drop_set - approved_drop_set)}", file=sys.stderr)
        print(f"  approved only: {sorted(approved_drop_set - live_drop_set)}", file=sys.stderr)
        return 2

    # Namespace scope check -- every point whose payload namespace is one of
    # the approved namespaces; confirm no drop id lives outside them.
    for fp, ids in seen.items():
        if len(ids) <= 1:
            continue
        # We don't have namespace directly here without a second pass; re-check below.
    # Re-scan to map id -> namespace for the drop set only (cheap, bounded to 8 ids).
    retrieved = client.retrieve(collection_name=COLLECTION, ids=DROP_IDS, with_payload=True)
    bad_ns = [
        r.id
        for r in retrieved
        if str((r.payload or {}).get("namespace", "")) not in APPROVED_NAMESPACES
    ]
    if bad_ns:
        print(f"ABORT: drop ids outside approved namespaces: {bad_ns}", file=sys.stderr)
        return 3
    if len(retrieved) != 8:
        print(
            f"ABORT: expected to retrieve exactly 8 drop points, got {len(retrieved)}",
            file=sys.stderr,
        )
        return 4

    print(
        "[revalidate] PASS -- live candidate set matches the approved 8-point scope exactly. Proceeding."
    )

    client.delete(
        collection_name=COLLECTION,
        points_selector=qmodels.PointIdsList(points=DROP_IDS),
    )
    print(f"[delete] issued explicit PointIdsList delete for {len(DROP_IDS)} ids: {DROP_IDS}")

    info_after = client.get_collection(COLLECTION)
    count_after = info_after.points_count
    print(f"[after] {COLLECTION}.points_count = {count_after}")
    print(f"[after] {COLLECTION}.status = {info_after.status}")
    print(f"[after] delta = {count_before - count_after} (expected 8)")

    seen_after, ns_counts_after = scan_duplicates(client)
    extra_after = sum(1 for ids in seen_after.values() if len(ids) > 1)
    print(f"[verify] duplicate fingerprints remaining after cleanup: {extra_after} (expected 0)")

    keep_check = client.retrieve(collection_name=COLLECTION, ids=KEEP_IDS, with_payload=False)
    print(f"[verify] canonical (keep) points still present: {len(keep_check)}/7 (expected 7)")

    for ns in ("solar_residential", "insurance", "ai_marketing", "home_loans", "_global"):
        before_n = ns_counts_before.get(ns)
        after_n = ns_counts_after.get(ns)
        print(
            f"[verify] namespace '{ns}' count before={before_n} after={after_n} unchanged={before_n == after_n}"
        )

    for ns in APPROVED_NAMESPACES:
        before_n = ns_counts_before.get(ns)
        after_n = ns_counts_after.get(ns)
        print(f"[verify] namespace '{ns}' count before={before_n} after={after_n}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
