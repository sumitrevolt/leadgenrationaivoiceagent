#!/usr/bin/env python3
"""Create the 3 coordination groups as FORUM supergroups in ONE session.

Why a new script:
  * The first create (megagroup, no forums) worked, but you cannot later
    toggle an existing supergroup into a forum, nor resolve the private
    chat ids in a fresh session (no access_hash, not in dialogs).
  * The RELIABLE pattern is to do everything on the entity object that
    CreateChannelRequest returns (it carries the access_hash), in the SAME
    session. That's what this does: create(forums=True) -> invite both
    bots -> promote to admin(manage_topics) -> create every declared
    forum topic -> bind the new chat_id via the canonical SSOT writer.

Outcome: the spec points at the new FORUM groups. The 3 earlier empty
non-forum groups (old ids in data/new_group_chat_ids.json, pre-forum)
become orphans the owner closes in-app (see the trailing NOTE).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SESSION = str(ROOT / "data" / "telethon_setup.session")
NEW_IDS = ROOT / "data" / "new_group_chat_ids.json"
OLD_IDS = ROOT / "data" / "old_nonforum_group_ids.json"
# Credentials MUST come from the environment. Never commit an api_id/api_hash as a
# source default — this repository is PUBLIC, so a committed credential is
# compromised by definition and must be rotated.
API_ID = os.environ.get("TELEGRAM_API_ID", "").strip()
API_HASH = os.environ.get("TELEGRAM_API_HASH", "").strip()
if not (API_ID and API_HASH):
    print(
        "[error] TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in the environment.\n"
        "        Obtain them from https://my.telegram.org and export them; never commit them.",
        file=sys.stderr,
    )
    sys.exit(2)
PHONE = os.environ.get("TELEGRAM_PHONE", "+918261030181")

sys.path.insert(0, str(ROOT / "scripts"))
import telegram_wire_coordination_groups as wire  # noqa: E402

KEYS = ("workers_coordination", "agents_coordination", "admin_command_center")


def _bot_usernames() -> list[str]:
    out = {}
    try:
        for line in (ROOT / ".env").read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    j = (
        os.environ.get("TELEGRAM_JARVIS_BOT_USERNAME")
        or out.get("TELEGRAM_JARVIS_BOT_USERNAME")
        or "Sumits_jarvis_bot"
    )
    n = (
        os.environ.get("TELEGRAM_NOTIFY_BOT_USERNAME")
        or out.get("TELEGRAM_NOTIFY_BOT_USERNAME")
        or "Leadsgenai1_bot"
    )
    return [u.lstrip("@") for u in (j, n)]


async def main() -> int:
    from telethon import TelegramClient, functions, types
    from telethon.tl.functions.messages import CreateForumTopicRequest

    spec = wire.load_spec()
    plan = []
    for key in KEYS:
        group, err = wire.resolve_group(spec, key)
        if err or group is None:
            print(f"[make-forum][ERROR] {key}: {err}")
            return 1
        plan.append((key, group))

    client = TelegramClient(SESSION, int(API_ID), API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        print("[make-forum] session not authorized; run two-phase auth first")
        return 1
    me = await client.get_me()
    print(f"[make-forum] logged in as: {me.first_name} ({me.phone})")

    rights = types.ChatAdminRights(
        change_info=True,
        post_messages=True,
        edit_messages=True,
        delete_messages=True,
        ban_users=True,
        invite_users=True,
        pin_messages=True,
        add_admins=True,
        manage_call=True,
        manage_topics=True,
        other=True,
    )
    bot_names = _bot_usernames()

    # Capture the PRE-forum orphan ids (from the earlier non-forum create) so the
    # owner can close them in-app after the new forum groups take over the spec.
    orphans: dict[str, str] = {}
    if NEW_IDS.exists():
        orphans = json.loads(NEW_IDS.read_text())
    OLD_IDS.write_text(json.dumps(orphans, indent=2), encoding="utf-8")
    print(f"[make-forum] previous (non-forum) group ids saved to {OLD_IDS.name}: {orphans}")

    new_ids: dict[str, str] = {}

    for key, group in plan:
        title = str(group.get("name") or key).strip()
        about = str(group.get("purpose") or "")[:255]
        print(f"\n--- {key}: {title} (forum supergroup) ---")

        # CREATE — the returned entity carries the access_hash for all later calls.
        res = await client(
            functions.channels.CreateChannelRequest(
                title=title,
                about=about,
                broadcast=False,
                megagroup=True,
                forum=True,
            )
        )
        ent = res.chats[0]
        cid = int(f"-100{ent.id}")
        new_id_str = f"-100{ent.id}"
        print(
            f"[OK] created forum group {key} -> {new_id_str} (is_forum={getattr(ent, 'is_forum', '?')})"
        )

        new_ids[key] = new_id_str

        # INVITE BOTH BOTS using the entity (this is the pattern that worked)
        for uname in bot_names:
            try:
                bot = await client.get_entity("@" + uname)
                await client(functions.channels.InviteToChannelRequest(channel=ent, users=[bot]))
                await client(
                    functions.channels.EditAdminRequest(
                        channel=ent, user_id=bot, admin_rights=rights, rank="Coordination"
                    )
                )
                print(f"[OK] @{uname} member + admin (manage_topics=True)")
            except Exception as exc:
                print(f"[WARN] @{uname} admin: {exc}")

        # CREATE TOPICS using the entity
        declared = [str(t) for t in (group.get("forum_topics") or [])]
        topic_ids: dict[str, int] = {}
        for topic in declared:
            try:
                tr = await client(CreateForumTopicRequest(peer=ent, title=topic[:128]))
                tid = None
                for upd in getattr(tr, "updates", []) or []:
                    cft = getattr(upd, "created_forum_topic", None)
                    if cft is not None:
                        ft = getattr(cft, "forum_topic", None)
                        if ft is not None:
                            tid = ft.id
                        break
                if tid:
                    topic_ids[topic] = tid
                    print(f"[OK] topic '{topic}' -> thread {tid}")
                else:
                    print(f"[OK] topic '{topic}' created (thread id not surfaced)")
            except Exception as exc:
                print(f"[WARN] topic '{topic}': {exc}")

        # PERSIST topic_ids + bind new chat_id via canonical SSOT writer
        if topic_ids:
            group["topic_ids"] = {**dict(group.get("topic_ids") or {}), **topic_ids}
            wire.save_spec(spec, backup=True)
        rc = wire.bind_chat_id(key, new_id_str, force=True)
        if rc != 0:
            print(f"[ERROR] bind_chat_id({key}) refused rc={rc}")

    NEW_IDS.write_text(json.dumps(new_ids, indent=2), encoding="utf-8")
    await client.disconnect()
    print(f"\n[make-forum] done — new forum ids written to {NEW_IDS.name}.")
    print(
        "[make-forum] Re-verify next: python scripts/telegram_wire_coordination_groups.py --verify --deep"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
