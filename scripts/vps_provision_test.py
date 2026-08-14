"""VPS smoke: pehle seeded client pe 2-agent provisioning chala ke verify (run on VPS)."""

import asyncio

from sqlalchemy import select

from app.models.base import get_async_session, init_async_db
from app.models.client import Client
from app.platform.agent_provisioner import provision_agents_for_client


async def main() -> None:
    await init_async_db()  # ensures agents.role column exists
    async with get_async_session() as db:
        result = await db.execute(select(Client).limit(1))
        client = result.scalar_one_or_none()
        if not client:
            print("NO CLIENTS IN DB — skipping")
            return
        out = await provision_agents_for_client(db, client)
        print("client:", client.business_name)
        print("niche resolved:", out["niche_key"], "| target:", out["target_type"])
        print("created:", [(a["agent_code"], a["role"]) for a in out["created"]])
        print("existing:", [(a["agent_code"], a["role"]) for a in out["existing"]])
        # idempotency double-check
        out2 = await provision_agents_for_client(db, client)
        print("second run created:", len(out2["created"]), "(expect 0)")


if __name__ == "__main__":
    asyncio.run(main())
