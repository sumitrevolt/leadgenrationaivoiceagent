"""Smoke — self-improve loop + skill library + naye social channels (VPS pe docker exec se).

Run: docker exec leadgen_worker python scripts/smoke_self_improve.py
(worker container me — web event-loop touch nahi hota.)
"""

from __future__ import annotations

import asyncio
import json


def main() -> None:
    from app.agents import self_improve
    from app.platform import skill_library

    print(
        "ENABLED",
        self_improve.enabled(),
        "| gap",
        self_improve.gap_seconds(),
        "| cap",
        self_improve.max_per_day(),
    )

    st = self_improve.status()
    print(
        "STATUS",
        json.dumps({k: st.get(k) for k in ("enabled", "queue_pending")}, ensure_ascii=False),
    )
    print("STATE", json.dumps(st.get("state") or {}, ensure_ascii=False))

    # ek inline iteration (smoke) — pick→execute→learn
    res = asyncio.run(self_improve.run_once())
    print(
        "RUN_ONCE",
        json.dumps(
            {k: res.get(k) for k in ("enabled", "ok", "action", "source", "detail", "skipped")},
            ensure_ascii=False,
        ),
    )

    summ = skill_library.summary()
    print("SKILLS tracked:", summ.get("skills_tracked"), "uses:", summ.get("total_uses"))
    for b in (summ.get("best") or [])[:3]:
        print("  best:", b.get("skill"), b.get("rate"), f"({b.get('uses')} uses)")
    for les in (summ.get("recent_lessons") or [])[:2]:
        print("  lesson:", str(les.get("lesson"))[:100])

    # naya channel draft (fallback-safe)
    from app.marketing import social_channels

    d = asyncio.run(social_channels.draft("youtube_shorts", "solar", "Pune"))
    print("SOCIAL_DRAFT ok:", d.get("ok"), "|", str(d.get("draft"))[:90].replace("\n", " "))

    from app.marketing import channel_experiments

    print("BANDIT channels:", len(channel_experiments.CHANNELS))
    print("SMOKE_PASS")


if __name__ == "__main__":
    main()
