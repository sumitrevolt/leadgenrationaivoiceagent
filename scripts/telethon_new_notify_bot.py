#!/usr/bin/env python3
"""Create a brand-new Notify bot under the LIVE MTProto account via @BotFather.

Flow: /newbot -> BotFather asks display name -> we answer -> BotFather asks
username -> we answer -> BotFather replies with the API token. We extract +
getMe-verify the token and save it to data/notify_token_new.txt.

The new bot belongs to the Sunny account (the one that owns 0 bots), so
/revoke /token /newbot all work under it — no cross-account boundary.

Safety: token saved to disk 0600, log shows masked prefix only. .env is NOT
touched here.

Usage:
    python scripts/telethon_new_notify_bot.py [--name "LeadGen Notify"] [--username LeadgenaiNotify_bot]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SESSION = str(ROOT / "data" / "telethon_setup.session")
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
OUT = ROOT / "data" / "notify_token_new.txt"
TOKEN_RE = re.compile(r"\b\d+:[A-Za-z0-9_\-]{30,}\b")


def getme(token: str) -> tuple[bool, str]:
    if not token:
        return False, "(empty)"
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=15) as r:
            data = json.load(r)
        if data.get("ok"):
            return True, str((data.get("result") or {}).get("username"))
        return False, str(data.get("description"))
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


async def last_bf_text(client, bf, limit: int = 5) -> str:
    """Most-recent inbound (BotFather) message text."""
    msgs = await client.get_messages(bf, limit=limit)
    for m in msgs or []:  # get_messages is newest-first
        if not getattr(m, "out", False):
            return m.raw_text or ""
    return ""


async def bf_inbound_all(client, bf, limit: int = 30) -> list[str]:
    """All inbound (BotFather) message texts, newest-first."""
    msgs = await client.get_messages(bf, limit=limit)
    out = []
    for m in msgs or []:
        if not getattr(m, "out", False):
            out.append(m.raw_text or "")
    return out


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="LeadGen Notify")
    ap.add_argument("--username", default="LeadgenaiNotify_bot")
    a = ap.parse_args()

    from telethon import TelegramClient

    client = TelegramClient(SESSION, int(API_ID), API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        print("[new-bot] session not authorized; run two-phase auth first")
        return 1
    me = await client.get_me()
    print(f"[new-bot] logged in as: {me.first_name} ({me.phone})")

    bf = await client.get_entity("@BotFather")
    uname = a.username.lstrip("@")

    async def wait_pattern(after_text: str, needles: list[str], timeout: float = 60) -> str:
        """Poll BotFather's latest reply until it contains one of `needles`."""
        import time as _t

        start = _t.time()
        while _t.time() - start < timeout:
            await asyncio.sleep(2)
            text = await last_bf_text(client, bf, limit=6)
            low = (text or "").lower()
            for n in needles:
                if n.lower() in low:
                    return text
        return await last_bf_text(client, bf, limit=6)

    # 1) /newbot  -> BotFather asks for a display name
    await client.send_message(bf, "/newbot")
    q1 = await wait_pattern(
        "/newbot",
        ["give it a name", "what would you like to call", "choose one that indicates", "name?"],
        timeout=45,
    )
    print(f"[new-bot] BotFather Q1: {q1[:90]!r}")

    # 2) display name  -> BotFather asks for a username
    await client.send_message(bf, a.name)
    q2 = await wait_pattern(a.name, ["what about a username", "username?"], timeout=45)
    print(f"[new-bot] BotFather Q2: {q2[:90]!r}")

    # 3) username -> BotFather replies with the token (or an already-taken error)
    await client.send_message(bf, uname)
    print("[new-bot] waiting for token reply ...")
    token = ""
    for _ in range(25):
        await asyncio.sleep(2)
        text = await last_bf_text(client, bf, limit=6) or ""
        low = text.lower()
        found = TOKEN_RE.search(text)
        if found:
            token = found.group(0)
            break
        if "already taken" in low or "can't be identical" in low:
            print(f"[new-bot] BotFather rejected username: {text[:160]!r}")
            await client.disconnect()
            return 2

    if not token:
        print("[new-bot] no token in BotFather replies yet — re-run or check manually")
        await client.disconnect()
        return 1

    ok, info = getme(token)
    mask = token[:10] + "..." + token[-4:]
    print(f"[new-bot] token: {mask}  getMe_ok={ok}  {info}")
    if ok:
        OUT.write_text(token + "\n", encoding="utf-8")
        try:
            OUT.chmod(0o600)
        except Exception:
            pass
        print(f"[new-bot] VERIFIED token saved to {OUT.name}")
    else:
        print("[new-bot] token failed getMe — NOT saved. Check BotFather chat.")
    await client.disconnect()
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
