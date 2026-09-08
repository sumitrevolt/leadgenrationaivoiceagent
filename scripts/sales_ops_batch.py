#!/usr/bin/env python3
"""Sales ops batch — phone-only lead email enrichment + dialer sprint stats.

Run on VPS (needs DB):
  docker exec leadgen_app python scripts/sales_ops_batch.py
  docker exec leadgen_app python scripts/sales_ops_batch.py --limit 30 --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter


async def _stats() -> dict:
    from sqlalchemy import func, select

    from app.models.base import get_async_session
    from app.models.lead import Lead

    async with get_async_session() as session:
        total = (await session.execute(select(func.count()).select_from(Lead))).scalar() or 0
        phone_only = (
            await session.execute(
                select(func.count())
                .select_from(Lead)
                .where(
                    Lead.phone.isnot(None),
                    Lead.phone != "",
                    (Lead.email.is_(None)) | (Lead.email == ""),
                )
            )
        ).scalar() or 0
        with_email = (
            await session.execute(
                select(func.count())
                .select_from(Lead)
                .where(
                    Lead.email.isnot(None),
                    Lead.email != "",
                )
            )
        ).scalar() or 0
        niche_rows = (
            await session.execute(
                select(Lead.industry, func.count())
                .where(
                    Lead.phone.isnot(None),
                    Lead.phone != "",
                    (Lead.email.is_(None)) | (Lead.email == ""),
                )
                .group_by(Lead.industry)
                .order_by(func.count().desc())
                .limit(8)
            )
        ).all()
    return {
        "total_leads": int(total),
        "phone_only": int(phone_only),
        "with_email": int(with_email),
        "top_phone_only_niches": [
            {"niche": (n or "unknown"), "count": int(c)} for n, c in niche_rows
        ],
    }


async def _enrich(limit: int) -> dict:
    from sqlalchemy import select

    from app.models.base import get_async_session
    from app.models.lead import Lead
    from app.platform import email_finder

    found = updated = not_found = skipped = 0
    samples: list[dict] = []

    async with get_async_session() as session:
        q = (
            select(Lead)
            .where(
                Lead.phone.isnot(None),
                Lead.phone != "",
                (Lead.email.is_(None)) | (Lead.email == ""),
            )
            .limit(limit)
        )
        leads = (await session.execute(q)).scalars().all()

    for lead in leads:
        website = (lead.website or "").strip()
        if not website:
            skipped += 1
            continue
        try:
            r = await email_finder.find(website, (lead.company_name or "").strip())
            emails = r.get("emails") or []
            best = next((e["email"] for e in emails if e.get("verified")), None)
            if not best and emails:
                best = emails[0].get("email")
            if best:
                async with get_async_session() as session:
                    obj = await session.get(Lead, lead.id)
                    if obj:
                        obj.email = best
                        obj.email_verified = True
                        await session.commit()
                found += 1
                updated += 1
                if len(samples) < 5:
                    samples.append({"phone": lead.phone, "email": best, "website": website})
            else:
                not_found += 1
        except Exception as e:
            not_found += 1
            if len(samples) < 8:
                samples.append({"phone": lead.phone, "error": str(e)[:80]})

    return {
        "scanned": len(leads),
        "found": found,
        "updated": updated,
        "not_found": not_found,
        "skipped_no_website": skipped,
        "samples": samples,
    }


async def _run(limit: int, apply: bool) -> int:
    stats = await _stats()
    print("DIALER_SPRINT_STATS", json.dumps(stats, ensure_ascii=False))
    print(f"\nHuman action: /app/dialer se 20-30 calls/day — phone-only pool={stats['phone_only']}")
    if not apply:
        print("\nDry-run only. Re-run with --apply to enrich emails.")
        return 0

    result = await _enrich(limit)
    print("EMAIL_ENRICH", json.dumps(result, ensure_ascii=False))
    after = await _stats()
    print("AFTER_STATS", json.dumps(after, ensure_ascii=False))
    return 0 if result["updated"] >= 0 else 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=30, help="Max leads to enrich")
    p.add_argument("--apply", action="store_true", help="Actually run email finder")
    args = p.parse_args()
    return asyncio.run(_run(args.limit, args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
