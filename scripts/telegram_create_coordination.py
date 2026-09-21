#!/usr/bin/env python3
"""Create the 3 required coordination groups over MTProto (user session).

WHY THIS EXISTS
---------------
The Telegram **Bot API cannot create groups** — only a user account (MTProto /
Telethon) can. This script creates the three required coordination supergroups
from ``config/telegram/setup_spec.yaml`` (``workers_coordination``,
``agents_coordination``, ``admin_command_center``) as a **forum-enabled**
supergroup, promotes the owner-configured bot(s) to admin with
``manage_topics`` rights, then writes each resulting ``chat_id`` back into the
spec **through the canonical SSOT writer** in
``scripts/telegram_wire_coordination_groups.py`` (``bind_chat_id``) so the
existing backup + round-trip guards still apply. No second, weaker writer.

ONE-TIME OWNER INPUTS (required before --apply)
-----------------------------------------------
1. ``TELEGRAM_API_ID`` + ``TELEGRAM_API_HASH`` from https://my.telegram.org
   (API development tools → create an app → copy both). Keep them ONLY in
   env/.env, never commit.
2. First run of --apply prompts once for the phone number + the login code,
   then persists a local session file (git-ignored ``telegram_user.session``).

SAFETY
------
* default is a **dry-run** (reads the spec, prints the plan, ZERO network).
* idempotent: a group whose title already exists in your dialogs is skipped.
* fail-closed: any Telegram API error is reported, never swallowed as success.
* bot usernames come from env (``TELEGRAM_JARVIS_BOT_USERNAME`` optional; the
  Notify bot is added too when ``TELEGRAM_NOTIFY_BOT_USERNAME`` is set).

USAGE
-----
    python scripts/telegram_create_coordination.py                # dry-run
    python scripts/telegram_create_coordination.py --apply        # create
    python scripts/telegram_create_coordination.py --apply --write-spec
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

try:
    import yaml
except Exception:  # pragma: no cover
    print("[coordination] PyYAML missing", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "config" / "telegram" / "setup_spec.yaml"
SESSION = os.environ.get("TELEGRAM_SESSION", str(ROOT / "telegram_user"))

# Canonical SSOT writer — reuse, do not re-implement.
sys.path.insert(0, str(ROOT / "scripts"))
import telegram_wire_coordination_groups as wire  # noqa: E402

#: The three required coordination surfaces (key → spec group).
COORDINATION_KEYS = ("workers_coordination", "agents_coordination", "admin_command_center")

# Forum admin rights the bot needs to run createForumTopic / pin / moderate.
_ADMIN_FLAGS = (
    "can_post_messages",
    "can_edit_messages",
    "can_delete_messages",
    "can_pin_messages",
    "can_manage_topics",
    "can_invite_users",
)


def _read_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return out


def _env(name: str, dotenv: dict[str, str]) -> str:
    return (os.environ.get(name) or dotenv.get(name) or "").strip()


def load_groups() -> dict[str, dict]:
    spec = wire.load_spec()
    out: dict[str, dict] = {}
    for key in COORDINATION_KEYS:
        group, err = wire.resolve_group(spec, key)
        if err or group is None:
            print(f"[coordination][ERROR] {key}: {err or 'not found in spec'}")
            sys.exit(1)
        out[key] = group
    return out


def plan(groups: dict[str, dict]) -> int:
    dotenv = _read_dotenv(ROOT / ".env")
    api_id = _env("TELEGRAM_API_ID", dotenv)
    api_hash = _env("TELEGRAM_API_HASH", dotenv)
    print("[coordination] DRY-RUN — %d required coordination groups\n" % len(groups))
    for key, g in groups.items():
        bound = str(g.get("chat_id") or "").strip()
        state = "already bound %s" % bound if bound else "needs creation"
        print("  PLAN %-24s kind=%-10s access=%-7s %s"
              % (key, g.get("kind"), g.get("access"), state))
        if g.get("forum_topics"):
            print("        topics: %s" % ", ".join(g["forum_topics"]))
    print("\n[coordination] creds: API_ID=%s  API_HASH=%s"
          % ("set" if api_id else "MISSING", "set" if api_hash else "MISSING"))
    if not (api_id and api_hash):
        print("[coordination] To apply, set TELEGRAM_API_ID + TELEGRAM_API_HASH "
              "(https://my.telegram.org) then run:  --apply")
    else:
        print("[coordination] Creds present. Run with --apply to create "
              "(one-time phone-code login).")
    return 0


async def _create_one(client, key: str, group: dict) -> tuple[str, str] | None:
    """Create the supergroup (forum-enabled) unless it already exists.

    Returns ``(chat_id, entity_title)`` or ``None`` when skipped as existing.
    """
    from telethon import functions, types

    title = str(group.get("name") or group.get("key") or key).strip()

    # Idempotency: skip if a dialog with this title already exists.
    for d in await client.get_dialogs(limit=200):
        if (d.title or "").strip() == title:
            print("  SKIP exists: %s" % title)
            return None

    result = await client(functions.channels.CreateChannelRequest(
        title=title,
        about=str(group.get("purpose") or "")[:255],
        broadcast=False,          # supergroup, not channel
        megagroup=True,
        forums=True,             # enable forum topics
    ))
    ent = result.chats[0]
    chat_id = "-100%d" % ent.id
    print("  CREATED %-24s -> %s" % (key, chat_id))
    return chat_id, title


async def _grant_bots(client, chat_id: str, user_names: list[str]) -> None:
    """Promote the owner's bots to admin with manage_topics rights."""
    from telethon import functions, types

    rights = types.ChatAdminRights(**{f: True for f in _ADMIN_FLAGS},
                                    change_rank=False,
                                    is_anonymous=False,
                                    promote_to_admin=False,
                                    title="Coordination Bot")
    for uname in user_names:
        if not uname:
            continue
        try:
            bot = await client.get_entity("@" + uname.lstrip("@"))
            await client(functions.channels.InviteToChannelRequest(
                peer=int(chat_id), fwd=bot.id))
            await client(functions.channels.EditAdminRequest(
                channel=int(chat_id), user_id=bot.id, admin_rights=rights))
            print("    admin: @%s (manage_topics=%s)" % (uname, True))
        except Exception as exc:  # pragma: no cover - reported, never swallowed
            print("    WARN could not add/admin @%s: %s" % (uname, exc))


