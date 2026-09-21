#!/usr/bin/env python3
"""Extract the token from BotFather's latest 'Congratulations' reply (no new
bot creation — the bot already exists; just pull the token it handed over).
Writes to data/notify_token_new.txt (0600). getMe-verifies before saving.
"""
import asyncio
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SESSION = str(ROOT / "data" / "telethon_setup.session")
API_ID = os.environ.get("TELEGRAM_API_ID", "30160587")
API_HASH = os.environ.get("TELEGRAM_API_HASH", "5a6af325bc59e9da130999f2ccda1674")
OUT = ROOT / "data" / "notify_token_new.txt"
TOKEN_RE = re.compile(r"\b\d+:[A-Za-z0-9_\-]{30,}\b")


def getme(token):
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


async def main() -> int:
    from telethon import TelegramClient
    client = TelegramClient(SESSION, int(API_ID), API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        print("[extract] session not authorized")
        return 1
    bf = await client.get_entity("@BotFather")
    msgs = await client.get_messages(bf, limit=30)
    token = ""
    source_text = ""
    for m in msgs or []:  # newest-first
        if getattr(m, "out", False):
            continue
        text = m.raw_text or ""
        found = TOKEN_RE.search(text)
        if found:
            token = found.group(0)
            source_text = text
            break
    if not token:
        print("[extract] no token in BotFather inbound messages — create the bot first")
        await client.disconnect()
        return 1

    ok, info = getme(token)
    mask = token[:10] + "..." + token[-4:]
    print(f"[extract] token: {mask}  getMe_ok={ok}  user={info}")
    if ok:
        OUT.write_text(token + "\n", encoding="utf-8")
        try:
            OUT.chmod(0o600)
        except Exception:
            pass
        print(f"[extract] VERIFIED token -> {OUT.name}")
    else:
        print("[extract] token failed getMe — NOT saved. Source reply:")
        print("  " + source_text[:200])
    await client.disconnect()
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
