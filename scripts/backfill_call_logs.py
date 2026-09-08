#!/usr/bin/env python3
"""Backfill the structured `call_logs` table from historical JSONL.

Voice calls have always written flat JSONL (data/call_transcripts/*.jsonl +
data/call_qualifications.jsonl). The DB-backed analytics dashboard reads the
`call_logs` table, which was never populated. This one-time, idempotent script
joins both JSONL sources on call_id and INSERTs a CallLog per historical call so
the dashboard shows history immediately.

Idempotent: skips any call whose call_sid already has a row. Safe to re-run.

Usage (repo root):  python scripts/backfill_call_logs.py
"""

from __future__ import annotations

import glob
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Force the writer on for the backfill regardless of the live env setting.
os.environ.setdefault("CALL_LOG_DB", "1")
os.environ["CALL_LOG_DB"] = "1"


def _parse_dt(val) -> datetime | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(str(val))
    except Exception:
        return None


def _iter_jsonl(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue
    except FileNotFoundError:
        return


def main() -> int:
    from app.models.base import get_db_session
    from app.models.call_log import CallLog
    from app.telephony.post_call_hooks import build_call_log, classify_stream_outcome

    data_dir = ROOT / "data"

    # 1) Index qualifications by call_id (last write wins).
    quals: dict[str, dict] = {}
    for rec in _iter_jsonl(str(data_dir / "call_qualifications.jsonl")):
        cid = str(rec.get("call_id") or "").strip()
        if cid:
            quals[cid] = rec

    inserted = skipped = 0
    seen: set[str] = set()

    transcript_files = sorted(glob.glob(str(data_dir / "call_transcripts" / "*.jsonl")))
    for tf in transcript_files:
        for rec in _iter_jsonl(tf):
            call_id = str(rec.get("call_sid") or rec.get("stream_sid") or "").strip()
            if not call_id or call_id in seen:
                continue
            seen.add(call_id)

            q = quals.get(call_id)
            phone = ""
            if q:
                phone = str(q.get("lead_id") or q.get("raw_phone") or "").strip()

            turns = int(rec.get("user_turns") or 0)
            dur = float(rec.get("duration_s") or 0.0)
            outcome = classify_stream_outcome(
                user_turns=turns, turn_metrics=rec.get("turn_metrics")
            )
            row = build_call_log(
                call_id=call_id,
                provider=str(rec.get("provider") or "vobiz"),
                phone=phone,
                client_id=str(rec.get("client_id") or ""),
                client_name=str(rec.get("client_name") or ""),
                niche=str(rec.get("niche") or ""),
                duration_s=dur,
                user_turns=turns,
                outcome=outcome,
                started_at=_parse_dt(rec.get("started_at")),
                ended_at=_parse_dt(rec.get("ts")) or datetime.now(timezone.utc),
                q=q,
            )
            if row is None:
                continue

            try:
                with get_db_session() as db:
                    if db.query(CallLog.id).filter(CallLog.call_sid == call_id).first():
                        skipped += 1
                        continue
                    # FK-safe client link (mirror persist_call_log).
                    cid = str(rec.get("client_id") or "").strip()
                    if cid:
                        try:
                            from app.models.client import Client

                            if db.get(Client, cid) is not None:
                                row.client_id = cid
                        except Exception:
                            pass
                    db.add(row)
                inserted += 1
            except Exception as e:  # noqa: BLE001 — best-effort backfill
                print(f"  skip {call_id}: {e}")
                skipped += 1

    print(
        f"backfill_call_logs: inserted={inserted} skipped={skipped} "
        f"(scanned {len(seen)} calls across {len(transcript_files)} files)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
