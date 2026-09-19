import asyncio

from app.utils.telegram_egress import send_to_group

msg = """LeadGen Admin — Final Status Sep 19

Production: v89ab2f29 HEALTHY (41 containers)
CI: GREEN

P0/P1 FIXES DEPLOYED:
✅ auto_outreach restored (450 pending sendable)
✅ TypeSafe System One API (jev-latest)
✅ Telegram YAML fix (working)
✅ VOBIZ dead credentials removed
✅ CI baseline regenerated
✅ Backup cron added (nightly)
✅ DLQ cleared
✅ All PRs closed, branches deleted

REVENUE:
- SmartFlo: active (sole provider)
- Subs: 2 active (Oct 22)
- Payments: ₹3,998 in system (test)

OWNER ACTIONS:
1. Paste TypeSafe API key in .env
2. Configure Razorpay/Stripe live keys"""


async def main():
    result = await send_to_group("owner_alerts", msg)
    print(result)


asyncio.run(main())
