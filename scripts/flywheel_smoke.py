#!/usr/bin/env python3
"""Flywheel health smoke — status, variants, objections, attribution."""

from __future__ import annotations

import asyncio
import json
import os
import sys


async def main() -> int:
    out: dict = {}
    try:
        from app.agents import campaign_optimizer

        out["kiran"] = campaign_optimizer.status()
    except Exception as e:
        out["kiran_error"] = str(e)[:120]

    try:
        from app.platform import campaign_variants

        out["variants"] = await campaign_variants.promotion_summary("cold_email")
        out["voice_variants"] = await campaign_variants.promotion_summary("voice_opening")
        out["voice_flag"] = os.environ.get("VOICE_CAMPAIGN_VARIANTS", "0")
    except Exception as e:
        out["variants_error"] = str(e)[:120]

    try:
        from app.platform import objection_extractor

        out["objections_recent"] = len(objection_extractor.recent_patterns(5))
    except Exception as e:
        out["objections_error"] = str(e)[:120]

    try:
        from app.platform import revenue_attribution

        out["attribution"] = revenue_attribution.summary(50)
    except Exception as e:
        out["attribution_error"] = str(e)[:120]

    ok = "kiran" in out and out.get("variants", {}).get("variants") is not None
    out["ok"] = ok
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
