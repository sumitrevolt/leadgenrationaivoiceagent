"""One-time purge: SERP-junk prospects ko "ready" pool se nikalo (backlog 2026-07-05).

KYU: lead_harvester ka websearch source SERP page-titles ko business_name aur page
ke kisi bhi 10-digit ko phone bana deta tha — ~94 junk records (bank helplines,
"Top 10 ..." listicles) "ready" pool me the = platform_dial IVR-disaster ka
root-enabler. Ingest gate (HARVEST_INGEST_VALIDATION) ab naya junk rokta hai;
yeh script PURANA junk saaf karta hai.

Kya karta hai:
  - data/prospects.jsonl padho, har record par wahi `ingest_reject_reason` lagao
    jo ab ingest par lagta hai (single source of truth = lead_harvester).
  - DEFAULT = DRY-RUN: sirf table print (kuch nahi likhta).
  - --apply: pehle backup (prospects.jsonl.bak-<ts>), phir matched records ko
    status="dead" + junk_reason set karke ATOMIC rewrite (tmp + os.replace —
    prospector.mark_prospect ka pattern). DELETE nahi karta (audit trail).
  - --niche <key>: us niche ke SAARE "ready" records bhi include (e.g.
    home_loans jo mostly garbage tha).

DB mirror note: jsonl = source of truth. Relational `leads` table / niche_database
call-queue me mirrors reh sakte hain — script end me dead-marked phones ki list
print karta hai taaki zaroorat ho to alag se saaf karo (yahan DB touch NAHI hota).

Run (local):    python scripts/purge_junk_prospects.py
Run (VPS):      docker compose -f docker-compose.vps.yml exec app \
                    python scripts/purge_junk_prospects.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

# Repo root importable banao (script direct run hota hai)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.platform.lead_harvester import ingest_reject_reason  # noqa: E402

_PROSPECTS_FILE = os.path.join("data", "prospects.jsonl")


def _phone10(raw: str) -> str:
    d = re.sub(r"\D", "", str(raw or ""))
    if d.startswith("91") and len(d) == 12:
        d = d[2:]
    elif d.startswith("0") and len(d) == 11:
        d = d[1:]
    return d if len(d) == 10 and d[:1] in "6789" else ""


def _source_of(rec: dict) -> str:
    # harvester records: source_query = "harvest:<source>"; prospector records me nahi
    sq = str(rec.get("source_query") or "")
    if sq.startswith("harvest:"):
        return sq.split(":", 1)[1]
    return str(rec.get("source") or "")


def _load() -> list[dict]:
    rows: list[dict] = []
    if not os.path.isfile(_PROSPECTS_FILE):
        return rows
    with open(_PROSPECTS_FILE, encoding="utf-8") as f:
        for ln in f:
            try:
                rec = json.loads(ln)
                if isinstance(rec, dict):
                    rows.append(rec)
            except Exception:
                continue
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Purge SERP-junk prospects (default dry-run)")
    ap.add_argument("--apply", action="store_true", help="actually mark matched records dead")
    ap.add_argument(
        "--niche",
        default="",
        help="is niche ke SAARE ready records bhi dead karo (e.g. home_loans)",
    )
    args = ap.parse_args()

    rows = _load()
    if not rows:
        print(f"{_PROSPECTS_FILE} empty/missing — kuch nahi karna.")
        return 0

    matched: list[tuple[dict, str]] = []
    for r in rows:
        status = str(r.get("status") or "ready")
        if status == "dead":
            continue
        name = str(r.get("business_name") or "")
        p10 = _phone10(r.get("phone"))
        email = str(r.get("email") or "").strip()
        src = _source_of(r)
        reason = ingest_reject_reason(name, p10, email, src)
        if not reason and args.niche and status == "ready" and r.get("niche") == args.niche:
            reason = f"niche_purge:{args.niche}"
        if reason:
            matched.append((r, reason))

    print(f"Total records: {len(rows)} | junk matched: {len(matched)}")
    for r, reason in matched:
        print(
            f"  [{reason:22s}] {str(r.get('business_name') or '')[:58]!r} "
            f"phone={r.get('phone') or '-'} niche={r.get('niche')} status={r.get('status')}"
        )

    if not matched:
        return 0
    if not args.apply:
        print("\nDRY-RUN tha — kuch nahi likha. Apply karne ke liye: --apply")
        return 0

    # Backup, phir atomic rewrite (prospector.mark_prospect pattern)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    bak = f"{_PROSPECTS_FILE}.bak-{ts}"
    with open(_PROSPECTS_FILE, encoding="utf-8") as fsrc, open(bak, "w", encoding="utf-8") as fdst:
        fdst.write(fsrc.read())
    print(f"Backup: {bak}")

    matched_ids = {r.get("id"): reason for r, reason in matched}
    now = datetime.now(timezone.utc).isoformat()
    dead_phones: list[str] = []
    for r in rows:
        reason = matched_ids.get(r.get("id"))
        if reason:
            r["status"] = "dead"
            r["junk_reason"] = reason
            r["status_at"] = now
            r["updated_at"] = now
            p = _phone10(r.get("phone"))
            if p:
                dead_phones.append(p)
    tmp = _PROSPECTS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    os.replace(tmp, _PROSPECTS_FILE)
    print(f"DONE: {len(matched)} records -> status=dead (delete NAHI kiya — audit trail).")
    if dead_phones:
        print("DB-mirror cleanup reference (dead phones):")
        print("  " + ",".join(sorted(set(dead_phones))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
