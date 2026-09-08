"""backfill_bounce_outcomes.py - reclassify NDR/complaint rows stuck as outcome='other'.

WHY
---
Measured on production 2026-07-25: ``interactions.outcome`` has exactly six live
values (interested / other / question / objection / ooo / unsubscribe). There is
no bounce or complaint category. Every mailer-daemon NDR silently landed in
``other`` (286 rows) — invisible to deliverability maths, and historically fed
to the LLM as if it were a human reply.

The forward fix lives in ``app/platform/reply_agent.classify_delivery_report``
(hard_bounce / soft_bounce / complaint, pre-LLM, never engagement). This script
repairs HISTORY for rows still labelled ``other`` that match the SAME detector.

HARD SCOPE
----------
* ONLY ``outcome='other'`` inbound email rows are candidates.
* Already-correct ``hard_bounce`` / ``soft_bounce`` / ``complaint`` rows are skipped
  (idempotent).
* Detection REUSES ``reply_agent.classify_delivery_report`` — no duplicated regexes.
* Subject-only rows stay ``other`` (HARD RULE: never guess from subject alone).

SAFETY
------
* dry-run by DEFAULT — ``--apply`` required to write
* idempotent — ``WHERE outcome='other'`` SQL guard + classifier re-check
* fail-CLOSED — any error exits non-zero
* no PII printed — counts only

Usage:
    python scripts/backfill_bounce_outcomes.py            # dry run
    python scripts/backfill_bounce_outcomes.py --apply    # write

Rates (once applied on prod), against known send denominator N=2543:
    hard_bounce_rate   = hard_bounce_count   / 2543
    soft_bounce_rate   = soft_bounce_count   / 2543
    complaint_rate     = complaint_count     / 2543
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys
from typing import Any, Iterable

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Known prod send denominator (2026-06-11 → 2026-07-21). Used only for the
# printed rate formula — never invented counts.
KNOWN_SEND_DENOMINATOR = 2543


def _ensure_repo_importable() -> None:
    """CLI-only sys.path fix - never at import time (see ADR-147)."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def _meta_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw) if isinstance(raw, str) else {}
    except Exception:
        return {}


def classify_row(
    *,
    body_summary: str = "",
    meta_json: Any = None,
    classify_fn: Any,
) -> str | None:
    """Pure — map one interaction row to a delivery outcome or None.

    Interaction table has no From/email column; we recover structural signals
    from body_summary + meta_json (forward path now stores ``from`` / ``kind``).
    """
    meta = _meta_dict(meta_json)
    frm = str(meta.get("from") or meta.get("email") or "").strip()
    subj = str(meta.get("subject") or "").strip()
    body = str(body_summary or "")
    # Historical rows often only have body_summary. If the summary itself embeds
    # an NDR From-ish localpart, surface it as frm so bounce-sender gate fires.
    if not frm:
        low = body.lower()
        for lp in ("mailer-daemon@", "postmaster@", "bounce@", "complaint@", "abuse@"):
            if lp in low:
                # synthetic address — localpart is what the classifier reads
                frm = lp.rstrip("@") + "@ndr.invalid"
                break
    return classify_fn(
        frm,
        None,
        subj,
        body,
        content_type=str(meta.get("content_type") or ""),
        auto_submitted=str(meta.get("auto_submitted") or ""),
        feedback_type=str(meta.get("feedback_type") or ""),
    )


def plan(
    rows: Iterable[tuple[str, str | None, Any]],
    classify_fn: Any,
) -> dict[str, Any]:
    """Pure — no DB. ``rows`` = (id, body_summary, meta_json) for outcome='other'.

    Returns deterministic update map + counts. Never prints PII.
    """
    updates: dict[str, str] = {}
    stats: collections.Counter[str] = collections.Counter()
    for iid, body, meta in rows:
        rid = (iid or "").strip()
        if not rid:
            continue
        stats["other_rows"] += 1
        kind = classify_row(body_summary=body or "", meta_json=meta, classify_fn=classify_fn)
        if kind is None:
            stats["unchanged"] += 1
            continue
        updates[rid] = kind
        stats[f"to_{kind}"] += 1
        stats["to_reclassify"] += 1
    return {"updates": updates, "stats": dict(stats)}


