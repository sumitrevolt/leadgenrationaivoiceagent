"""backfill_interaction_identity.py — link orphaned interactions to leads/contacts.

WHY
---
``interaction_log.record()`` historically resolved identity from PHONE only.
Outreach is overwhelmingly EMAIL, and an email interaction carries no phone, so
every email interaction landed with ``lead_id = NULL``. Measured on production
2026-07-25: 2,611 interaction rows, **zero** with a ``lead_id`` — including 295
replies whose outcome was ``interested``. Those warm prospects were invisible to
the lead pipeline, which is why all 10,559 leads sat at ``status='new'`` and
``lead_status_history`` was empty.

The forward fix lives in ``app/platform/interaction_log.py``. This script repairs
the HISTORY, using ``data/interactions.jsonl`` — the JSONL keeps the ``email``
field that the ``interactions`` table never had a column for.

SCOPE — deliberately linkage only
---------------------------------
This sets ``lead_id`` / ``contact_id`` on existing rows. It does NOT change
``leads.status`` and does NOT write ``lead_status_history``: deciding that a
reply means "contacted" or "interested" is a business-state judgement and
belongs in its own reviewed change. Linking is a statement of fact; status is
an opinion.

SAFETY
------
* dry-run by DEFAULT — ``--apply`` is required to write
* only ever fills a NULL ``lead_id`` / ``contact_id``; never overwrites
* never invents an id: an unmatched email is left alone and counted
* no PII printed — counts and domains only

Usage:
    python scripts/backfill_interaction_identity.py            # dry run
    python scripts/backfill_interaction_identity.py --apply    # write
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
JSONL = ROOT / "data" / "interactions.jsonl"


def _ensure_repo_importable() -> None:
    """CLI-only sys.path fix — never at import time (see ADR-147)."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def load_jsonl() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not JSONL.exists():
        return out
    with open(JSONL, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def plan(
    records: list[dict[str, Any]],
    lead_by_email: dict[str, str],
    contact_by_email: dict[str, str],
    orphan_ids: set[str],
) -> dict[str, Any]:
    """Compute the (deterministic) set of updates. Pure — no DB writes."""
    updates: list[tuple[str, str | None, str | None]] = []
    unmatched_domains: collections.Counter = collections.Counter()
    stats = collections.Counter()

    for r in sorted(records, key=lambda x: str(x.get("id") or "")):
        iid = str(r.get("id") or "").strip()
        if not iid:
            stats["no_id"] += 1
            continue
        if iid not in orphan_ids:
            stats["already_linked_or_absent"] += 1
            continue
        em = (r.get("email") or "").strip().lower()
        if not em:
            stats["no_email"] += 1
            continue
        lid = lead_by_email.get(em)
        cid = contact_by_email.get(em)
        if not lid and not cid:
            stats["unmatched"] += 1
            unmatched_domains[em.split("@")[-1]] += 1
            continue
        updates.append((iid, lid, cid))
        stats["linkable"] += 1
        if r.get("outcome") == "interested":
            stats["linkable_interested"] += 1

    return {
        "updates": updates,
        "stats": dict(stats),
        "unmatched_domains": unmatched_domains.most_common(10),
    }


def main(argv: list[str]) -> int:
    _ensure_repo_importable()
    apply = "--apply" in argv

    from sqlalchemy import create_engine, text

    from app.config import settings

    # app.config exposes it lowercase (settings.database_url); accept either so
    # this keeps working if the settings casing ever changes.
    url = getattr(settings, "database_url", "") or getattr(settings, "DATABASE_URL", "") or ""
    url = url.replace("postgresql+asyncpg://", "postgresql://").replace("+asyncpg", "")
    if not url:
        print("[backfill] FATAL: no database_url in app.config.settings")
        return 2

    engine = create_engine(url)
    with engine.connect() as conn:
        lead_by_email = {
            e.lower(): i
            for i, e in conn.execute(
                text(
                    "select id, lower(trim(email)) from leads "
                    "where email is not null and email <> ''"
                )
            )
        }
        contact_by_email = {
            e.lower(): i
            for i, e in conn.execute(
                text(
                    "select id, lower(trim(email)) from contacts "
                    "where email is not null and email <> ''"
                )
            )
        }
        orphan_ids = {
            r[0] for r in conn.execute(text("select id from interactions where lead_id is null"))
        }

    records = load_jsonl()
    p = plan(records, lead_by_email, contact_by_email, orphan_ids)

    print("=" * 62)
    print("INTERACTION IDENTITY BACKFILL — " + ("APPLY" if apply else "DRY RUN"))
    print("=" * 62)
    print(f"jsonl records          : {len(records)}")
    print(f"orphan rows in DB      : {len(orphan_ids)}")
    print(f"lead emails            : {len(lead_by_email)}")
    print(f"contact emails         : {len(contact_by_email)}")
    print()
    for k in (
        "linkable",
        "linkable_interested",
        "unmatched",
        "no_email",
        "already_linked_or_absent",
        "no_id",
    ):
        if p["stats"].get(k):
            print(f"  {k:<26} {p['stats'][k]}")
    print()
    print("top unmatched domains (counts only):")
    for d, c in p["unmatched_domains"]:
        print(f"   {d:<30} {c}")

    if not apply:
        print(
            f"\n[DRY RUN] would update {len(p['updates'])} interaction row(s). "
            "Re-run with --apply to write."
        )
        return 0

    written = 0
    with engine.begin() as conn:
        for iid, lid, cid in p["updates"]:
            res = conn.execute(
                text(
                    "update interactions set lead_id = coalesce(lead_id, :lid), "
                    "contact_id = coalesce(contact_id, :cid) where id = :iid"
                ),
                {"lid": lid, "cid": cid, "iid": iid},
            )
            written += res.rowcount or 0
    print(f"\n[APPLIED] updated {written} interaction row(s).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:  # fail CLOSED with context
        print(f"[backfill] FATAL {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(2)
