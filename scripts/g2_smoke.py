"""Godmode-2 VPS smoke — public audit funnel + content pack + retention wiring."""

import asyncio


async def main() -> None:
    from app.marketing.content_pack import build_client_pack
    from app.marketing.gbp_audit import AUDIT_QUESTIONS, score_audit

    r = score_audit({q["id"]: len(q["options"]) - 1 for q in AUDIT_QUESTIONS})
    print("AUDIT-LOGIC:", r.get("score"), r.get("grade"), len(r.get("top_fixes") or []))

    pack = await build_client_pack("Sharma Solar", "solar_residential", offer="20% off")
    html = pack.get("html") or ""
    print("PACK:", "Sharma Solar" in html, len(html) > 3000, pack.get("counts"))

    from app.agents.staff import run_ops

    ops = await run_ops()
    print("OPS:", ops.get("status"), "pruned" in str(ops).lower() or "prune" in str(ops).lower())


if __name__ == "__main__":
    asyncio.run(main())
