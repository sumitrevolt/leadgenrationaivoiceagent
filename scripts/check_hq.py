import asyncio
import json

from app.platform.office_hq import build_snapshot, next_best_actions


async def fetch():
    snap = await build_snapshot()
    if isinstance(snap.get("pipeline"), list):
        pipeline = snap.get("pipeline", [])
    else:
        pipeline = snap.get("pipeline", {}).get("recent_items", [])

    print("=== Hot Queue Approvals ===")
    approvals = snap.get("approvals", {}).get("items", [])
    for item in approvals[:5]:
        print(f"- {item.get('id')}: {item.get('title')} ({item.get('source')})")

    # Let's get Hot Queue top-5 from next_best_actions
    nbas = next_best_actions(snap)[:5]
    print("\n=== Top 5 Next Best Actions (Hot Queue) ===")
    for n in nbas:
        print(f"[{n.get('type')}] {n.get('severity')} - {n.get('title')} - {n.get('action_txt')}")


if __name__ == "__main__":
    asyncio.run(fetch())
