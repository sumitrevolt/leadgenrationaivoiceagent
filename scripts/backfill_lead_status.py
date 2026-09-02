"""backfill_lead_status.py - promote leads with a real outbound touch NEW -> CONTACTED.

WHY
---
Measured on production ``f096a08d`` (2026-07-25): ``leads`` = 10,759 rows, every
single one ``status='new'``; ``lead_status_history`` = 0 rows (never written in
the product's life). ``scripts/backfill_interaction_identity.py`` has since linked
``interactions.lead_id``, so 1,363 distinct leads now demonstrably received an
OUTBOUND touch (``direction='out'``). An outbound touch is a fact: we contacted
them. This repairs the HISTORY by advancing exactly those leads NEW -> CONTACTED
and writing their ``lead_status_history`` rows. The forward fix (auto-transition
on every new outbound interaction) lives in ``app/platform/interaction_log.py``
via ``Lead.mark_contacted()``.

HARD SCOPE - contacted only, no opinions
----------------------------------------
* ONLY NEW -> CONTACTED. QUALIFIED / APPOINTMENT / CONVERTED are NOT invented -
  there is no trustworthy signal for them yet (the ``outcome='interested'`` signal
  was poisoned: 285 of 295 came from one adityabirla.com ticketing autoresponder
  whose bodies say "Not required as of now. Hence, case is closed.").
* Closure-noise exclusion: any interaction whose ``body_summary`` matches the SAME
  guard regex used by ``app/platform/reply_agent._is_case_closure`` is NOT counted
  as a real touch. (Outbound copy never matches this in practice; the filter is a
  belt-and-braces guarantee that a mislabelled closure row can never promote.)
* NEVER downgrades: only rows currently at ``new`` are touched (SQL-guarded), so a
  lead already past contacted is left exactly as-is.

SAFETY
------
* dry-run by DEFAULT - ``--apply`` is required to write
* idempotent - the ``where status='new'`` guard means a second run is a no-op and
  writes no duplicate history
* fail-CLOSED - any error exits non-zero (see ``backfill_interaction_identity.py``)
* no PII printed - counts only

Usage:
    python scripts/backfill_lead_status.py            # dry run
    python scripts/backfill_lead_status.py --apply    # write
"""

from __future__ import annotations

import collections
import pathlib
import sys
from datetime import datetime
from typing import Any, Iterable

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _ensure_repo_importable() -> None:
    """CLI-only sys.path fix - never at import time (see ADR-147)."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def plan(
    outbound_rows: Iterable[tuple[str, str | None]],
    new_lead_ids: set[str],
    closure_re: Any,
) -> dict[str, Any]:
    """Pure - no DB. Decide which NEW leads have a real (non-closure) outbound touch.

    ``outbound_rows`` = (lead_id, body_summary) for every ``direction='out'``
    interaction that carries a ``lead_id``. ``closure_re`` = the compiled regex
    from ``reply_agent._CLOSURE_RE``. Returns the deterministic, sorted set of
    lead ids to promote plus counts.
    """
    real_touch: set[str] = set()
    closure_only_candidates: set[str] = set()
    stats = collections.Counter()

    for lead_id, body in outbound_rows:
        lid = (lead_id or "").strip()
        if not lid:
            continue
        stats["outbound_rows"] += 1
        if body and closure_re.search(body):
            stats["closure_noise_rows"] += 1
            closure_only_candidates.add(lid)
            continue
        real_touch.add(lid)

    # A lead whose ONLY outbound rows were closure-noise never earns a touch.
    closure_only = closure_only_candidates - real_touch
    stats["leads_with_real_touch"] = len(real_touch)
    stats["leads_closure_noise_only"] = len(closure_only)

    promote = sorted(real_touch & new_lead_ids)
    stats["already_advanced_skipped"] = len(real_touch - new_lead_ids)
    stats["to_promote"] = len(promote)
    return {"promote": promote, "stats": dict(stats)}


def run(engine: Any, closure_re: Any, *, apply: bool) -> dict[str, Any]:
    """Fetch inputs from ``engine``, compute the plan, optionally write. Pure of
    argv/printing so it is directly unit-testable against a sqlite engine."""
    from sqlalchemy import text

    with engine.connect() as conn:
        new_lead_ids = {
            r[0] for r in conn.execute(text("select id from leads where status = 'new'"))
        }
        outbound_rows = [
            (r[0], r[1])
            for r in conn.execute(
                text(
                    "select lead_id, body_summary from interactions "
                    "where lead_id is not null "
                    "and lower(trim(coalesce(direction, ''))) = 'out'"
                )
            )
        ]

    p = plan(outbound_rows, new_lead_ids, closure_re)
    result: dict[str, Any] = {
        "promote": p["promote"],
        "stats": dict(p["stats"]),
        "new_lead_count": len(new_lead_ids),
        "applied": False,
        "promoted": 0,
        "history": 0,
    }

    if not apply:
        return result

    promoted = 0
    history = 0
    now = datetime.utcnow()
    with engine.begin() as conn:
        for lid in p["promote"]:
            # SQL-guarded so this stays idempotent AND never downgrades even if the
            # row advanced between the read above and this write.
            res = conn.execute(
                text(
                    "update leads set status = 'contacted', updated_at = :ts "
                    "where id = :lid and status = 'new'"
                ),
                {"ts": now, "lid": lid},
            )
            if (res.rowcount or 0) != 1:
                continue
            promoted += 1
            conn.execute(
                text(
                    "insert into lead_status_history "
                    "(lead_id, old_status, new_status, changed_by, changed_at) "
                    "values (:lid, 'new', 'contacted', :cb, :ts)"
                ),
                {"lid": lid, "cb": "backfill:outreach", "ts": now},
            )
            history += 1

    result.update({"applied": True, "promoted": promoted, "history": history})
    return result


def main(argv: list[str]) -> int:
    _ensure_repo_importable()
    apply = "--apply" in argv

    from sqlalchemy import create_engine

    from app.config import settings
    from app.platform.reply_agent import _CLOSURE_RE  # single-source closure regex

    url = getattr(settings, "database_url", "") or getattr(settings, "DATABASE_URL", "") or ""
    url = url.replace("postgresql+asyncpg://", "postgresql://").replace("+asyncpg", "")
    if not url:
        print("[backfill] FATAL: no database_url in app.config.settings")
        return 2

    engine = create_engine(url)
    r = run(engine, _CLOSURE_RE, apply=apply)
    st = r["stats"]

    print("=" * 62)
    print("LEAD STATUS BACKFILL (new -> contacted) - " + ("APPLY" if apply else "DRY RUN"))
    print("=" * 62)
    print(f"leads at status='new'        : {r['new_lead_count']}")
    print(f"outbound interaction rows    : {st.get('outbound_rows', 0)}")
    print(f"  closure-noise rows skipped : {st.get('closure_noise_rows', 0)}")
    print(f"leads with a real touch      : {st.get('leads_with_real_touch', 0)}")
    print(f"  closure-noise-only leads   : {st.get('leads_closure_noise_only', 0)}")
    print(f"  already past 'new' (skip)  : {st.get('already_advanced_skipped', 0)}")
    print(f"TO PROMOTE new->contacted    : {st.get('to_promote', 0)}")

    if not apply:
        print(
            f"\n[DRY RUN] would promote {len(r['promote'])} lead(s) and write "
            f"{len(r['promote'])} lead_status_history row(s). Re-run with --apply."
        )
        return 0

    print(f"\n[APPLIED] promoted {r['promoted']} lead(s); wrote {r['history']} history row(s).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:  # fail CLOSED with context
        print(f"[backfill] FATAL {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(2)
