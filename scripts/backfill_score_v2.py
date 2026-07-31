#!/usr/bin/env python
"""Prospect Score V2 — safe, bounded, idempotent backfill (2026-07-31).

Writes Score V2 results to a SIDECAR audit store (`data/prospect_scores_v2.jsonl`,
keyed by prospect id) — NEVER mutates prospects.jsonl (source preserved →
rollback = restore sidecar backup / re-run with older version). Original scores
and versions are preserved. No contact, no send, read-only on source.

Usage (from repo root, after deploy):
  python scripts/backfill_score_v2.py --dry-run
  python scripts/backfill_score_v2.py --batch-size 500 --limit 2000
  python scripts/backfill_score_v2.py --all
  python scripts/backfill_score_v2.py --rollback <backup-ts>

Properties (mission §5): backup/checkpoint · dry-run · bounded idempotent
batches · changed/skipped/failed counts · rollback · no unbounded full-load
(default line-batched reader, capped by --limit).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.platform.lead_scoring_v2 import SCORE_VERSION, explain_score, score_lead_v2  # noqa: E402

_SIDECAR = Path("data/prospect_scores_v2.jsonl")
_SOURCE = Path("data/prospects.jsonl")
_BACKUP_DIR = Path("data/backups")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_source_rows(limit: int | None) -> list[dict]:
    """Line-batched read (default reads full file, capped by --limit; used only
    for backfill which is a bounded offline op, never a hot read path)."""
    rows = []
    if not _SOURCE.exists():
        return rows
    with open(_SOURCE, encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            if limit is not None and i >= limit:
                break
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows


def _read_sidecar() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not _SIDECAR.exists():
        return out
    with open(_SIDECAR, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.strip():
                try:
                    rec = json.loads(line)
                    out[str(rec.get("prospect_id") or "")] = rec
                except Exception:
                    pass
    return out


def _backup_sidecar() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest = _BACKUP_DIR / f"prospect_scores_v2.bak-{ts}.jsonl"
    if _SIDECAR.exists():
        dest.write_bytes(_SIDECAR.read_bytes())
    return ts


def backfill(*, dry_run: bool, batch_size: int, limit: int | None, only_ready: bool) -> dict:
    rows = _read_source_rows(limit)
    side = _read_sidecar()
    changed = skipped = failed = 0
    batch: list[dict] = []
    started = _now()
    for rec in rows:
        pid = str(rec.get("id") or uuid.uuid4().hex)
        status = str(rec.get("status") or "ready")
        if only_ready and status != "ready":
            skipped += 1
            continue
        existing = side.get(pid)
        if existing and existing.get("score_version") == SCORE_VERSION:
            skipped += 1  # idempotent: same version already scored
            continue
        try:
            s = score_lead_v2(rec)
            expl = explain_score(rec)
            batch.append(
                {
                    "prospect_id": pid,
                    "score_version": SCORE_VERSION,
                    "score": s,
                    "components": expl["components"],
                    "valid_phone": expl["valid_phone"],
                    "reviews_count": expl["reviews_count"],
                    "rating": expl["rating"],
                    "status": status,
                    "niche": str(rec.get("niche") or ""),
                    "city": str(rec.get("city") or ""),
                    "scored_at": _now(),
                }
            )
            changed += 1
        except Exception as e:
            failed += 1
            logger_note = f"score fail {pid}: {e}"
            batch.append(
                {
                    "prospect_id": pid,
                    "score_version": SCORE_VERSION,
                    "score": 0,
                    "components": {},
                    "scored_at": _now(),
                    "error": str(e)[:120],
                }
            )
        if len(batch) >= batch_size and not dry_run:
            with open(_SIDECAR, "a", encoding="utf-8") as f:
                for r in batch:
                    f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
            batch = []
    if batch and not dry_run:
        with open(_SIDECAR, "a", encoding="utf-8") as f:
            for r in batch:
                f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    return {
        "ok": True,
        "dry_run": dry_run,
        "version": SCORE_VERSION,
        "scanned": len(rows),
        "changed": changed,
        "skipped": skipped,
        "failed": failed,
        "only_ready": only_ready,
        "started": started,
        "finished": _now(),
        "sidecar": str(_SIDECAR),
        "note": (
            "source prospects.jsonl UNTOUCHED (sidecar audit store only)"
            if not dry_run
            else "dry-run — kuch bhi write nahi hua"
        ),
    }


def rollback(backup_ts: str) -> dict:
    src = _BACKUP_DIR / f"prospect_scores_v2.bak-{backup_ts}.jsonl"
    if not src.exists():
        return {"ok": False, "error": f"backup nahi mila: {src}"}
    _SIDECAR.write_bytes(src.read_bytes())
    return {
        "ok": True,
        "restored_from": str(src),
        "sidecar": str(_SIDECAR),
        "note": "source prospects.jsonl abhi bhi untouched — rollback sidecar store only",
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Prospect Score V2 backfill (sidecar, safe)")
    p.add_argument("--dry-run", action="store_true", help="compute only, write kuch nahi")
    p.add_argument("--batch-size", type=int, default=500)
    p.add_argument("--limit", type=int, default=None, help="max rows scan (default all)")
    p.add_argument(
        "--all",
        dest="only_ready",
        action="store_false",
        default=True,
        help="saare rows score karo (default sirf status=ready)",
    )
    p.add_argument("--backup", action="store_true", help="pehle sidecar backup banao")
    p.add_argument("--rollback", metavar="TS", help="sidecar ko backup se restore karo")
    args = p.parse_args()

    if args.rollback:
        print(json.dumps(rollback(args.rollback), indent=2))
        return
    backup_ts = _backup_sidecar() if args.backup else None
    res = backfill(
        dry_run=args.dry_run,
        batch_size=args.batch_size,
        limit=args.limit,
        only_ready=args.only_ready,
    )
    if backup_ts:
        res["backup"] = f"prospect_scores_v2.bak-{backup_ts}.jsonl"
    print(json.dumps(res, indent=2, default=str))
    if not args.dry_run:
        print(f"\nBACKFILL DONE {res['finished']} — source UNTOUCHED, sidecar updated.")


if __name__ == "__main__":
    main()
