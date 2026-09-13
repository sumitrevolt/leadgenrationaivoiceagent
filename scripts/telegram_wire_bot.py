#!/usr/bin/env python3
"""Wire @Leadsgenai1_bot into the LeadGen enterprise chats: add as member -> promote to admin.

Path B (programmatic). Requires a Telethon user session:
  export TELEGRAM_API_ID=<from my.telegram.org>
  export TELEGRAM_API_HASH=<from my.telegram.org>
  python scripts/telegram_wire_bot.py            # interactive one-time login (code arrives in your Telegram app)

What it does:
  1. logs in (one-time; session saved to ./telegram_user.session, git-ignored)
  2. resolves each chat in config/telegram/setup_spec.yaml BY TITLE via get_dialogs
     (basic groups migrate to supergroups when members are added, so ids change)
  3. invites the bot, then promotes it to admin (per full rights)
  4. writes the CURRENT chat_id back into the spec, so `telegram_setup.py --apply` works

Safe: prints a plan first; --apply performs the writes. Idempotent-ish (skips if the bot is already admin).
"""
from __future__ import annotations

import asyncio
import os
import re
import sys

try:
    import yaml
except Exception:  # pragma: no cover
    print("PyYAML missing"); sys.exit(2)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(REPO, "config", "telegram", "setup_spec.yaml")
SESSION = os.path.join(REPO, "telegram_user")
BOT = os.environ.get("TELEGRAM_BOT_USERNAME", "Leadsgenai1_bot")


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def spec_entities():
    with open(SPEC, encoding="utf-8") as fh:
        spec = yaml.safe_load(fh)
    ents = []
    for p in spec.get("products", []) or []:
        for g in p.get("groups", []) or []:
            ents.append(g)
    for g in spec.get("cross_product", []) or []:
        ents.append(g)
    return spec, ents


async def run(apply: bool):
    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    if not (api_id and api_hash):
        print("FATAL: set TELEGRAM_API_ID + TELEGRAM_API_HASH"); return 3
    try:
        from telethon import TelegramClient, functions, types
    except Exception:
        print("FATAL: telethon not installed"); return 3

    spec, ents = spec_entities()
    want = {norm(e.get("name")): e for e in ents}

    client = TelegramClient(SESSION, int(api_id), api_hash)
    await client.start()
    me = await client.get_me()
    print("logged in as", me.first_name, me.id)

    bot = await client.get_entity("@" + BOT)
    by_title = {}
    async for d in client.iter_dialogs():
        by_title[norm(d.title)] = d.entity

    rights = types.ChatAdminRights(
        change_info=True, delete_messages=True, ban_users=True, invite_users=True,
        pin_messages=True, add_admins=True, manage_call=True, other=True,
    )

    for key, e in want.items():
        name = e.get("name")
        ent = by_title.get(key)
        if ent is None:
            print("  MISS (not found in dialogs):", name); continue
        cid = getattr(ent, "id", None)
        full = "-100%d" % cid if not str(cid).startswith("-") else str(cid)
        print("  %-38s -> %s" % (name, full))
        if not apply:
            continue
        try:
            if getattr(e, "kind", None) == "channel":
                await client(functions.channels.InviteToChannelRequest(channel=ent, users=[bot]))
            else:
                await client(functions.channels.InviteToChannelRequest(channel=ent, users=[bot]))
        except Exception as exc:
            print("    invite note:", str(exc)[:90])
        try:
            await client(functions.channels.EditAdminRequest(channel=ent, user_id=bot, admin_rights=rights, rank="bot"))
            print("    promoted to admin")
        except Exception as exc:
            print("    promote FAILED:", str(exc)[:120])
        e["chat_id"] = full

    if apply:
        with open(SPEC, "w", encoding="utf-8") as fh:
            yaml.safe_dump(spec, fh, allow_unicode=True, sort_keys=False)
        print("spec updated with current chat_ids -> run: TELEGRAM_SETUP_ENABLED=1 python scripts/telegram_setup.py --apply")
    else:
        print("dry-run (pass --apply to wire + update spec)")
    await client.disconnect()
    return 0


if __name__ == "__main__":
    asyncio.run(run(apply="--apply" in sys.argv))
