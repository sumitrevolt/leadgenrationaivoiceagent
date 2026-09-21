#!/usr/bin/env python3
"""
LeadGen AI -- Jarvis Bot Ingress Runner (Local & VPS)
===================================================
Runs the long-polling loop for Jarvis Bot (@Sumits_jarvis_bot) with:
- Single-consumer coordination (lease + ``TELEGRAM_INGRESS_OWNER`` gate)
- HTTP 409 standby/backoff when an external consumer (Hermes gateway) holds the token
- Live token validation before polling (a revoked token never spins in a 401 loop)
- Intent classification & routing across the 9 supervisory bots
- TypeSafe System One semantics + skill execution via app.agents.skills
- Zero 409 conflict guarantee against the Notify bot (polling permanently disabled)

Coordination knobs (see docs/TELEGRAM_DUAL_BOT_SETUP.md):
  TELEGRAM_INGRESS_OWNER=auto|local|vps|hermes|off   # who may poll
  TELEGRAM_INSTANCE_ROLE=local|vps                   # what THIS process is
  TELEGRAM_INSTANCE_ID=<name>                        # stable id (default host:pid)
  TELEGRAM_POLL_LEASE_TTL=120                        # seconds
"""

from __future__ import annotations

import argparse
import logging
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

from app.platform.telegram_coordinator import (  # noqa: E402
    get_dual_bot_status,
    get_instance_id,
    get_polling_token,
    ingress_owner_role,
    instance_role,
    run_jarvis_polling,
    validate_bot_token,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("jarvis_runner")


def _print_status(live_probe: bool, instance: str, role: str) -> bool:
    """Print the dual-bot truth table. Returns True when polling is possible."""
    status = get_dual_bot_status(live_probe=live_probe)
    ingress = status["ingress"]
    jarvis = status["jarvis"]

    print("=" * 66)
    print("LEADGEN AI -- TELEGRAM DUAL-BOT COORDINATOR")
    print("=" * 66)
    print(f"Jarvis Ingress Bot : {jarvis['username']}  configured={jarvis['token_configured']}")
    if live_probe:
        print(f"                     token_valid={jarvis['token_valid']}")
    print(f"Notify Egress Bot  : {status['notify']['username']}  configured={status['notify']['token_configured']}")
    print(f"Authorized Owners  : {status['owners']['chat_ids']}")
    print(f"Ingress Owner Role : {ingress['owner_role']}")
    print(f"This Instance      : {instance} (role={role})")
    lease = ingress["lease"]
    print(
        f"Polling Lease      : holder={lease.get('holder')} backend={lease.get('backend')} "
        f"held_by_me={lease.get('held_by_me')} remaining={lease.get('seconds_remaining')}"
    )
    print(f"May Poll Now       : {ingress['may_poll_now']}")
    heartbeat = ingress.get("heartbeat") or {}
    age = ingress.get("heartbeat_age_s")
    if heartbeat:
        print(
            f"Loop Heartbeat     : state={heartbeat.get('state')} age={round(age, 1) if age is not None else None}s "
            f"polls={heartbeat.get('polls')} updates={heartbeat.get('updates_total')} "
            f"at={heartbeat.get('at_iso')} pid={heartbeat.get('pid')}"
        )
    else:
        print("Loop Heartbeat     : (none — this process has never completed a poll round)")
    conflicts = ingress["conflicts"]
    print(
        f"409 Conflicts      : count={conflicts.get('conflict_count')} "
        f"last={conflicts.get('last_conflict_at')} retry_in={conflicts.get('retry_in_s')}"
    )
    if live_probe:
        for slot, info in (status.get("tokens") or {}).items():
            print(
                f"Token Slot [{slot:<8}] present={info.get('present')} valid={info.get('valid')} "
                f"reason={info.get('reason')} {info.get('username') or ''}"
            )
    print("=" * 66)

    if not jarvis["token_configured"]:
        logger.error("TELEGRAM_JARVIS_BOT_TOKEN is not configured in environment or .env!")
        return False
    if live_probe and not jarvis.get("token_valid"):
        logger.error("Jarvis token is present but INVALID -- refusing to poll (fix the credential).")
        return False
    return True


def _sigterm_to_interrupt(signum: int, frame: object) -> None:  # noqa: ARG001
    """Docker stop / systemd stop send SIGTERM.

    Python's default SIGTERM handler terminates the process immediately, which
    would skip ``run_jarvis_polling``'s ``finally`` and leave the polling lease
    held until its TTL expires. Raising the same thing Ctrl-C raises keeps the
    release path identical for both.
    """
    raise KeyboardInterrupt


def main() -> int:
    parser = argparse.ArgumentParser(description="LeadGen AI Jarvis Ingress Bot Runner")
    parser.add_argument("--timeout", type=int, default=25, help="getUpdates long-polling timeout in seconds")
    parser.add_argument("--status-only", action="store_true", help="Print dual-bot status and exit")
    parser.add_argument("--probe", action="store_true", help="Also validate tokens live (getMe, no secrets printed)")
    parser.add_argument("--instance", default=None, help="Stable instance id (default host:pid)")
    parser.add_argument("--role", default=None, help="Instance role: local | vps | hermes")
    parser.add_argument(
        "--max-standby-rounds",
        type=int,
        default=240,
        help="How many standby rounds before exiting so a supervisor can retry",
    )
    args = parser.parse_args()

    instance = get_instance_id(args.instance)
    role = instance_role(args.role)

    if not _print_status(live_probe=args.probe, instance=instance, role=role):
        return 1

    if args.status_only:
        return 0

    poller = get_polling_token()
    if not poller:
        logger.error("TELEGRAM_JARVIS_BOT_TOKEN is not configured in environment or .env!")
        return 1

    try:
        import signal

        signal.signal(signal.SIGTERM, _sigterm_to_interrupt)
    except Exception as exc:  # pragma: no cover - platform quirk
        logger.debug("SIGTERM handler not installed: %s", exc)

    logger.info(
        "Starting Jarvis Bot interactive listener (instance=%s role=%s owner=%s)...",
        instance,
        role,
        ingress_owner_role(),
    )
    try:
        run_jarvis_polling(
            poll_timeout=args.timeout,
            instance_id=instance,
            role=role,
            max_standby_rounds=args.max_standby_rounds,
        )
    except KeyboardInterrupt:
        logger.info("Jarvis Bot stopped by owner (SIGINT).")
    except Exception as e:
        logger.exception("Jarvis Bot encountered an error: %s", e)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
