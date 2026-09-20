#!/usr/bin/env python3
"""
LeadGen AI — Jarvis Bot Ingress Runner (Local & VPS)
===================================================
Runs long-polling loop for Jarvis Bot (@Sumits_jarvis_bot) with:
- Intent classification & routing across 9 Hermes supervisory bots
- TypeSafe System One (jev-latest) semantic intelligence
- Skill execution via app.agents.skills
- Coordination with Notify Bot (@Leadsgenai1_bot)
- Zero 409 conflict guarantee (Notify bot has polling permanently disabled)
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load environment from .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from app.platform.telegram_coordinator import (
    get_dual_bot_status,
    get_polling_token,
    run_jarvis_polling,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("jarvis_runner")


def main() -> int:
    parser = argparse.ArgumentParser(description="LeadGen AI Jarvis Ingress Bot Runner")
    parser.add_argument("--timeout", type=int, default=25, help="getUpdates long-polling timeout in seconds")
    parser.add_argument("--status-only", action="store_true", help="Print dual-bot status and exit")
    args = parser.parse_args()

    status = get_dual_bot_status()
    print("=" * 60)
    print("LEADGEN AI — TELEGRAM DUAL-BOT COORDINATOR")
    print("=" * 60)
    print(f"Jarvis Ingress Bot:  {status['jarvis']['username']} (Configured: {status['jarvis']['token_configured']})")
    print(f"Notify Egress Bot:   {status['notify']['username']} (Configured: {status['notify']['token_configured']})")
    print(f"Authorized Owners:   {status['owners']['chat_ids']}")
    print("=" * 60)

    if args.status_only:
        return 0 if status["configured"] else 1

    token = get_polling_token()
    if not token:
        logger.error("TELEGRAM_JARVIS_BOT_TOKEN is not configured in environment or .env!")
        return 1

    logger.info("Starting Jarvis Bot interactive listener...")
    try:
        run_jarvis_polling(poll_timeout=args.timeout)
    except KeyboardInterrupt:
        logger.info("Jarvis Bot stopped by owner (SIGINT).")
    except Exception as e:
        logger.exception("Jarvis Bot encountered an error: %s", e)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
