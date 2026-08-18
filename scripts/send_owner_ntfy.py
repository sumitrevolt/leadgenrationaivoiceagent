import asyncio

from app.integrations import ntfy


async def send_owner_prep():
    print("ntfy enabled?", ntfy.enabled())
    body = (
        "Morning WS-1 Prep Pack\n\n"
        "1. Hot Queue Blitz (15m): Login > Inbox > 5 verified hot cards > Call/1-click WA\n"
        "2. UPI Bind Path: Admin tab > Payment setup > bind your real VPA\n"
        "3. Bank Confirm: Clear the 1 pending approved unbound queue item for 1st paid!\n"
    )
    ok = await ntfy.push("🔥 Today's Owner Gates Ready", body, priority="high")
    print("Push ok?", ok)


if __name__ == "__main__":
    asyncio.run(send_owner_prep())
