#!/usr/bin/env python3
"""Wire @Leadsgenai1_bot into the LeadGen enterprise chats: add as member -> promote to admin.

Path B (programmatic). Requires a Telethon user session:
  export TELEGRAM_API_ID=<from my.telegram.org or tdesktop public fallback>
  export TELEGRAM_API_HASH=<same>
  python scripts/telegram_wire_bot.py            # dry-run (resolve by title)
  python scripts/telegram_wire_bot.py --apply    # invite + promote + write spec

2026-09-13 hardening (after first live run):
  * Basic (small) groups: InviteToChannelRequest raised "Cannot cast InputPeerChat
    to any kind of InputChannel" -> use messages.AddChatUserRequest, which also
    triggers the automatic migration to a supergroup.
  * Channels: InviteToChannelRequest legally fails with "Bots can only be admins
    in channels" -> that is FINE; EditAdminRequest promotes a non-member bot.
  * After any successful add, re-resolve the entity by title from a FRESH dialogs
    snapshot (migration changes the id), then promote + capture the NEW chat_id.
  * Canonical id formatting via telethon.utils.get_peer_id (no hand-rolled -100).
"""
from __future__ import annotations

import asyncio
import os
import re
import sys

try:
    import yaml
except Exception:  # pragma: no cover
    print("PyYAML missing")
    sys.exit(2)

from telethon import TelegramClient, functions, types, utils

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


async def snapshot_titles(client):
    by_title = {}
    async for d in client.iter_dialogs():
        k = norm(d.title)
        prev = by_title.get(k)
        # Same-title duplicate (pre/post migration): supergroup/channel ko prefer karo
        if prev is None or (isinstance(d.entity, types.Channel) and not isinstance(prev, types.Channel)):
            by_title[k] = d.entity
    return by_title


async def run(apply: bool):
    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    if not (api_id and api_hash):
        print("FATAL: set TELEGRAM_API_ID + TELEGRAM_API_HASH")
        return 3

    spec, ents = spec_entities()
    want = {norm(e.get("name")): e for e in ents}

    client = TelegramClient(SESSION, int(api_id), api_hash)
    await client.start()
    me = await client.get_me()
    print("logged in as", me.first_name, me.id)

    bot = await client.get_entity("@" + BOT)
    by_title = await snapshot_titles(client)

    rights = types.ChatAdminRights(
        change_info=True, post_messages=True, edit_messages=True, delete_messages=True,
        ban_users=True, invite_users=True, pin_messages=True, add_admins=True,
        anonymous=False, manage_call=True, other=True, manage_topics=True,
    )

    ok = failed = 0
    for key, e in want.items():
        name = e.get("name")
        ent = by_title.get(key)
        if ent is None:
            print("  MISS (not found in dialogs):", name)
            failed += 1
            continue

        if not apply:
            print("  %-38s -> %s" % (name, utils.get_peer_id(ent)))
            continue

        is_channel = isinstance(ent, types.Channel)
        if not is_channel and apply:
            # Basic group -> supergroup migration (prerequisite: channels.EditAdmin
            # granular rights supergroups/channels pe hi kaam karte hain; basic
            # groups me EditChatAdmin ke paas sirf coarse is_admin hai).
            try:
                await client(functions.messages.MigrateChatRequest(chat_id=ent.id))
                print("  %-38s migrated to supergroup" % name)
                by_title = await snapshot_titles(client)
                ent = by_title.get(key) or ent
            except Exception as exc:  # noqa: BLE001
                # CHAT_ID_INVALID ka rendered text bhi ho sakta hai (already-migrated)
                # -> hamesha fresh snapshot se re-resolve, phir promote try hota hai
                print("    migrate note:", str(exc)[:90])
                by_title = await snapshot_titles(client)
                ent = by_title.get(key) or ent
            # bot basic group ka member tha; migration ke baad membership carry ho jaati hai

        # Forum topics (spec wale supergroups): Bot API forum toggle nahi kar sakta,
        # owner-side MTProto toggle (idempotent: already-on pe error -> note only).
        if apply and e.get("forum_topics") and isinstance(ent, types.Channel):
            try:
                await client(functions.channels.ToggleForumRequest(channel=ent, enabled=True, tabs=False))
                print("    forum mode ON")
            except Exception as exc:  # noqa: BLE001
                print("    forum note:", str(exc)[:90])

        try:
            await client(functions.channels.EditAdminRequest(channel=ent, user_id=bot, admin_rights=rights, rank="bot"))
            print("    promoted to admin; chat_id=%s" % utils.get_peer_id(ent))
            e["chat_id"] = str(utils.get_peer_id(ent))
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print("    promote FAILED:", str(exc)[:120])
            failed += 1

    if apply:
        with open(SPEC, "w", encoding="utf-8") as fh:
            yaml.safe_dump(spec, fh, allow_unicode=True, sort_keys=False)
        print("spec updated (%d ok, %d failed) -> run: TELEGRAM_SETUP_ENABLED=1 python scripts/telegram_setup.py --apply" % (ok, failed))
    else:
        print("dry-run (pass --apply to wire + update spec)")
    await client.disconnect()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    asyncio.run(run(apply="--apply" in sys.argv))
