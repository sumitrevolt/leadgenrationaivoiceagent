import asyncio
from app.models.base import init_async_db

async def main():
    await init_async_db()
    print("Database tables initialized successfully.")

asyncio.run(main())
