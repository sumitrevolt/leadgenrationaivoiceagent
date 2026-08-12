#!/usr/bin/env python3
"""Flywheel step-2 ops: identity backfill + approve latest Kiran email proposal."""

from __future__ import annotations

import asyncio
import json
import sys


async def main() -> int:
    out: dict = {"steps": []}

    try:
        from app.platform import identity_resolver

        bf = await identity_resolver.backfill_accounts_contacts(200)
        out["steps"].append({"identity_backfill": bf})
    except Exception as e:
        out["steps"].append({"identity_backfill_error": str(e)[:200]})

    try:
        from app.platform import objection_extractor

        scan = await objection_extractor.scan_recent_transcripts(15)
        out["steps"].append({"objection_scan": scan})
    except Exception as e:
        out["steps"].append({"objection_scan_error": str(e)[:200]})

    try:
        from app.agents import campaign_optimizer

        props = campaign_optimizer.recent_proposals(10)
        pending = [p for p in props if p.get("status") != "approve"]
        email = next(
            (p for p in pending if p.get("type") == "email_variant"),
            pending[0] if pending else None,
        )
        if email:
            appr = await campaign_optimizer.approve_proposal(str(email["id"]))
        else:
            appr = "no pending proposals"
        from app.platform import campaign_variants

        variants = await campaign_variants.list_variants("cold_email")
        out["steps"].append({"proposal_approved": appr})
        out["variants"] = variants
    except Exception as e:
        out["steps"].append({"proposal_error": str(e)[:200]})

    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
