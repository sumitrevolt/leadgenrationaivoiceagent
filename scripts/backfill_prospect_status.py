"""backfill_prospect_status.py - reclassify prospects stuck at status='new'.

WHY
---
Measured on production ``f096a08d`` (2026-07-25): ``data/prospects.jsonl`` holds
18,100 prospects split ``ready`` 9,677 / ``needs_enrich`` 6,671 / ``new`` 1,736 /
``replied`` 16. That ``new`` bucket is a PERMANENT black hole:

* ``prospector.VALID_STATUSES`` is ``(ready, sent, replied, client, dead)`` -
  ``new`` is not even a pipeline state.
* Outreach only reads ``status='ready'`` (``prospector.pending_for_outreach``),
  so a ``new`` row can never be emailed.
* No job promoted ``new`` -> anything. ``udyam_pipeline.run()`` wrote a hardcoded
  ``"status": "new"`` for every row it persisted, so these rows were dead on
  arrival.

The forward fix (``app/platform/udyam_pipeline.py``) now mirrors the harvester's
ingest semantics - ``ready`` when a contact was found, else ``needs_enrich`` - but
that only affects FUTURE writes. This script applies the SAME rule to the rows
already on disk, so the status split stops lying and the enrichable rows become
visible to the enrichment sweep instead of sitting outside every query.

SCOPE - reclassify only, never promote past the ingest rule
-----------------------------------------------------------
* ONLY rows currently at ``status='new'`` are considered. Any other status
  (``ready``/``sent``/``replied``/``client``/``dead``/``needs_enrich``) is left
  byte-identical - so this can never downgrade a row that already progressed,
  and can never resurrect a dead/replied one.
* Rule (identical to ``lead_harvester.run_harvest`` ingest and the udyam fix):
  a usable contact -> ``ready``, otherwise -> ``needs_enrich``.
* ``needs_enrich`` is NOT a demotion here: ``new`` was unreachable by every job,
  whereas ``needs_enrich`` is exactly what the email-enrichment sweep scans.
* No network. Stored ``phone`` values already passed ``_valid_phone`` and stored
  ``email`` values already passed MX verification at ingest time, so re-verifying
  would only add a way for a transient DNS failure to misclassify a good row.
  Cheap local sanity checks are used instead (see ``has_contact``).

SAFETY
------
* dry-run by DEFAULT - ``--apply`` is required to write
* idempotent - after a successful apply there are no ``new`` rows left, so a
  second run finds 0 candidates and performs NO write
* one atomic write via the existing ``prospector.set_prospect_fields_bulk``
  (tmp file + replace) - no parallel writer, no per-row rewrite of the 20MB file
* fail-CLOSED - any error exits non-zero (see ``backfill_lead_status.py``)
* no PII printed - counts and source names only

Usage (from the repo root - the store path is relative):
    python scripts/backfill_prospect_status.py            # dry run
    python scripts/backfill_prospect_status.py --apply    # write
"""

from __future__ import annotations

import collections
import pathlib
import re
import sys
from typing import Any, Iterable

ROOT = pathlib.Path(__file__).resolve().parent.parent

_DIGITS = re.compile(r"\d")


