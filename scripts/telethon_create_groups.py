#!/usr/bin/env python3
"""Create 3 missing Telegram enterprise groups using Telethon (user API).

Non-interactive, two-phase auth for agent execution.

Usage:
  # Phase 1: Send SMS code
  .venv/Scripts/python.exe scripts/telethon_create_groups.py --api-id ID --api-hash HASH --phone +91XXX

  # Phase 2: Verify code + create groups
  .venv/Scripts/python.exe scripts/telethon_create_groups.py --api-id ID --api-hash HASH --phone +91XXX --code 12345

  # Just create (if session already authed)
  .venv/Scripts/python.exe scripts/telethon_create_groups.py --api-id ID --api-hash HASH --phone +91XXX --create

  # Dry run
  .venv/Scripts/python.exe scripts/telethon_create_groups.py --api-id ID --api-hash HASH --phone +91XXX --create --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Force UTF-8 on stdout/stderr for Windows console
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from telethon import TelegramClient
from telethon.tl.types import ChatAdminRights
from telethon.tl.functions.channels import CreateChannelRequest, InviteToChannelRequest, EditAdminRequest

BOT_USERNAME = "Leadsgenai1_bot"

GROUPS = [
    {
        "name": "LeadGen AI - Worker Coordination",
        "spec_key": "workers_coordination",
        "description": (
            "Cross-worker coordination, task handoffs, status updates between the 9 worker CLI agents.\n"
            "Audience: Worker agents + founder + PM\n"
            "Access: private"
        ),
    },
    {
        "name": "LeadGen AI - Agents Coordination",
        "spec_key": "agents_coordination",
        "description": (
            "31-agent coordination, Boss verdict, hierarchical runs, skill sharing, agent health.\n"
            "Audience: Agent operators + founder\n"
            "Access: private"
        ),
    },
    {
        "name": "LeadGen AI - Admin Command Center",
        "spec_key": "admin_command_center",
        "description": (
            "Owner/admin operational commands, deployment notices, kill-switch status, revenue truth, system health.\n"
            "Audience: Founder + devops + PM\n"
            "Access: private"
        ),
    },
]

SESSION_PATH = REPO_ROOT / "data" / "telethon_setup.session"
CODE_HASH_PATH = REPO_ROOT / "data" / "telethon_code_hash.json"


async def do_auth(api_id: int, api_hash: str, phone: str, code: str | None):
    """Authenticate: send SMS if no code, verify + create if code provided."""
    client = TelegramClient(str(SESSION_PATH), api_id, api_hash)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"[OK] Already authenticated as: {me.first_name} ({me.phone})")
        await client.disconnect()
        return True

    if code:
        # Load saved phone_code_hash
        phone_code_hash = None
        if CODE_HASH_PATH.exists():
            data = json.loads(CODE_HASH_PATH.read_text())
            phone_code_hash = data.get("phone_code_hash")

        if not phone_code_hash:
            print("[ERROR] No phone_code_hash found. Run without --code first to send SMS.")
            await client.disconnect()
            return False

        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
            me = await client.get_me()
            print(f"[OK] Authenticated as: {me.first_name} ({me.phone})")
            # Clean up code hash
            CODE_HASH_PATH.unlink(missing_ok=True)
        except Exception as e:
            print(f"[FAIL] Code verification error: {e}")
            await client.disconnect()
            return False
    else:
        # Send code request
        try:
            result = await client.send_code_request(phone)
            # Save phone_code_hash for next step
            CODE_HASH_PATH.parent.mkdir(parents=True, exist_ok=True)
            CODE_HASH_PATH.write_text(json.dumps({"phone_code_hash": result.phone_code_hash}))
            print(f"[OK] SMS code sent to {phone}")
            print(f"[INFO] phone_code_hash saved to {CODE_HASH_PATH}")
            print(f"[NEXT] Run again with --code <SMS_CODE>")
        except Exception as e:
            print(f"[FAIL] Send code error: {e}")
            await client.disconnect()
            return False

    await client.disconnect()
    return True


async def do_create(api_id: int, api_hash: str, phone: str, dry_run: bool = False):
    """Create 3 groups, add bot as admin, return chat_ids."""
    client = TelegramClient(str(SESSION_PATH), api_id, api_hash)
    await client.start(phone=phone)

    me = await client.get_me()
    print(f"[telethon] Logged in as: {me.first_name} ({me.phone})\n")

    results: dict[str, str] = {}

    for g in GROUPS:
        print(f"--- Creating: {g['name']} ---")

        if dry_run:
            print(f"  [DRY RUN] Would create supergroup '{g['name']}'")
            results[g["spec_key"]] = "DRY_RUN"
            continue

        try:
            result = await client(CreateChannelRequest(
                title=g["name"],
                about=g["description"][:255],
                megagroup=True,
            ))
            entity = result.chats[0]
            print(f"  [OK] Created: {entity.title}")

            # Add bot as admin
            bot_entity = await client.get_entity(BOT_USERNAME)
            await client(InviteToChannelRequest(channel=entity, users=[bot_entity]))
            print(f"  [OK] Added @{BOT_USERNAME}")

            admin_rights = ChatAdminRights(
                change_info=True, delete_messages=True, ban_users=True,
                invite_users=True, pin_messages=True, manage_call=True, other=True,
            )
            await client(EditAdminRequest(
                channel=entity, user_id=bot_entity,
                admin_rights=admin_rights, rank="Bot Admin",
            ))
            print(f"  [OK] Made @{BOT_USERNAME} admin")

            full_id = f"-100{entity.id}"
            results[g["spec_key"]] = full_id
            print(f"  [OK] chat_id: {full_id}")

        except Exception as e:
            print(f"  [FAIL] Error: {e}")
            results[g["spec_key"]] = f"FAILED: {e}"

        print()

    await client.disconnect()

    # Output results
    print("=" * 60)
    print("RESULTS -- chat_ids for setup_spec.yaml:")
    print("=" * 60)
    for spec_key, chat_id in results.items():
        print(f"  {spec_key}: {chat_id}")

    # Save to JSON
    results_path = REPO_ROOT / "data" / "new_group_chat_ids.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to: {results_path}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Create 3 Telegram groups via Telethon")
    parser.add_argument("--api-id", type=int, required=True)
    parser.add_argument("--api-hash", type=str, required=True)
    parser.add_argument("--phone", type=str, required=True)
    parser.add_argument("--code", type=str, default=None, help="SMS verification code")
    parser.add_argument("--create", action="store_true", help="Create groups (session must be authed)")
    parser.add_argument("--dry-run", action="store_true", help="Print only")
    args = parser.parse_args()

    if args.create:
        asyncio.run(do_create(args.api_id, args.api_hash, args.phone, args.dry_run))
    else:
        asyncio.run(do_auth(args.api_id, args.api_hash, args.phone, args.code))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
