import asyncio
from app.models.base import get_async_session
from app.models.lead import Lead
from sqlalchemy import func, select

async def main():
    async with get_async_session() as db:
        result = await db.execute(select(func.count()).select_from(Lead))
        print(f"Leads count: {result.scalar()}")

asyncio.run(main())
