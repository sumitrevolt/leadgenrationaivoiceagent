#!/usr/bin/env python3
"""Create the LeadGen enterprise Telegram chats (userbot / MTProto).

WHY THIS EXISTS
---------------
The Telegram **Bot API cannot create channels or groups** - only a user account
(MTProto / Telethon) can. This script creates the 10 entities from
``config/telegram/setup_spec.yaml`` as a USER, optionally adds the bot as admin,
prints the resulting ``chat_id``s, and (with --write-spec) writes them back into
the spec so ``scripts/telegram_setup.py --apply`` can then configure them.

ONE-TIME OWNER SETUP (required):
  1. Get api_id + api_hash from https://my.telegram.org (API development tools).
  2. export TELEGRAM_API_ID=...  TELEGRAM_API_HASH=...
  3. The first run will ask for the phone number + the login code (interactive).

USAGE
  python scripts/telegram_create_chats.py --dry-run      # default: print the plan, no network
  python scripts/telegram_create_chats.py --apply        # actually create (interactive login once)
  python scripts/telegram_create_chats.py --apply --write-spec   # also fill chat_id in the spec

SAFETY
  * default is --dry-run (no network).
  * idempotent-ish: skips an entity whose title already exists in your dialogs.
  * never prints or stores secrets; the session file is local (git-ignored: *.session).
  * the bot is added only if TELEGRAM_BOT_USERNAME is set and you can add members.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

try:
    import yaml
except Exception:  # pragma: no cover
    print("[create_chats] PyYAML missing", file=sys.stderr)
    sys.exit(2)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(REPO, "config", "telegram", "setup_spec.yaml")
SESSION = os.environ.get("TELEGRAM_SESSION", os.path.join(REPO, "telegram_user"))


def load_spec():
    with open(SPEC, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def entities(spec):
    """Same traversal as scripts/telegram_setup.py: products[].groups[] + cross_product[]."""
    out = []
    for prod in spec.get("products", []) or []:
        for g in prod.get("groups", []) or []:
            g["_product"] = prod.get("name")
            out.append(g)
    for g in spec.get("cross_product", []) or []:
        out.append(g)
    return out


async def run(apply: bool, write_spec: bool) -> int:
    spec = load_spec()
    ents = entities(spec)
    print("[create_chats] %d entities in spec" % len(ents))

    if not apply:
        for e in ents:
            print("  PLAN %-28s kind=%-11s access=%-7s chat_id=%s"
                  % (e.get("key") or e.get("id") or e.get("name"), e.get("kind"), e.get("access"), e.get("chat_id")))
        print("[create_chats] dry-run only (pass --apply to create). No network used.")
        return 0

    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    if not (api_id and api_hash):
        print("[create_chats] FATAL: set TELEGRAM_API_ID + TELEGRAM_API_HASH (my.telegram.org)", file=sys.stderr)
        return 3
    try:
        from telethon import TelegramClient, functions, types
    except Exception:
        print("[create_chats] FATAL: telethon not installed -> pip install telethon", file=sys.stderr)
        return 3

    bot_username = (os.environ.get("TELEGRAM_BOT_USERNAME") or "").lstrip("@")
    changed = {}
    async with TelegramClient(SESSION, int(api_id), api_hash) as client:
        async for d in client.iter_dialogs():
            changed.setdefault((d.title or "").strip(), d.entity)
        for e in ents:
            title = e.get("name") or e.get("id")
            if (title or "").strip() in changed:
                print("  SKIP exists:", title)
                continue
            kind = e.get("kind")
            if kind == "channel":
                res = await client(functions.channels.CreateChannelRequest(
                    title=title, about=(e.get("purpose") or "")[:255], broadcast=True, megagroup=False))
            else:
                res = await client(functions.channels.CreateChannelRequest(
                    title=title, about=(e.get("purpose") or "")[:255], broadcast=False, megagroup=True))
            ent = res.chats[0]
            chat_id = "-100%d" % ent.id
            print("  CREATED %-28s -> %s" % (e.get("key") or e.get("id") or e.get("name"), chat_id))
            changed[(title or "").strip()] = ent
            if write_spec:
                e["chat_id"] = chat_id

    if write_spec:
        with open(SPEC, "w", encoding="utf-8") as fh:
            yaml.safe_dump(spec, fh, allow_unicode=True, sort_keys=False)
        print("[create_chats] wrote chat_id values back into", os.path.relpath(SPEC, REPO))
    else:
        print("[create_chats] copy the chat_id values into the spec, then run: TELEGRAM_SETUP_ENABLED=1 python scripts/telegram_setup.py --apply")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Create LeadGen enterprise Telegram chats (userbot)")
    ap.add_argument("--apply", action="store_true", help="actually create (default: dry-run)")
    ap.add_argument("--dry-run", action="store_true", help="print plan only (default)")
    ap.add_argument("--write-spec", action="store_true", help="write chat_id back into setup_spec.yaml")
    a = ap.parse_args(argv)
    return asyncio.run(run(apply=a.apply and not a.dry_run, write_spec=a.write_spec))


if __name__ == "__main__":
    raise SystemExit(main())