def _ensure_repo_importable() -> None:
    """CLI-only sys.path fix - never at import time (see ADR-147)."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def has_contact(row: dict[str, Any]) -> bool:
    """Does this row carry a contact the pipeline can actually use?

    Mirrors the ingest rule ``"ready" if (p10 or email) else "needs_enrich"``,
    where ``p10 = phone[-10:]``. The extra local checks (>=10 digits for a phone,
    ``@`` plus a dotted domain for an email) only reject junk placeholders like
    ``"N/A"`` that would otherwise read as truthy - a genuine ``_valid_phone``
    E.164 output or MX-verified address always passes them.
    """
    phone = str(row.get("phone") or "").strip()
    if len(_DIGITS.findall(phone)) >= 10:
        return True
    email = str(row.get("email") or "").strip()
    return "@" in email and "." in email.split("@")[-1]


def plan(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Pure - no IO. Decide the new status for every row stuck at ``new``.

    Returns ``updates`` ({pid: {"status": ...}}) plus counts and a per-source
    breakdown, so a dry run can prove the candidate set matches expectations
    before anything is written.
    """
    updates: dict[str, dict[str, Any]] = {}
    stats = collections.Counter()
    by_source = collections.Counter()
    status_split = collections.Counter()

    for row in rows:
        status = str(row.get("status") or "").strip().lower()
        status_split[status or "(empty)"] += 1
        if status != "new":
            continue
        stats["candidates"] += 1
        pid = str(row.get("id") or "").strip()
        if not pid:
            # set_prospect_fields_bulk matches on id; a row without one cannot be
            # addressed. Counted so it is never silently invisible.
            stats["skipped_no_id"] += 1
            continue
        new_status = "ready" if has_contact(row) else "needs_enrich"
        updates[pid] = {"status": new_status}
        stats[f"to_{new_status}"] += 1
        by_source[str(row.get("source") or "(unknown)")] += 1

    return {
        "updates": updates,
        "stats": dict(stats),
        "by_source": dict(by_source),
        "status_split": dict(status_split),
        "total_rows": sum(status_split.values()),
    }


def run(prospector: Any, *, apply: bool) -> dict[str, Any]:
    """Read the store, compute the plan, optionally write. Pure of argv/printing
    so it is directly unit-testable with a monkeypatched prospector module."""
    p = plan(prospector._read_all())
    result: dict[str, Any] = {
        "total_rows": p["total_rows"],
        "status_split": p["status_split"],
        "stats": p["stats"],
        "by_source": p["by_source"],
        "candidates": len(p["updates"]),
        "applied": False,
        "updated": 0,
    }
    if not apply or not p["updates"]:
        return result

    updated = prospector.set_prospect_fields_bulk(p["updates"])
    result.update({"applied": True, "updated": int(updated or 0)})
    if result["updated"] != result["candidates"]:
        # Writer reported fewer matches than planned -> the store changed under us
        # or an id did not match. Surface it; main() turns this into a non-zero exit.
        result["mismatch"] = True
    return result


def main(argv: list[str]) -> int:
    _ensure_repo_importable()
    apply = "--apply" in argv

    from app.platform import prospector

    store = pathlib.Path(prospector._PROSPECTS_FILE())
    if not store.is_file():
        print(
            f"[backfill] FATAL: prospect store not found at {store} (run this from the repo root)",
            file=sys.stderr,
        )
        return 2

    r = run(prospector, apply=apply)
    st = r["stats"]

    mode = "APPLY" if apply else "DRY RUN"
    print("=" * 62)
    print(f"PROSPECT STATUS BACKFILL (new -> ready/needs_enrich) - {mode}")
    print("=" * 62)
    print(f"prospects total              : {r['total_rows']}")
    for status, count in sorted(r["status_split"].items(), key=lambda kv: -kv[1]):
        print(f"  status={status:<14}     : {count}")
    print(f"candidates (status='new')    : {st.get('candidates', 0)}")
    if st.get("skipped_no_id"):
        print(f"  skipped (no id)            : {st['skipped_no_id']}")
    print(f"  -> ready (has contact)     : {st.get('to_ready', 0)}")
    print(f"  -> needs_enrich (no contact): {st.get('to_needs_enrich', 0)}")
    if r["by_source"]:
        print("candidate sources:")
        for src, count in sorted(r["by_source"].items(), key=lambda kv: -kv[1]):
            print(f"  {src:<28} : {count}")

    if not apply:
        print(
            f"\n[DRY RUN] would reclassify {r['candidates']} prospect(s) in one "
            "atomic write. Re-run with --apply."
        )
        return 0

    if not r["applied"]:
        print("\n[APPLIED] nothing to do - no rows at status='new' (already idempotent).")
        return 0

    print(f"\n[APPLIED] reclassified {r['updated']} prospect(s).")
    if r.get("mismatch"):
        print(
            f"[backfill] FATAL: planned {r['candidates']} but writer matched "
            f"{r['updated']} - store changed mid-run, re-run the dry run",
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:  # fail CLOSED with context
        print(f"[backfill] FATAL {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(2)