async def run(apply: bool, write_spec: bool) -> int:
    groups = load_groups()

    if not apply:
        return plan(groups)

    dotenv = _read_dotenv(ROOT / ".env")
    api_id = _env("TELEGRAM_API_ID", dotenv)
    api_hash = _env("TELEGRAM_API_HASH", dotenv)
    if not (api_id and api_hash):
        print("[coordination] FATAL: set TELEGRAM_API_ID + TELEGRAM_API_HASH "
              "(my.telegram.org)", file=sys.stderr)
        return 3

    try:
        from telethon import TelegramClient
    except Exception:  # pragma: no cover
        print("[coordination] FATAL: telethon not installed -> pip install telethon",
              file=sys.stderr)
        return 3

    jarvis = _env("TELEGRAM_JARVIS_BOT_USERNAME", dotenv) or "Sumits_jarvis_bot"
    notify = _env("TELEGRAM_NOTIFY_BOT_USERNAME", dotenv) or "Leadsgenai1_bot"
    bot_names = [jarvis] + ([notify] if notify else [])

    created: dict[str, str] = {}
    async with TelegramClient(SESSION, int(api_id), api_hash) as client:
        me = await client.get_me()
        print("[coordination] logged in as: %s (id=%s)"
              % (getattr(me, "username", None), me.id))
        for key, group in groups.items():
            if str(group.get("chat_id") or "").strip():
                print("  SKIP %-24s already bound to %s"
                      % (key, group["chat_id"]))
                continue
            res = await _create_one(client, key, group)
            if res is None:
                continue
            chat_id, _title = res
            created[key] = chat_id
            await _grant_bots(client, chat_id, bot_names)

    if not created:
        print("[coordination] nothing to create (all already bound/existing).")
        return 0

    if write_spec:
        for key, chat_id in created.items():
            rc = wire.bind_chat_id(key, chat_id, force=False)
            if rc != 0:
                print("[coordination] FATAL: spec write refused for %s" % key)
                return 1
    else:
        print("\n[coordination] created ids (run --write-spec to bind, or "
              "use scripts/telegram_wire_coordination_groups.py):")
        for key, cid in created.items():
            print("  %s = %s" % (key, cid))

    print("\n[coordination] next: create forum topics + verify via the canonical tool:")
    for key in created:
        print("  python scripts/telegram_wire_coordination_groups.py "
              "--create-topics %s" % key)
    print("  python scripts/telegram_wire_coordination_groups.py --verify --deep")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Create the required coordination groups over MTProto "
                    "(user session; dry-run by default).")
    ap.add_argument("--apply", action="store_true",
                    help="actually create (default is a dry-run).")
    ap.add_argument("--write-spec", action="store_true",
                    help="bind the created chat_ids back into setup_spec.yaml "
                         "via the canonical SSOT writer.")
    a = ap.parse_args(argv)
    return asyncio.run(run(apply=a.apply, write_spec=a.write_spec))


if __name__ == "__main__":
    raise SystemExit(main())
