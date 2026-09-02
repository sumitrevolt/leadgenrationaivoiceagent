"""One-time backfill: existing prospects par phone_type tag + FIXED_LINE dial_block (ADR-027).

KYU (council 2026-07-06): store me 649 FIXED_LINE cloud-IVR DIDs (Livspace/HDFC
DID-blocks) "ready" the — 05-Jul batch ne unhe dial kiya (IVR paisa-burn). Naye
records ab ingest par `phone_type` ke saath likhe jaate hain (prospector) aur
dial_gate FIXED_LINE promotional-dial block karta hai; yeh script PURANE rows
ko wahi tag deta hai taaki dashboards/email-routing/audit sab consistent ho.

Kya karta hai:
  - data/prospects.jsonl padho, har record ke phone par dial_gate.phone_quality
    lagao (single source of truth — wahi jo dial-time par lagta hai).
  - DEFAULT = DRY-RUN: sirf type-distribution table print (kuch nahi likhta).
  - --apply: pehle backup (prospects.jsonl.bak-<ts>), phir har record par
    `phone_type` set + fixed/tollfree walo par `dial_block="fixed_line_type"`
    ATOMIC rewrite (tmp + os.replace). STATUS NAHI badalta — email path zinda
    rehta (council: route, don't shrink). DELETE nahi karta (audit trail).

Run (local):    python scripts/backfill_phone_type.py
Run (VPS):      docker compose -f docker-compose.vps.yml exec app \
                    python scripts/backfill_phone_type.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone

# Repo root importable banao (script direct run hota hai)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.telephony.dial_gate import phone_quality  # noqa: E402

_PROSPECTS_FILE = os.path.join("data", "prospects.jsonl")
_DIAL_BLOCK_TYPES = ("fixed", "tollfree")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="likho (default: dry-run)")
    ap.add_argument("--file", default=_PROSPECTS_FILE)
    args = ap.parse_args()

    if not os.path.isfile(args.file):
        print(f"[backfill] file nahi mili: {args.file}")
        return 1

    rows: list[dict] = []
    with open(args.file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue

    dist: Counter[str] = Counter()
    changed = 0
    blocked = 0
    for r in rows:
        digits = "".join(c for c in str(r.get("phone") or "") if c.isdigit())[-10:]
        q = phone_quality(digits) if len(digits) == 10 else ""
        dist[q or "NO_PHONE"] += 1
        if r.get("phone_type") != q:
            r["phone_type"] = q
            changed += 1
        if q in _DIAL_BLOCK_TYPES and not r.get("dial_block"):
            r["dial_block"] = "fixed_line_type"
            r["dial_block_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            blocked += 1

    print(f"[backfill] rows={len(rows)} | type distribution: {dict(dist)}")
    print(f"[backfill] phone_type set/updated: {changed} | naya dial_block: {blocked}")

    if not args.apply:
        print("[backfill] DRY-RUN — kuch nahi likha. Apply: --apply")
        return 0

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    bak = f"{args.file}.bak-{ts}"
    shutil.copyfile(args.file, bak)
    tmp = args.file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, args.file)
    print(f"[backfill] APPLIED (backup: {bak})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
