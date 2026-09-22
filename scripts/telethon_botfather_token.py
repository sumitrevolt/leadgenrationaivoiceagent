#!/usr/bin/env python3
"""Re-issue a bot's API token by driving @BotFather over the live MTProto user
session. No owner manual step: it sends /revoke <bot> to BotFather, reads the
reply, extracts the fresh token, and verifies it with getMe.

Why: the Notify slot (bot 8889560331 / @Leadsgenai1_bot) token in .env is 401.
/revoke always returns a guaranteed-live token, so it's the clean single action.

Safety:
  * the extracted token is written to data/notify_token_new.txt (not printed in
    full; the log shows a masked prefix only).
  * .env is NOT touched here — a separate, backed-up, surgical edit happens
    after getMe confirms the token is live.
  * read-only on everything except the single BotFather command the owner asked for.

Usage:
    python scripts/telethon_botfather_token.py [--username Leadsgenai1_bot] [--revoke]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
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


def load_dotenv() -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for line in (ROOT / ".env").read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return out


def getme(token: str) -> bool:
    import json
    import urllib.request
    if not token:
        return False
    try:
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/getMe", timeout=15
        ) as r:
            data = json.load(r)
        return bool(data.get("ok"))
    except Exception:
        return False


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--username", default="Leadsgenai1_bot")
    ap.add_argument("--revoke", action="store_true",
                    help="send /revoke (default; guaranteed-live token). "
                         "Pass without --revoke to send /token (returns current).")
    a = ap.parse_args()
    uname = a.username.lstrip("@")

    from telethon import TelegramClient
    client = TelegramClient(SESSION, int(API_ID), API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        print("[bf] session not authorized; run two-phase auth first")
        return 1

    # 1) confirm the target bot exists and is a bot
    try:
        bot = await client.get_entity("@" + uname)
        is_bot = bool(getattr(bot, "is_bot", False))
        print(f"[bf] @{uname} id={bot.id} is_bot={is_bot} first_name={getattr(bot,'first_name','?')}")
    except Exception as exc:
        print(f"[bf] could not resolve @{uname}: {exc}")
        return 1

    cmd = "/revoke" if a.revoke else "/token"
    print(f"[bf] sending '{cmd} @{uname}' to @BotFather ...")
    bf = await client.get_entity("@BotFather")
    await client.send_message(bf, f"{cmd} @{uname}")

    # 2) poll for BotFather's reply and extract the token
    token = ""
    last_text = ""
    for _ in range(15):
        await asyncio.sleep(2)
        msgs = await client.get_messages(bf, limit=3)
        for m in reversed(msgs):
            text = m.raw_text or ""
            found = TOKEN_RE.search(text)
            if found:
                token = found.group(0)
                last_text = text
                break
        if token:
            break

    if not token:
        print(f"[bf] no token in BotFather reply yet. Last text: {last_text[:160]!r}")
        await client.disconnect()
        return 1

    # 3) verify with getMe
    live = getme(token)
    mask = token[:12] + "..." + token[-4:]
    print(f"[bf] token received: {mask}  getMe_live={live}")
    if live:
        OUT.write_text(token + "\n", encoding="utf-8")
        OUT.chmod(0o600) if hasattr(OUT, "chmod") else None
        print(f"[bf] VERIFIED. token saved to {OUT.name}. Now update .env surgically.")
    else:
        print("[bf] token did NOT pass getMe — do NOT update .env. Re-check.")
    await client.disconnect()
    return 0 if live else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