def run(engine: Any, classify_fn: Any, *, apply: bool) -> dict[str, Any]:
    """Fetch outcome='other' email inbound rows, plan, optionally write."""
    from sqlalchemy import text

    with engine.connect() as conn:
        rows = [
            (r[0], r[1], r[2])
            for r in conn.execute(
                text(
                    "select id, body_summary, meta_json from interactions "
                    "where lower(trim(coalesce(outcome, ''))) = 'other' "
                    "and lower(trim(coalesce(channel, ''))) = 'email' "
                    "and lower(trim(coalesce(direction, ''))) = 'in'"
                )
            )
        ]

    p = plan(rows, classify_fn)
    result: dict[str, Any] = {
        "updates": p["updates"],
        "stats": dict(p["stats"]),
        "candidate_count": len(rows),
        "applied": False,
        "updated": 0,
        "send_denominator": KNOWN_SEND_DENOMINATOR,
    }

    if not apply:
        return result

    updated = 0
    with engine.begin() as conn:
        for iid, kind in p["updates"].items():
            # SQL-guarded: only rewrite rows still at 'other' (idempotent).
            res = conn.execute(
                text(
                    "update interactions set outcome = :kind "
                    "where id = :iid and lower(trim(coalesce(outcome, ''))) = 'other'"
                ),
                {"kind": kind, "iid": iid},
            )
            if (res.rowcount or 0) == 1:
                updated += 1

    result.update({"applied": True, "updated": updated})
    return result


def _rate(n: int, denom: int) -> str:
    if denom <= 0:
        return "n/a"
    return f"{(n / denom) * 100:.3f}%"


def main(argv: list[str]) -> int:
    _ensure_repo_importable()
    apply = "--apply" in argv

    from sqlalchemy import create_engine

    from app.config import settings
    from app.platform.reply_agent import classify_delivery_report

    url = getattr(settings, "database_url", "") or getattr(settings, "DATABASE_URL", "") or ""
    url = url.replace("postgresql+asyncpg://", "postgresql://").replace("+asyncpg", "")
    if not url:
        print("[backfill] FATAL: no database_url in app.config.settings")
        return 2

    engine = create_engine(url)
    r = run(engine, classify_delivery_report, apply=apply)
    st = r["stats"]
    denom = int(r["send_denominator"])
    hard = int(st.get("to_hard_bounce", 0))
    soft = int(st.get("to_soft_bounce", 0))
    complaint = int(st.get("to_complaint", 0))

    print("=" * 62)
    print("BOUNCE/COMPLAINT OUTCOME BACKFILL - " + ("APPLY" if apply else "DRY RUN"))
    print("=" * 62)
    print(f"outcome='other' email inbound   : {r['candidate_count']}")
    print(f"  -> hard_bounce                 : {hard}")
    print(f"  -> soft_bounce                 : {soft}")
    print(f"  -> complaint                   : {complaint}")
    print(f"  unchanged (no structural NDR) : {st.get('unchanged', 0)}")
    print(f"TO RECLASSIFY                   : {st.get('to_reclassify', 0)}")
    print("-" * 62)
    print(f"Projected rates vs N={denom} sends (formula only; apply on prod for truth):")
    print(f"  hard_bounce_rate = {hard}/{denom} = {_rate(hard, denom)}")
    print(f"  soft_bounce_rate = {soft}/{denom} = {_rate(soft, denom)}")
    print(f"  complaint_rate   = {complaint}/{denom} = {_rate(complaint, denom)}")

    if not apply:
        print(
            f"\n[DRY RUN] would update {len(r['updates'])} interaction row(s). Re-run with --apply."
        )
        return 0

    print(f"\n[APPLIED] updated {r['updated']} interaction row(s).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:  # fail CLOSED with context
        print(f"[backfill] FATAL {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(2)
