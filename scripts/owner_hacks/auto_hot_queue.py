import asyncio
import os

from app.api import growth
from app.platform import reply_agent


async def process_hq():
    while True:
        cards = reply_agent.hot_queue(limit=50, scope="boss")
        if not cards:
            break
        for c in cards:
            hq_id = c.get("hq_id")
            print(f"Processing {hq_id}...")
            try:
                await growth.reply_hot_queue_council_decide(
                    body=growth.HotQueueCouncilIn(hq_id=hq_id, apply=True),
                    _user=None,  # Needs bypass for script
                )
            except Exception as e:
                print(f"Error processing {hq_id}: {e}")
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(process_hq())
