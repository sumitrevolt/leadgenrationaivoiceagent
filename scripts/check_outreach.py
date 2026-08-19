import asyncio
import logging

from app.platform.auto_outreach import hot_queue_candidates, run_email_outreach

logging.basicConfig(level=logging.INFO)


async def check_outreach():
    print("--- Hot Queue Candidates ---")
    cands = hot_queue_candidates(limit=5)
    print("Hot Queue Candidates:", len(cands))

    print("\n--- Outreach Sends ---")
    outreach = await run_email_outreach(limit=5)
    print("Outreach:", outreach)


if __name__ == "__main__":
    asyncio.run(check_outreach())
